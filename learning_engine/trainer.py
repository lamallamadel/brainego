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
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
from pathlib import Path

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
from . import metrics as learning_metrics

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
            "metrics": {},
            "last_run": {}
        }
        
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
        
        # Process samples with weights
        samples = []
        for row in rows:
            request_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            response_data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            feedback_type = row[2]
            
            # Extract messages
            messages = request_data.get('messages', [])
            assistant_response = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            # Format as training sample
            input_text = self._format_messages(messages)
            output_text = assistant_response
            
            # Apply weights based on feedback
            weight = 2.0 if feedback_type == 'thumbs_up' else 0.5
            
            samples.append({
                'input': input_text,
                'output': output_text,
                'weight': weight,
                'feedback_type': feedback_type
            })
        
        cursor.close()
        conn.close()
        
        logger.info(f"✓ Loaded {len(samples)} training samples")
        
        # Log statistics
        positive = sum(1 for s in samples if s['feedback_type'] == 'thumbs_up')
        negative = len(samples) - positive
        logger.info(f"  Positive samples: {positive} (2.0x weight)")
        logger.info(f"  Negative samples: {negative} (0.5x weight)")
        
        return samples
    
    def _format_messages(self, messages: List[Dict]) -> str:
        """Format messages for training"""
        formatted = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            formatted.append(f"{role}: {content}")
        return "\n".join(formatted)
    
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

        started_at = time.monotonic()
        
        # Update status
        self.training_status["is_training"] = True
        self.training_status["current_job"] = job_id or f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        dataset_id = f"feedback_{days}d_{self.training_status['current_job']}"

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
                        "ewc_lambda_max": getattr(self.config, "ewc_lambda_max", None)
                    },
                    "decision": "evaluate"
                }
            }
        )
        
        try:
            # Load feedback data
            samples = self.load_feedback_data(days=days)

            decision_context = {
                "force": force,
                "enough_samples": len(samples) >= self.config.min_samples_for_training,
                "train": force or len(samples) >= self.config.min_samples_for_training
            }
            
            # Check minimum samples
            if len(samples) < self.config.min_samples_for_training and not force:
                msg = f"Not enough samples ({len(samples)} < {self.config.min_samples_for_training})"
                logger.warning(msg)
                learning_metrics.training_runs_total.labels(
                    model=self.config.model_name,
                    status="skipped"
                ).inc()

                self.training_status["last_run"] = {
                    "status": "skipped",
                    "dataset_id": dataset_id,
                    "dataset_size": len(samples),
                    "duration_seconds": time.monotonic() - started_at,
                    "thresholds": {
                        "min_samples_for_training": self.config.min_samples_for_training,
                        "ewc_lambda": ewc_lambda
                    },
                    "decision": decision_context
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
                                "ewc_lambda": ewc_lambda
                            },
                            "decision": decision_context
                        }
                    }
                )
                return {
                    "status": "skipped",
                    "message": msg,
                    "samples": len(samples)
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

            loss_history = [entry.get("loss") for entry in trainer.state.log_history if "loss" in entry]
            initial_loss = loss_history[0] if loss_history else None
            final_loss = loss_history[-1] if loss_history else train_result.training_loss
            
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
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Update metrics
            metrics = {
                "version": self.current_version,
                "samples": len(samples),
                "train_loss": train_result.training_loss,
                "initial_loss": initial_loss,
                "final_loss": final_loss,
                "ewc_lambda": ewc_lambda,
                "duration_seconds": train_result.metrics.get('train_runtime', 0),
                "dataset_id": dataset_id,
                "dataset_size": len(samples),
                "thresholds": {
                    "min_samples_for_training": self.config.min_samples_for_training,
                    "ewc_lambda": ewc_lambda
                },
                "decision": decision_context
            }
            
            self.training_status["metrics"] = metrics
            self.training_status["last_run"] = {
                "status": "success",
                **metrics
            }
            self.training_status["last_job"] = self.training_status["current_job"]

            learning_metrics.training_runs_total.labels(
                model=self.config.model_name,
                status="success"
            ).inc()
            learning_metrics.training_duration_seconds.labels(
                model=self.config.model_name,
                version_id=self.current_version
            ).set(metrics["duration_seconds"])
            learning_metrics.training_samples_total.labels(
                model=self.config.model_name,
                version_id=self.current_version
            ).set(len(samples))
            learning_metrics.training_loss.labels(
                model=self.config.model_name,
                version_id=self.current_version
            ).set(final_loss if final_loss is not None else 0.0)
            learning_metrics.ewc_lambda.labels(
                model=self.config.model_name,
                version_id=self.current_version
            ).set(ewc_lambda)
            
            logger.info("=" * 60)
            logger.info("Training Complete!")
            logger.info("=" * 60)
            logger.info(f"Version: {self.current_version}")
            logger.info(f"Train Loss: {train_result.training_loss:.4f}")
            logger.info(f"Duration: {metrics['duration_seconds']:.2f}s")
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
                            "ewc_lambda": ewc_lambda
                        },
                        "decision": decision_context
                    }
                }
            )
            logger.info("=" * 60)
            
            return {
                "status": "success",
                "version": self.current_version,
                "metrics": metrics
            }
            
        except Exception as e:
            logger.error(f"Training failed: {e}", exc_info=True)
            learning_metrics.training_runs_total.labels(
                model=self.config.model_name,
                status="failed"
            ).inc()

            self.training_status["last_run"] = {
                "status": "failed",
                "dataset_id": dataset_id,
                "duration_seconds": time.monotonic() - started_at,
                "thresholds": {
                    "min_samples_for_training": self.config.min_samples_for_training,
                    "ewc_lambda": ewc_lambda
                },
                "decision": "exception"
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
                            "ewc_lambda": ewc_lambda
                        },
                        "decision": "exception",
                        "error": str(e)
                    }
                },
                exc_info=True
            )
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
