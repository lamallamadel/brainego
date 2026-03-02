"""
LoRA Trainer with EWC Regularization

Implements fine-tuning with:
- LoRA rank-16 adapters
- EWC regularization to prevent catastrophic forgetting
- Feedback-based training data loading
- Adapter versioning and storage
"""

import json
import logging
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)

from . import metrics as learning_metrics
from .data_loader import load_dataset_from_file
from .fisher import FisherInformationCalculator
from .storage import AdapterStorage
from .validator import GoldenSetValidator

logger = logging.getLogger(__name__)


class LoRATrainer:
    """
    LoRA trainer with EWC regularization for continuous learning.
    """

    def __init__(
        self,
        config: Any,
        storage: AdapterStorage,
        fisher_calculator: FisherInformationCalculator,
    ):
        """
        Initialize LoRA trainer.

        Args:
            config: Training configuration
            storage: Adapter storage manager
            fisher_calculator: Fisher Information Matrix calculator
        """
        self.config = config
        self.storage = storage
        self.fisher_calculator = fisher_calculator
        self.validator = GoldenSetValidator()

        self.model = None
        self.tokenizer = None
        self.current_version = "v1.0"
        self.training_status = {
            "is_training": False,
            "current_job": None,
            "last_job": None,
            "metrics": {},
            "last_run": {},
        }
        self.last_dataset_diagnostics: Dict[str, Any] = {}
        self.last_validation_report: Dict[str, Any] = {}

        logger.info("LoRA Trainer initialized")

    @staticmethod
    def _coerce_payload(value: Any) -> Dict[str, Any]:
        """Safely decode request/response payload fields from DB rows."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(decoded, dict):
                return decoded
        return {}

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """Convert metric candidate value to float when possible."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def load_base_model(self):
        """Load the base model for fine-tuning."""
        logger.info("Loading base model: %s", self.config.model_name)

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Load model with quantization
        self.model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
        )

        # Prepare for training
        self.model = prepare_model_for_kbit_training(self.model)

        logger.info("✓ Base model loaded")

    def setup_lora(self) -> None:
        """Setup LoRA configuration and apply to model."""
        logger.info("Setting up LoRA configuration...")

        lora_config = LoraConfig(
            r=self.config.lora_rank,
            lora_alpha=self.config.lora_alpha,
            target_modules=self.config.target_modules,
            lora_dropout=self.config.lora_dropout,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        )

        self.model = get_peft_model(self.model, lora_config)
        self.model.print_trainable_parameters()

        logger.info("✓ LoRA configuration applied")

    def load_feedback_data(
        self,
        days: int = 7,
    ) -> List[Dict[str, str]]:
        """
        Load training data from feedback database.

        Args:
            days: Number of days to look back

        Returns:
            List of training samples
        """
        logger.info("Loading feedback data from last %s days...", days)

        conn = psycopg2.connect(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            dbname=self.config.postgres_db,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
        )

        cursor = conn.cursor()

        # Query feedback data
        query = """
        SELECT
            request_data,
            response_data,
            feedback_type,
            created_at
        FROM feedback
        WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
        AND feedback_type IN ('thumbs_up', 'thumbs_down')
        ORDER BY created_at DESC
        """

        cursor.execute(query, (days,))
        rows = cursor.fetchall()

        # Process samples with diagnostics and basic cleaning
        samples = []
        dropped_reasons: Counter = Counter()
        feedback_distribution: Counter = Counter()
        intent_distribution: Counter = Counter()
        project_distribution: Counter = Counter()

        for row in rows:
            request_data = self._coerce_payload(row[0])
            response_data = self._coerce_payload(row[1])
            feedback_type = row[2]
            feedback_distribution[feedback_type] += 1

            # Extract messages
            messages = request_data.get("messages", [])
            assistant_response = (
                response_data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            # Basic cleaning rules to remove low-value or broken examples
            if not messages or not isinstance(messages, list):
                dropped_reasons["missing_messages"] += 1
                continue

            # Format as training sample
            input_text = self._format_messages(messages)
            output_text = assistant_response

            if not input_text:
                dropped_reasons["empty_input"] += 1
                continue
            if not output_text or not str(output_text).strip():
                dropped_reasons["empty_output"] += 1
                continue
            if len(input_text.strip()) < 15:
                dropped_reasons["short_input"] += 1
                continue
            if len(str(output_text).strip()) < 15:
                dropped_reasons["short_output"] += 1
                continue
            if input_text.strip() == str(output_text).strip():
                dropped_reasons["duplicate_input_output"] += 1
                continue

            intent_distribution[self._extract_intent(request_data, response_data)] += 1
            project_distribution[self._extract_project(request_data, response_data)] += 1

            # Apply weights based on feedback
            weight = 2.0 if feedback_type == "thumbs_up" else 0.5

            samples.append(
                {
                    "input": input_text,
                    "output": str(output_text).strip(),
                    "weight": weight,
                    "feedback_type": feedback_type,
                }
            )

        cursor.close()
        conn.close()

        self.last_dataset_diagnostics = {
            "raw_examples": len(rows),
            "kept_examples": len(samples),
            "dropped_examples": len(rows) - len(samples),
            "drop_reasons": dict(dropped_reasons),
            "feedback_distribution": dict(feedback_distribution),
            "intent_distribution": dict(intent_distribution),
            "project_distribution": dict(project_distribution),
        }

        logger.info(
            "✓ Loaded %s training samples (from %s raw examples)",
            len(samples),
            len(rows),
        )
        logger.info("Dataset diagnostics: %s", self.last_dataset_diagnostics)

        # Log weighted feedback summary for kept samples
        positive = sum(1 for s in samples if s["feedback_type"] == "thumbs_up")
        negative = len(samples) - positive
        logger.info("  Positive samples kept: %s (2.0x weight)", positive)
        logger.info("  Negative samples kept: %s (0.5x weight)", negative)

        return samples

    def load_historical_data(
        self,
        historical_days: int = 30,
        recent_days: int = 7,
    ) -> List[Dict[str, str]]:
        """Load historical feedback data for Fisher approximation."""
        logger.info(
            "Loading historical feedback data from %sd to %sd ago...",
            historical_days,
            recent_days,
        )

        conn = psycopg2.connect(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            dbname=self.config.postgres_db,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
        )

        cursor = conn.cursor()
        query = """
        SELECT
            request_data,
            response_data,
            feedback_type
        FROM feedback
        WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
          AND created_at < NOW() - (%s * INTERVAL '1 day')
          AND feedback_type IN ('thumbs_up', 'thumbs_down')
        ORDER BY created_at DESC
        """

        cursor.execute(query, (historical_days, recent_days))
        rows = cursor.fetchall()

        samples = []
        for row in rows:
            request_data = self._coerce_payload(row[0])
            response_data = self._coerce_payload(row[1])
            messages = request_data.get("messages", [])
            assistant_response = (
                response_data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            samples.append(
                {
                    "input": self._format_messages(messages),
                    "output": assistant_response,
                    "weight": 1.0,
                    "feedback_type": row[2],
                }
            )

        cursor.close()
        conn.close()

        logger.info("✓ Loaded %s historical samples for Fisher", len(samples))
        return samples

    def _format_messages(self, messages: List[Dict]) -> str:
        """Format messages for training."""
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            formatted.append(f"{role}: {content}")
        return "\n".join(formatted)

    def _extract_intent(
        self,
        request_data: Dict[str, Any],
        response_data: Dict[str, Any],
    ) -> str:
        """Best-effort intent extraction for diagnostics."""
        candidates = [
            request_data.get("intent"),
            request_data.get("metadata", {}).get("intent")
            if isinstance(request_data.get("metadata"), dict)
            else None,
            response_data.get("intent"),
            response_data.get("x-routing-metadata"),
        ]
        for candidate in candidates:
            if isinstance(candidate, dict):
                value = candidate.get("intent")
                if value:
                    return str(value)
            if isinstance(candidate, str) and candidate.strip():
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict) and parsed.get("intent"):
                        return str(parsed["intent"])
                except json.JSONDecodeError:
                    return candidate.strip()
        return "unknown"

    def _extract_project(
        self,
        request_data: Dict[str, Any],
        response_data: Dict[str, Any],
    ) -> str:
        """Best-effort project extraction for diagnostics."""
        metadata = (
            request_data.get("metadata")
            if isinstance(request_data.get("metadata"), dict)
            else {}
        )
        candidates = [
            request_data.get("project"),
            metadata.get("project"),
            response_data.get("project"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return "unknown"

    def prepare_dataset(
        self,
        samples: List[Dict[str, str]],
    ) -> Dataset:
        """
        Prepare dataset for training.

        Args:
            samples: List of training samples

        Returns:
            HuggingFace Dataset object
        """
        logger.info("Preparing dataset...")

        # Format for causal LM training
        texts: List[str] = []
        weights: List[float] = []

        for sample in samples:
            text = f"{sample['input']}\n{sample['output']}{self.tokenizer.eos_token}"
            texts.append(text)
            weights.append(float(sample["weight"]))

        # Tokenize
        tokenized = self.tokenizer(
            texts,
            truncation=True,
            max_length=self.config.max_seq_length,
            padding="max_length",
            return_tensors="pt",
        )

        # Create dataset
        dataset_dict = {
            "input_ids": tokenized["input_ids"],
            "attention_mask": tokenized["attention_mask"],
            "labels": tokenized["input_ids"].clone(),
            "weight": torch.tensor(weights, dtype=torch.float),
        }

        dataset = Dataset.from_dict(dataset_dict)

        logger.info("✓ Dataset prepared with %s samples", len(dataset))
        return dataset

    def _build_validation_thresholds(
        self, overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build effective golden-set validation thresholds from config + overrides."""
        thresholds = {
            "max_regressions": getattr(self.config, "golden_max_regressions", 1),
            "max_mean_score_drop": getattr(
                self.config, "golden_max_mean_score_drop", 0.15
            ),
            "min_pass_rate": getattr(self.config, "golden_min_pass_rate", 0.85),
            "max_unsafe_cases": getattr(self.config, "golden_max_unsafe_cases", 0),
        }

        if overrides:
            for key in thresholds:
                if key in overrides and overrides[key] is not None:
                    thresholds[key] = overrides[key]

        thresholds["max_regressions"] = int(thresholds["max_regressions"])
        thresholds["max_mean_score_drop"] = float(thresholds["max_mean_score_drop"])
        thresholds["min_pass_rate"] = float(thresholds["min_pass_rate"])
        thresholds["max_unsafe_cases"] = int(thresholds["max_unsafe_cases"])
        return thresholds

    def _derive_validation_loss(
        self,
        validation_metrics: Dict[str, Any],
        golden_validation_report: Optional[Dict[str, Any]],
    ) -> Optional[float]:
        """
        Derive a scalar validation loss for compatibility with existing dashboards.

        Preference order:
        1) explicit validation_loss provided by caller
        2) fallback from generic "loss"
        3) 1 - golden_set candidate_mean_score
        """
        if not validation_metrics:
            validation_metrics = {}

        explicit_loss = self._safe_float(validation_metrics.get("validation_loss"))
        if explicit_loss is not None:
            return explicit_loss

        generic_loss = self._safe_float(validation_metrics.get("loss"))
        if generic_loss is not None:
            return generic_loss

        if not golden_validation_report:
            return None

        comparison = golden_validation_report.get("comparison", {})
        mean_score = self._safe_float(comparison.get("candidate_mean_score"))
        if mean_score is None:
            return None
        return max(0.0, 1.0 - mean_score)

    @staticmethod
    def _version_to_number(version: str) -> float:
        """Convert semantic version (vX.Y) to a numeric gauge value."""
        try:
            core = version.replace("v", "", 1)
            major_raw, minor_raw = core.split(".", 1)
            major = int(major_raw)
            minor = int(minor_raw)
            return float(major * 100 + minor)
        except (ValueError, AttributeError):
            return 0.0

    def _generate_candidate_outputs_for_suite(
        self,
        suite_path: str,
        candidate_output_path: str,
    ) -> str:
        """
        Generate candidate outputs from the current in-memory model for golden prompts.
        """
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model/tokenizer not initialized for golden-set generation")

        suite_cases = self.validator.load_prompt_suite(Path(suite_path))
        outputs: Dict[str, str] = {}
        max_new_tokens = int(
            getattr(self.config, "golden_validation_max_new_tokens", 192)
        )

        try:
            model_device = next(self.model.parameters()).device
        except StopIteration:
            model_device = torch.device("cpu")

        for case in suite_cases:
            encoded = self.tokenizer(case.prompt, return_tensors="pt")
            encoded = {key: value.to(model_device) for key, value in encoded.items()}

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **encoded,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    num_beams=1,
                    pad_token_id=self.tokenizer.eos_token_id
                    or self.tokenizer.pad_token_id,
                )

            generated_text = self.tokenizer.decode(
                generated_ids[0], skip_special_tokens=True
            ).strip()
            candidate_text = generated_text
            if generated_text.startswith(case.prompt):
                candidate_text = generated_text[len(case.prompt) :].strip()
            outputs[case.case_id] = candidate_text or generated_text

        output_path = Path(candidate_output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps({"outputs": outputs}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Generated golden-set candidate outputs at %s", output_path)
        return str(output_path)

    def _run_golden_validation(
        self,
        output_dir: str,
        suite_path: Optional[str],
        baseline_output_path: Optional[str],
        candidate_output_path: Optional[str],
        threshold_overrides: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Run golden-set validation and return the full report."""
        effective_suite = suite_path or getattr(self.config, "golden_suite_path", None)
        effective_baseline = baseline_output_path or getattr(
            self.config, "golden_baseline_output_path", None
        )
        if not effective_suite or not effective_baseline:
            logger.info(
                "Golden-set validation skipped: suite/baseline path not configured"
            )
            return None

        effective_candidate = candidate_output_path
        candidate_source = "provided"
        if not effective_candidate:
            candidate_dir = Path(
                getattr(self.config, "golden_candidate_output_dir", "./lora_validation")
            )
            if not candidate_dir.is_absolute():
                candidate_dir = Path.cwd() / candidate_dir
            candidate_dir.mkdir(parents=True, exist_ok=True)
            effective_candidate = str(
                candidate_dir
                / f"{self.training_status['current_job']}_golden_candidate_outputs.json"
            )
            self._generate_candidate_outputs_for_suite(
                suite_path=effective_suite,
                candidate_output_path=effective_candidate,
            )
            candidate_source = "generated"

        thresholds = self._build_validation_thresholds(threshold_overrides)
        report = self.validator.validate_from_files(
            suite_path=effective_suite,
            baseline_output_path=effective_baseline,
            candidate_output_path=effective_candidate,
            thresholds=thresholds,
        )
        report["candidate_source"] = candidate_source
        report["candidate_output_path"] = str(Path(effective_candidate).resolve())
        report["output_dir"] = output_dir
        return report

    def validate_golden_set(
        self,
        suite_path: str,
        baseline_output_path: str,
        candidate_output_path: str,
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validate candidate outputs against the golden suite and baseline."""
        report = self.validator.validate_from_files(
            suite_path=suite_path,
            baseline_output_path=baseline_output_path,
            candidate_output_path=candidate_output_path,
            thresholds=self._build_validation_thresholds(thresholds),
        )
        self.last_validation_report = report
        return report

    def _build_training_provenance(
        self,
        dataset_id: str,
        days: int,
        samples_count: int,
        ewc_lambda: float,
        author: Optional[str],
        validation_enabled: bool,
        validation_required: bool,
        validation_thresholds: Dict[str, Any],
        validation_report: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build structured provenance payload for adapter metadata."""
        return {
            "job_id": self.training_status["current_job"],
            "dataset_id": dataset_id,
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "author": author or "learning-engine",
            "data_source": {
                "type": "feedback",
                "window_days": days,
                "sample_count": samples_count,
                "dataset_diagnostics": self.last_dataset_diagnostics,
            },
            "model": {
                "name": self.config.model_name,
                "lora_rank": self.config.lora_rank,
                "lora_alpha": self.config.lora_alpha,
                "lora_dropout": self.config.lora_dropout,
                "target_modules": list(self.config.target_modules),
            },
            "training_hyperparameters": {
                "learning_rate": self.config.learning_rate,
                "epochs": self.config.num_train_epochs,
                "batch_size": self.config.batch_size,
                "gradient_accumulation_steps": self.config.gradient_accumulation_steps,
                "max_seq_length": self.config.max_seq_length,
                "ewc_lambda": ewc_lambda,
            },
            "validation": {
                "enabled": validation_enabled,
                "required": validation_required,
                "thresholds": validation_thresholds,
                "report": validation_report,
            },
            "environment": {
                "service": "learning-engine",
                "git_commit": os.getenv("GIT_COMMIT_SHA"),
            },
        }

    def _publish_validation_metrics(
        self,
        version_id: str,
        validation_metrics: Dict[str, Any],
        golden_validation_report: Optional[Dict[str, Any]],
    ) -> None:
        """Publish validation metrics to Prometheus gauges/counters."""
        validation_loss_value = self._derive_validation_loss(
            validation_metrics, golden_validation_report
        )
        if validation_loss_value is not None:
            learning_metrics.validation_loss.labels(
                model=self.config.model_name,
                version_id=version_id,
            ).set(validation_loss_value)

        if not golden_validation_report:
            return

        comparison = golden_validation_report.get("comparison", {})
        pass_rate = self._safe_float(comparison.get("candidate_pass_rate"))
        mean_score = self._safe_float(comparison.get("candidate_mean_score"))
        regressions = self._safe_float(comparison.get("regressed_cases"))
        unsafe_cases = self._safe_float(comparison.get("unsafe_cases"))
        approved_flag = 1.0 if golden_validation_report.get("approved") else 0.0

        if pass_rate is not None:
            learning_metrics.model_accuracy.labels(
                model=self.config.model_name,
                version_id=version_id,
            ).set(pass_rate)
            learning_metrics.golden_validation_pass_rate.labels(
                model=self.config.model_name,
                version_id=version_id,
            ).set(pass_rate)

        if mean_score is not None:
            learning_metrics.golden_validation_mean_score.labels(
                model=self.config.model_name,
                version_id=version_id,
            ).set(mean_score)

        if regressions is not None:
            learning_metrics.golden_validation_regressions.labels(
                model=self.config.model_name,
                version_id=version_id,
            ).set(regressions)

        if unsafe_cases is not None:
            learning_metrics.golden_validation_unsafe_cases.labels(
                model=self.config.model_name,
                version_id=version_id,
            ).set(unsafe_cases)

        learning_metrics.golden_validation_approved.labels(
            model=self.config.model_name,
            version_id=version_id,
        ).set(approved_flag)

    def train_from_feedback(
        self,
        days: int = 7,
        ewc_lambda: float = 500.0,
        force: bool = False,
        job_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        author: Optional[str] = None,
        validation_metrics: Optional[Dict[str, Any]] = None,
        golden_suite_path: Optional[str] = None,
        golden_baseline_output_path: Optional[str] = None,
        golden_candidate_output_path: Optional[str] = None,
        golden_validation_required: Optional[bool] = None,
        golden_validation_enabled: Optional[bool] = None,
        golden_thresholds: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Train LoRA adapter from feedback data with EWC regularization.

        Args:
            days: Number of days to look back for training data
            ewc_lambda: EWC regularization strength
            force: Force training even if sample count is low
            job_id: Job identifier

        Returns:
            Training results dictionary
        """
        logger.info("=" * 60)
        logger.info("Starting LoRA Fine-tuning with EWC")
        logger.info("=" * 60)

        started_at = time.monotonic()

        # Update status
        self.training_status["is_training"] = True
        self.training_status["current_job"] = (
            job_id or f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        dataset_id = dataset_id or f"feedback_{days}d_{self.training_status['current_job']}"

        logger.info(
            "training_run_started",
            extra={
                "extra_fields": {
                    "event": "learning_engine.training.started",
                    "job_id": self.training_status["current_job"],
                    "dataset_id": dataset_id,
                    "thresholds": {
                        "min_samples_for_training": self.config.min_samples_for_training,
                        "ewc_lambda_min": getattr(self.config, "ewc_lambda_min", None),
                        "ewc_lambda_max": getattr(self.config, "ewc_lambda_max", None),
                    },
                    "decision": "evaluate",
                }
            },
        )

        try:
            # Load feedback data
            samples = self.load_feedback_data(days=days)

            decision_context = {
                "force": force,
                "enough_samples": len(samples) >= self.config.min_samples_for_training,
                "train": force or len(samples) >= self.config.min_samples_for_training,
            }

            # Check minimum samples
            if len(samples) < self.config.min_samples_for_training and not force:
                msg = (
                    f"Not enough samples ({len(samples)} < "
                    f"{self.config.min_samples_for_training})"
                )
                logger.warning(msg)
                learning_metrics.training_runs_total.labels(
                    model=self.config.model_name,
                    status="skipped",
                ).inc()

                self.training_status["last_run"] = {
                    "status": "skipped",
                    "dataset_id": dataset_id,
                    "dataset_size": len(samples),
                    "duration_seconds": time.monotonic() - started_at,
                    "thresholds": {
                        "min_samples_for_training": self.config.min_samples_for_training,
                        "ewc_lambda": ewc_lambda,
                    },
                    "decision": decision_context,
                }

                logger.info(
                    "training_run_skipped",
                    extra={
                        "extra_fields": {
                            "event": "learning_engine.training.skipped",
                            "job_id": self.training_status["current_job"],
                            "dataset_id": dataset_id,
                            "dataset_size": len(samples),
                            "thresholds": {
                                "min_samples_for_training": self.config.min_samples_for_training,
                                "ewc_lambda": ewc_lambda,
                            },
                            "decision": decision_context,
                        }
                    },
                )
                return {
                    "status": "skipped",
                    "message": msg,
                    "samples": len(samples),
                    "dataset_diagnostics": self.last_dataset_diagnostics,
                }

            # Load base model
            if self.model is None:
                self.load_base_model()
                self.setup_lora()

            # Save old parameters for EWC
            old_params: Dict[str, torch.Tensor] = {}
            for name, param in self.model.named_parameters():
                if param.requires_grad:
                    old_params[name] = param.data.clone()

            # Calculate Fisher matrix if not exists
            if not self.fisher_calculator.get_fisher_dict():
                logger.info(
                    "Calculating Fisher Information Matrix from historical data..."
                )
                historical_samples = self.load_historical_data(
                    historical_days=getattr(self.config, "fisher_history_days", 30),
                    recent_days=days,
                )
                fisher_samples = historical_samples if historical_samples else samples
                self.fisher_calculator.calculate_fim(
                    fisher_samples,
                    num_samples=getattr(self.config, "fisher_num_samples", 1000),
                )

            # Prepare dataset
            dataset = self.prepare_dataset(samples)
            output_dir = f"./lora_checkpoints/{self.training_status['current_job']}"
            os.makedirs(output_dir, exist_ok=True)

            train_result, run_trainer = self._run_training(
                dataset=dataset,
                output_dir=output_dir,
                learning_rate=self.config.learning_rate,
                epochs=self.config.num_train_epochs,
                batch_size=self.config.batch_size,
                fisher_calculator=self.fisher_calculator,
                old_params=old_params,
                ewc_lambda=ewc_lambda,
            )

            loss_history = [
                entry.get("loss")
                for entry in run_trainer.state.log_history
                if "loss" in entry and entry.get("loss") is not None
            ]
            initial_loss = loss_history[0] if loss_history else None
            final_loss = loss_history[-1] if loss_history else train_result.training_loss

            # Golden-set validation
            validation_enabled = (
                getattr(self.config, "golden_validation_enabled", True)
                if golden_validation_enabled is None
                else golden_validation_enabled
            )
            validation_required = (
                getattr(self.config, "golden_validation_required", False)
                if golden_validation_required is None
                else golden_validation_required
            )
            if validation_required:
                validation_enabled = True

            validation_thresholds = self._build_validation_thresholds(golden_thresholds)
            merged_validation_metrics: Dict[str, Any] = dict(validation_metrics or {})
            golden_validation_report: Optional[Dict[str, Any]] = None

            if validation_enabled:
                try:
                    golden_validation_report = self._run_golden_validation(
                        output_dir=output_dir,
                        suite_path=golden_suite_path,
                        baseline_output_path=golden_baseline_output_path,
                        candidate_output_path=golden_candidate_output_path,
                        threshold_overrides=validation_thresholds,
                    )
                    if golden_validation_report:
                        merged_validation_metrics["golden_set"] = golden_validation_report
                        comparison = golden_validation_report.get("comparison", {})
                        if comparison.get("candidate_pass_rate") is not None:
                            merged_validation_metrics.setdefault(
                                "pass_rate", comparison.get("candidate_pass_rate")
                            )
                        if comparison.get("candidate_mean_score") is not None:
                            merged_validation_metrics.setdefault(
                                "mean_score", comparison.get("candidate_mean_score")
                            )
                        self.last_validation_report = golden_validation_report
                        learning_metrics.golden_validation_runs_total.labels(
                            model=self.config.model_name,
                            status="success",
                        ).inc()
                    elif validation_required:
                        raise ValueError(
                            "Golden-set validation required but no report was produced"
                        )
                except Exception as validation_error:
                    logger.error(
                        "Golden-set validation failed: %s",
                        validation_error,
                        exc_info=True,
                    )
                    learning_metrics.golden_validation_runs_total.labels(
                        model=self.config.model_name,
                        status="failed",
                    ).inc()
                    merged_validation_metrics["golden_set"] = {
                        "status": "error",
                        "approved": False,
                        "error": str(validation_error),
                    }
                    if validation_required:
                        raise

            if (
                golden_validation_report
                and validation_required
                and not golden_validation_report.get("approved", False)
            ):
                raise ValueError(
                    "Golden-set validation failed; adapter promotion blocked"
                )

            # Generate new version
            self.current_version = self._increment_version(self.current_version)

            # Save adapter
            adapter_path = os.path.join(output_dir, "adapter")
            self.model.save_pretrained(adapter_path)

            # Record provenance for reproducibility/auditability
            provenance = self._build_training_provenance(
                dataset_id=dataset_id,
                days=days,
                samples_count=len(samples),
                ewc_lambda=ewc_lambda,
                author=author,
                validation_enabled=validation_enabled,
                validation_required=validation_required,
                validation_thresholds=validation_thresholds,
                validation_report=golden_validation_report,
            )

            # Upload to MinIO
            logger.info("Uploading adapter version %s...", self.current_version)
            self.storage.upload_adapter(
                local_path=adapter_path,
                version=self.current_version,
                metadata={
                    "job_id": self.training_status["current_job"],
                    "samples": len(samples),
                    "days": days,
                    "ewc_lambda": ewc_lambda,
                    "train_loss": train_result.training_loss,
                    "dataset_id": dataset_id,
                    "validation_metrics": merged_validation_metrics
                    or {"train_loss": train_result.training_loss},
                    "author": author or "learning-engine",
                    "dataset_diagnostics": self.last_dataset_diagnostics,
                    "provenance": provenance,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            # Update metrics
            metrics = {
                "version": self.current_version,
                "samples": len(samples),
                "train_loss": train_result.training_loss,
                "initial_loss": initial_loss,
                "final_loss": final_loss,
                "ewc_lambda": ewc_lambda,
                "dataset_id": dataset_id,
                "dataset_size": len(samples),
                "thresholds": {
                    "min_samples_for_training": self.config.min_samples_for_training,
                    "ewc_lambda": ewc_lambda,
                    "golden_validation": validation_thresholds,
                },
                "decision": decision_context,
                "dataset_diagnostics": self.last_dataset_diagnostics,
                "duration_seconds": train_result.metrics.get("train_runtime", 0),
                "validation_metrics": merged_validation_metrics,
                "provenance": provenance,
            }

            self.training_status["metrics"] = metrics
            self.training_status["last_run"] = {
                "status": "success",
                **metrics,
            }
            self.training_status["last_job"] = self.training_status["current_job"]

            learning_metrics.training_runs_total.labels(
                model=self.config.model_name,
                status="success",
            ).inc()
            learning_metrics.training_duration_seconds.labels(
                model=self.config.model_name,
                version_id=self.current_version,
            ).set(metrics["duration_seconds"])
            learning_metrics.training_samples_total.labels(
                model=self.config.model_name,
                version_id=self.current_version,
            ).set(len(samples))
            learning_metrics.training_loss.labels(
                model=self.config.model_name,
                version_id=self.current_version,
            ).set(final_loss if final_loss is not None else 0.0)
            learning_metrics.ewc_lambda.labels(
                model=self.config.model_name,
                version_id=self.current_version,
            ).set(ewc_lambda)

            self._publish_validation_metrics(
                version_id=self.current_version,
                validation_metrics=merged_validation_metrics,
                golden_validation_report=golden_validation_report,
            )
            learning_metrics.lora_versions_total.labels(
                model=self.config.model_name
            ).set(self._version_to_number(self.current_version))
            learning_metrics.lora_active_version.info(
                {"model": self.config.model_name, "version_id": self.current_version}
            )

            logger.info("=" * 60)
            logger.info("Training Complete!")
            logger.info("=" * 60)
            logger.info("Version: %s", self.current_version)
            logger.info("Train Loss: %.4f", train_result.training_loss)
            logger.info("Duration: %.2fs", metrics["duration_seconds"])
            logger.info(
                "training_run_completed",
                extra={
                    "extra_fields": {
                        "event": "learning_engine.training.completed",
                        "job_id": self.training_status["current_job"],
                        "dataset_id": dataset_id,
                        "dataset_size": len(samples),
                        "initial_loss": initial_loss,
                        "final_loss": final_loss,
                        "duration_seconds": metrics["duration_seconds"],
                        "thresholds": {
                            "min_samples_for_training": self.config.min_samples_for_training,
                            "ewc_lambda": ewc_lambda,
                            "golden_validation": validation_thresholds,
                        },
                        "decision": decision_context,
                    }
                },
            )
            logger.info("=" * 60)

            return {
                "status": "success",
                "version": self.current_version,
                "metrics": metrics,
            }

        except Exception as e:
            logger.error("Training failed: %s", e, exc_info=True)
            learning_metrics.training_runs_total.labels(
                model=self.config.model_name,
                status="failed",
            ).inc()

            self.training_status["last_run"] = {
                "status": "failed",
                "dataset_id": dataset_id,
                "duration_seconds": time.monotonic() - started_at,
                "thresholds": {
                    "min_samples_for_training": self.config.min_samples_for_training,
                    "ewc_lambda": ewc_lambda,
                },
                "decision": "exception",
            }

            logger.error(
                "training_run_failed",
                extra={
                    "extra_fields": {
                        "event": "learning_engine.training.failed",
                        "job_id": self.training_status["current_job"],
                        "dataset_id": dataset_id,
                        "thresholds": {
                            "min_samples_for_training": self.config.min_samples_for_training,
                            "ewc_lambda": ewc_lambda,
                        },
                        "decision": "exception",
                        "error": str(e),
                    }
                },
                exc_info=True,
            )
            return {
                "status": "failed",
                "error": str(e),
            }

        finally:
            self.training_status["is_training"] = False
            self.training_status["current_job"] = None

    def _increment_version(self, version: str) -> str:
        """Increment version string (e.g., v1.0 -> v1.1)."""
        parts = version.replace("v", "").split(".")
        major, minor = int(parts[0]), int(parts[1])
        minor += 1
        if minor >= 10:
            major += 1
            minor = 0
        return f"v{major}.{minor}"

    def train_from_jsonl(
        self,
        dataset_path: str,
        learning_rate: Optional[float] = None,
        epochs: Optional[int] = None,
        batch_size: Optional[int] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Train a base LoRA adapter from a JSONL dataset.

        Args:
            dataset_path: Path to JSONL file with input/output pairs
            learning_rate: Optional learning rate override
            epochs: Optional epoch override
            batch_size: Optional batch size override
            job_id: Optional job identifier

        Returns:
            Training result metadata
        """
        logger.info("=" * 60)
        logger.info("Starting Base LoRA Fine-tuning from JSONL")
        logger.info("=" * 60)

        self.training_status["is_training"] = True
        self.training_status["current_job"] = (
            job_id or f"train_jsonl_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        try:
            if not Path(dataset_path).exists():
                raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

            samples = load_dataset_from_file(dataset_path)
            if not samples:
                raise ValueError("Dataset is empty")

            if self.model is None:
                self.load_base_model()
                self.setup_lora()

            dataset = self.prepare_dataset(samples)

            output_dir = f"./lora_checkpoints/{self.training_status['current_job']}"
            os.makedirs(output_dir, exist_ok=True)
            train_result, _ = self._run_training(
                dataset=dataset,
                output_dir=output_dir,
                learning_rate=learning_rate or self.config.learning_rate,
                epochs=epochs or self.config.num_train_epochs,
                batch_size=batch_size or self.config.batch_size,
            )

            self.current_version = self._increment_version(self.current_version)
            adapter_path = os.path.join(output_dir, "adapter")
            self.model.save_pretrained(adapter_path)

            self.storage.upload_adapter(
                local_path=adapter_path,
                version=self.current_version,
                metadata={
                    "job_id": self.training_status["current_job"],
                    "dataset_path": dataset_path,
                    "samples": len(samples),
                    "learning_rate": learning_rate or self.config.learning_rate,
                    "epochs": epochs or self.config.num_train_epochs,
                    "batch_size": batch_size or self.config.batch_size,
                    "train_loss": train_result.training_loss,
                    "provenance": {
                        "dataset_path": dataset_path,
                        "source_type": "jsonl",
                        "recorded_at": datetime.utcnow().isoformat() + "Z",
                    },
                    "timestamp": datetime.now().isoformat(),
                },
            )

            metrics = {
                "version": self.current_version,
                "samples": len(samples),
                "train_loss": train_result.training_loss,
                "learning_rate": learning_rate or self.config.learning_rate,
                "epochs": epochs or self.config.num_train_epochs,
                "batch_size": batch_size or self.config.batch_size,
                "duration_seconds": train_result.metrics.get("train_runtime", 0),
            }
            self.training_status["metrics"] = metrics
            self.training_status["last_job"] = self.training_status["current_job"]

            return {
                "status": "success",
                "version": self.current_version,
                "metrics": metrics,
            }

        except Exception as e:
            logger.error("JSONL training failed: %s", e, exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
            }
        finally:
            self.training_status["is_training"] = False
            self.training_status["current_job"] = None

    def _run_training(
        self,
        dataset: Dataset,
        output_dir: str,
        learning_rate: float,
        epochs: int,
        batch_size: int,
        fisher_calculator: Optional[FisherInformationCalculator] = None,
        old_params: Optional[Dict[str, torch.Tensor]] = None,
        ewc_lambda: float = 0.0,
    ) -> Tuple[Any, Trainer]:
        """Run training with optional EWC regularization."""
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            learning_rate=learning_rate,
            warmup_steps=self.config.warmup_steps,
            logging_steps=10,
            save_strategy="epoch",
            fp16=True,
            report_to="none",
        )

        if fisher_calculator and old_params:
            run_trainer = EWCTrainer(
                model=self.model,
                args=training_args,
                train_dataset=dataset,
                data_collator=DataCollatorForLanguageModeling(
                    tokenizer=self.tokenizer,
                    mlm=False,
                ),
                fisher_calculator=fisher_calculator,
                old_params=old_params,
                ewc_lambda=ewc_lambda,
            )
        else:
            run_trainer = Trainer(
                model=self.model,
                args=training_args,
                train_dataset=dataset,
                data_collator=DataCollatorForLanguageModeling(
                    tokenizer=self.tokenizer,
                    mlm=False,
                ),
            )

        logger.info("Starting training...")
        train_result = run_trainer.train()
        return train_result, run_trainer

    def get_status(self) -> Dict[str, Any]:
        """Get current training status."""
        return self.training_status

    def get_metrics(self) -> Dict[str, Any]:
        """Get training metrics."""
        return self.training_status.get("metrics", {})


class EWCTrainer(Trainer):
    """Custom Trainer with EWC regularization."""

    def __init__(
        self,
        fisher_calculator: FisherInformationCalculator,
        old_params: Dict[str, torch.Tensor],
        ewc_lambda: float,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fisher_calculator = fisher_calculator
        self.old_params = old_params
        self.ewc_lambda = ewc_lambda

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        """Compute loss with EWC regularization."""
        inputs = dict(inputs)
        inputs.pop("weight", None)

        # Standard loss
        outputs = model(**inputs)
        loss = outputs.loss

        # Add EWC regularization
        if self.fisher_calculator.get_fisher_dict() and self.old_params:
            ewc_loss = self.fisher_calculator.compute_ewc_loss(
                model,
                self.old_params,
                self.ewc_lambda,
            )
            loss = loss + ewc_loss

        return (loss, outputs) if return_outputs else loss
