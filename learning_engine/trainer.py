"""
LoRA Trainer with EWC Regularization

Implements fine-tuning with:
- LoRA rank-16 adapters
- EWC regularization to prevent catastrophic forgetting
- Feedback-based training data loading
- Adapter versioning and storage
"""

import os
import logging
import torch
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
from pathlib import Path
from collections import Counter

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType
)
from datasets import Dataset
import psycopg2

from .fisher import FisherInformationCalculator
from .storage import AdapterStorage

logger = logging.getLogger(__name__)


class LoRATrainer:
    """
    LoRA trainer with EWC regularization for continuous learning.
    """
    
    def __init__(
        self,
        config: Any,
        storage: AdapterStorage,
        fisher_calculator: FisherInformationCalculator
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
        
        self.model = None
        self.tokenizer = None
        self.current_version = "v1.0"
        self.training_status = {
            "is_training": False,
            "current_job": None,
            "last_job": None,
            "metrics": {}
        }
        self.last_dataset_diagnostics: Dict[str, Any] = {}
        
        logger.info("LoRA Trainer initialized")
    
    def load_base_model(self):
        """Load the base model for fine-tuning"""
        logger.info(f"Loading base model: {self.config.model_name}")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        # Load model with quantization
        self.model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        
        # Prepare for training
        self.model = prepare_model_for_kbit_training(self.model)
        
        logger.info("✓ Base model loaded")
    
    def setup_lora(self) -> None:
        """Setup LoRA configuration and apply to model"""
        logger.info("Setting up LoRA configuration...")
        
        lora_config = LoraConfig(
            r=self.config.lora_rank,
            lora_alpha=self.config.lora_alpha,
            target_modules=self.config.target_modules,
            lora_dropout=self.config.lora_dropout,
            bias="none",
            task_type=TaskType.CAUSAL_LM
        )
        
        self.model = get_peft_model(self.model, lora_config)
        self.model.print_trainable_parameters()
        
        logger.info("✓ LoRA configuration applied")
    
    def load_feedback_data(
        self,
        days: int = 7
    ) -> List[Dict[str, str]]:
        """
        Load training data from feedback database.
        
        Args:
            days: Number of days to look back
        
        Returns:
            List of training samples
        """
        logger.info(f"Loading feedback data from last {days} days...")
        
        conn = psycopg2.connect(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            dbname=self.config.postgres_db,
            user=self.config.postgres_user,
            password=self.config.postgres_password
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
        WHERE created_at >= NOW() - INTERVAL '%s days'
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
            request_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            response_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            feedback_type = row[2]
            feedback_distribution[feedback_type] += 1
            
            # Extract messages
            messages = request_data.get('messages', [])
            assistant_response = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')

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
            weight = 2.0 if feedback_type == 'thumbs_up' else 0.5
            
            samples.append({
                'input': input_text,
                'output': str(output_text).strip(),
                'weight': weight,
                'feedback_type': feedback_type
            })
        
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

        logger.info(f"✓ Loaded {len(samples)} training samples (from {len(rows)} raw examples)")
        logger.info("Dataset diagnostics: %s", self.last_dataset_diagnostics)

        # Log weighted feedback summary for kept samples
        positive = sum(1 for s in samples if s['feedback_type'] == 'thumbs_up')
        negative = len(samples) - positive
        logger.info(f"  Positive samples kept: {positive} (2.0x weight)")
        logger.info(f"  Negative samples kept: {negative} (0.5x weight)")
        
        return samples
    
    def _format_messages(self, messages: List[Dict]) -> str:
        """Format messages for training"""
        formatted = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = str(msg.get('content', '')).strip()
            if not content:
                continue
            formatted.append(f"{role}: {content}")
        return "\n".join(formatted)

    def _extract_intent(self, request_data: Dict[str, Any], response_data: Dict[str, Any]) -> str:
        """Best-effort intent extraction for diagnostics."""
        candidates = [
            request_data.get("intent"),
            request_data.get("metadata", {}).get("intent") if isinstance(request_data.get("metadata"), dict) else None,
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

    def _extract_project(self, request_data: Dict[str, Any], response_data: Dict[str, Any]) -> str:
        """Best-effort project extraction for diagnostics."""
        metadata = request_data.get("metadata") if isinstance(request_data.get("metadata"), dict) else {}
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
        samples: List[Dict[str, str]]
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
        texts = []
        weights = []
        
        for sample in samples:
            text = f"{sample['input']}\n{sample['output']}{self.tokenizer.eos_token}"
            texts.append(text)
            weights.append(sample['weight'])
        
        # Tokenize
        tokenized = self.tokenizer(
            texts,
            truncation=True,
            max_length=self.config.max_seq_length,
            padding="max_length",
            return_tensors="pt"
        )
        
        # Create dataset
        dataset_dict = {
            "input_ids": tokenized["input_ids"],
            "attention_mask": tokenized["attention_mask"],
            "labels": tokenized["input_ids"].clone(),
            "weight": torch.tensor(weights, dtype=torch.float)
        }
        
        dataset = Dataset.from_dict(dataset_dict)
        
        logger.info(f"✓ Dataset prepared with {len(dataset)} samples")
        return dataset
    
    def train_from_feedback(
        self,
        days: int = 7,
        ewc_lambda: float = 500.0,
        force: bool = False,
        job_id: Optional[str] = None
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
        
        # Update status
        self.training_status["is_training"] = True
        self.training_status["current_job"] = job_id or f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # Load feedback data
            samples = self.load_feedback_data(days=days)
            
            # Check minimum samples
            if len(samples) < self.config.min_samples_for_training and not force:
                msg = f"Not enough samples ({len(samples)} < {self.config.min_samples_for_training})"
                logger.warning(msg)
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
            old_params = {}
            for name, param in self.model.named_parameters():
                if param.requires_grad:
                    old_params[name] = param.data.clone()
            
            # Calculate Fisher matrix if not exists
            if not self.fisher_calculator.get_fisher_dict():
                logger.info("Calculating Fisher Information Matrix...")
                self.fisher_calculator.calculate_fim(samples, num_samples=1000)
            
            # Prepare dataset
            dataset = self.prepare_dataset(samples)
            
            # Training arguments
            output_dir = f"./lora_checkpoints/{self.training_status['current_job']}"
            training_args = TrainingArguments(
                output_dir=output_dir,
                num_train_epochs=self.config.num_train_epochs,
                per_device_train_batch_size=self.config.batch_size,
                gradient_accumulation_steps=self.config.gradient_accumulation_steps,
                learning_rate=self.config.learning_rate,
                warmup_steps=self.config.warmup_steps,
                logging_steps=10,
                save_strategy="epoch",
                fp16=True,
                report_to="none"
            )
            
            # Custom trainer with EWC
            trainer = EWCTrainer(
                model=self.model,
                args=training_args,
                train_dataset=dataset,
                data_collator=DataCollatorForLanguageModeling(
                    tokenizer=self.tokenizer,
                    mlm=False
                ),
                fisher_calculator=self.fisher_calculator,
                old_params=old_params,
                ewc_lambda=ewc_lambda
            )
            
            # Train
            logger.info("Starting training...")
            train_result = trainer.train()
            
            # Generate new version
            self.current_version = self._increment_version(self.current_version)
            
            # Save adapter
            adapter_path = os.path.join(output_dir, "adapter")
            self.model.save_pretrained(adapter_path)
            
            # Upload to MinIO
            logger.info(f"Uploading adapter version {self.current_version}...")
            self.storage.upload_adapter(
                local_path=adapter_path,
                version=self.current_version,
                metadata={
                    "job_id": self.training_status['current_job'],
                    "samples": len(samples),
                    "days": days,
                    "ewc_lambda": ewc_lambda,
                    "train_loss": train_result.training_loss,
                    "dataset_diagnostics": self.last_dataset_diagnostics,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Update metrics
            metrics = {
                "version": self.current_version,
                "samples": len(samples),
                "train_loss": train_result.training_loss,
                "ewc_lambda": ewc_lambda,
                "dataset_diagnostics": self.last_dataset_diagnostics,
                "duration_seconds": train_result.metrics.get('train_runtime', 0)
            }
            
            self.training_status["metrics"] = metrics
            self.training_status["last_job"] = self.training_status["current_job"]
            
            logger.info("=" * 60)
            logger.info("Training Complete!")
            logger.info("=" * 60)
            logger.info(f"Version: {self.current_version}")
            logger.info(f"Train Loss: {train_result.training_loss:.4f}")
            logger.info(f"Duration: {metrics['duration_seconds']:.2f}s")
            logger.info("=" * 60)
            
            return {
                "status": "success",
                "version": self.current_version,
                "metrics": metrics
            }
            
        except Exception as e:
            logger.error(f"Training failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e)
            }
        
        finally:
            self.training_status["is_training"] = False
            self.training_status["current_job"] = None
    
    def _increment_version(self, version: str) -> str:
        """Increment version string (e.g., v1.0 -> v1.1)"""
        parts = version.replace('v', '').split('.')
        major, minor = int(parts[0]), int(parts[1])
        minor += 1
        if minor >= 10:
            major += 1
            minor = 0
        return f"v{major}.{minor}"
    
    def get_status(self) -> Dict[str, Any]:
        """Get current training status"""
        return self.training_status
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get training metrics"""
        return self.training_status.get("metrics", {})


class EWCTrainer(Trainer):
    """Custom Trainer with EWC regularization"""
    
    def __init__(
        self,
        fisher_calculator: FisherInformationCalculator,
        old_params: Dict[str, torch.Tensor],
        ewc_lambda: float,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.fisher_calculator = fisher_calculator
        self.old_params = old_params
        self.ewc_lambda = ewc_lambda
    
    def compute_loss(self, model, inputs, return_outputs=False):
        """Compute loss with EWC regularization"""
        # Standard loss
        outputs = model(**inputs)
        loss = outputs.loss
        
        # Add EWC regularization
        if self.fisher_calculator.get_fisher_dict() and self.old_params:
            ewc_loss = self.fisher_calculator.compute_ewc_loss(
                self.old_params,
                self.ewc_lambda
            )
            loss = loss + ewc_loss
        
        return (loss, outputs) if return_outputs else loss
