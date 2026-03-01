"""
MAML (Model-Agnostic Meta-Learning) Implementation

Implements MAML algorithm for fast adaptation across projects/tasks:
- Inner loop: Task-specific adaptation (few-shot learning)
- Outer loop: Meta-optimization across all tasks
- Goal: Learn meta-weights that enable fast adaptation (<10 steps to 80% accuracy)
"""

import os
import logging
import torch
import torch.nn as nn
import torch.optim as optim
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import json
from collections import defaultdict

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    get_linear_schedule_with_warmup
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType
)

logger = logging.getLogger(__name__)


class MAMLLearner:
    """
    MAML meta-learner for fast adaptation across projects/tasks.
    
    The algorithm works in two loops:
    1. Inner loop: Adapt to specific task using few gradient steps
    2. Outer loop: Update meta-parameters to minimize loss after inner adaptation
    
    This enables the model to quickly adapt to new tasks/projects with minimal data.
    """
    
    def __init__(
        self,
        model_name: str,
        config: Any,
        device: str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        """
        Initialize MAML learner.
        
        Args:
            model_name: Base model name/path
            config: Configuration object
            device: Device for computation
        """
        self.model_name = model_name
        self.config = config
        self.device = device
        
        # MAML hyperparameters
        self.inner_lr = getattr(config, 'maml_inner_lr', 1e-3)
        self.outer_lr = getattr(config, 'maml_outer_lr', 1e-4)
        self.num_inner_steps = getattr(config, 'maml_inner_steps', 5)
        self.num_outer_steps = getattr(config, 'maml_outer_steps', 100)
        self.inner_batch_size = getattr(config, 'maml_inner_batch_size', 4)
        self.outer_batch_size = getattr(config, 'maml_outer_batch_size', 2)  # Tasks per meta-batch
        
        # Adaptation target
        self.target_accuracy = getattr(config, 'maml_target_accuracy', 0.80)
        self.max_adaptation_steps = getattr(config, 'maml_max_adaptation_steps', 10)
        
        # Model components
        self.meta_model = None
        self.tokenizer = None
        self.meta_optimizer = None
        
        # Meta-learning state
        self.meta_weights = None
        self.task_embeddings = {}
        self.adaptation_history = []
        
        logger.info(f"MAML learner initialized: inner_lr={self.inner_lr}, outer_lr={self.outer_lr}")
        logger.info(f"Target: {self.target_accuracy*100}% accuracy in <{self.max_adaptation_steps} steps")
    
    def initialize_model(self):
        """Initialize the base model with LoRA for MAML"""
        logger.info(f"Initializing meta-model: {self.model_name}")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        # Load base model
        self.meta_model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16,
            device_map=self.device,
            trust_remote_code=True
        )
        
        # Prepare for training
        self.meta_model = prepare_model_for_kbit_training(self.meta_model)
        
        # Apply LoRA configuration
        lora_config = LoraConfig(
            r=self.config.lora_rank,
            lora_alpha=self.config.lora_alpha,
            target_modules=self.config.target_modules,
            lora_dropout=self.config.lora_dropout,
            bias="none",
            task_type=TaskType.CAUSAL_LM
        )
        
        self.meta_model = get_peft_model(self.meta_model, lora_config)
        self.meta_model.print_trainable_parameters()
        
        # Initialize meta-optimizer
        self.meta_optimizer = optim.Adam(
            self.meta_model.parameters(),
            lr=self.outer_lr
        )
        
        # Store initial meta-weights
        self.meta_weights = {
            name: param.data.clone()
            for name, param in self.meta_model.named_parameters()
            if param.requires_grad
        }
        
        logger.info("✓ Meta-model initialized")
    
    def inner_loop(
        self,
        task_data: List[Dict[str, str]],
        num_steps: Optional[int] = None
    ) -> Tuple[nn.Module, float, List[float]]:
        """
        Inner loop: Adapt meta-model to specific task.
        
        Args:
            task_data: Training samples for this task
            num_steps: Number of gradient steps (uses self.num_inner_steps if None)
        
        Returns:
            Tuple of (adapted_model, final_loss, loss_history)
        """
        if num_steps is None:
            num_steps = self.num_inner_steps
        
        # Clone model with meta-weights
        adapted_model = self._clone_model()
        
        # Create task-specific optimizer
        inner_optimizer = optim.SGD(
            [p for p in adapted_model.parameters() if p.requires_grad],
            lr=self.inner_lr
        )
        
        loss_history = []
        
        # Adaptation steps
        for step in range(num_steps):
            # Sample batch
            batch = self._sample_batch(task_data, self.inner_batch_size)
            
            # Forward pass
            inputs = self._prepare_inputs(batch)
            outputs = adapted_model(**inputs)
            loss = outputs.loss
            
            # Backward pass
            inner_optimizer.zero_grad()
            loss.backward()
            inner_optimizer.step()
            
            loss_history.append(loss.item())
        
        final_loss = loss_history[-1] if loss_history else float('inf')
        
        return adapted_model, final_loss, loss_history
    
    def outer_loop(
        self,
        task_batches: List[List[Dict[str, str]]],
        num_steps: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Outer loop: Meta-optimization across tasks.
        
        Args:
            task_batches: List of task datasets
            num_steps: Number of meta-optimization steps
        
        Returns:
            Training metrics dictionary
        """
        if num_steps is None:
            num_steps = self.num_outer_steps
        
        logger.info("=" * 60)
        logger.info("Starting MAML Meta-Training")
        logger.info("=" * 60)
        logger.info(f"Tasks: {len(task_batches)}")
        logger.info(f"Outer steps: {num_steps}")
        logger.info(f"Inner steps per task: {self.num_inner_steps}")
        
        meta_losses = []
        task_accuracies = []
        
        for outer_step in range(num_steps):
            # Sample batch of tasks
            task_batch = self._sample_tasks(task_batches, self.outer_batch_size)
            
            meta_gradients = defaultdict(lambda: torch.zeros_like(
                next(iter(self.meta_weights.values()))
            ))
            batch_loss = 0.0
            
            for task_data in task_batch:
                # Use precomputed support/query splits when provided (project tasks),
                # otherwise build an ephemeral split for raw task datasets.
                support_set, query_set = self._resolve_task_split(task_data)
                
                # Inner loop: Adapt to task
                adapted_model, _, _ = self.inner_loop(support_set)
                
                # Evaluate on query set
                query_loss, query_acc = self._evaluate_task(adapted_model, query_set)
                batch_loss += query_loss
                task_accuracies.append(query_acc)
                
                # Compute meta-gradients (gradients of query loss w.r.t. meta-parameters)
                for name, param in adapted_model.named_parameters():
                    if param.requires_grad and param.grad is not None:
                        if name in meta_gradients:
                            meta_gradients[name] += param.grad.data
            
            # Average gradients across task batch
            avg_loss = batch_loss / len(task_batch)
            meta_losses.append(avg_loss)
            
            for name in meta_gradients:
                meta_gradients[name] /= len(task_batch)
            
            # Meta-update
            self.meta_optimizer.zero_grad()
            for name, param in self.meta_model.named_parameters():
                if name in meta_gradients:
                    param.grad = meta_gradients[name]
            
            self.meta_optimizer.step()
            
            # Update stored meta-weights
            for name, param in self.meta_model.named_parameters():
                if param.requires_grad:
                    self.meta_weights[name] = param.data.clone()
            
            # Logging
            if outer_step % 10 == 0:
                avg_acc = sum(task_accuracies[-len(task_batch):]) / len(task_batch)
                logger.info(
                    f"Step {outer_step}/{num_steps} | "
                    f"Meta Loss: {avg_loss:.4f} | "
                    f"Avg Task Acc: {avg_acc:.2%}"
                )
        
        logger.info("=" * 60)
        logger.info("Meta-Training Complete")
        logger.info("=" * 60)
        
        return {
            "meta_losses": meta_losses,
            "task_accuracies": task_accuracies,
            "final_meta_loss": meta_losses[-1] if meta_losses else 0.0,
            "mean_task_accuracy": sum(task_accuracies) / len(task_accuracies) if task_accuracies else 0.0
        }
    
    def adapt_to_task(
        self,
        task_data: List[Dict[str, str]],
        target_accuracy: Optional[float] = None,
        max_steps: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Fast adaptation to a new task using meta-learned weights.
        
        Args:
            task_data: Training samples for the new task
            target_accuracy: Target accuracy to achieve (default: self.target_accuracy)
            max_steps: Maximum adaptation steps (default: self.max_adaptation_steps)
        
        Returns:
            Adaptation metrics dictionary
        """
        if target_accuracy is None:
            target_accuracy = self.target_accuracy
        if max_steps is None:
            max_steps = self.max_adaptation_steps
        
        logger.info(f"Fast adaptation: target {target_accuracy:.0%} in <{max_steps} steps")
        
        # Split data
        support_set, query_set = self._split_support_query(task_data, support_ratio=0.7)
        
        # Track adaptation progress
        adaptation_metrics = {
            "steps": [],
            "losses": [],
            "accuracies": [],
            "target_reached": False,
            "steps_to_target": None
        }
        
        # Initialize from meta-weights
        adapted_model = self._clone_model()
        inner_optimizer = optim.SGD(
            [p for p in adapted_model.parameters() if p.requires_grad],
            lr=self.inner_lr
        )
        
        # Adaptive learning
        for step in range(max_steps):
            # Training step
            batch = self._sample_batch(support_set, self.inner_batch_size)
            inputs = self._prepare_inputs(batch)
            outputs = adapted_model(**inputs)
            loss = outputs.loss
            
            inner_optimizer.zero_grad()
            loss.backward()
            inner_optimizer.step()
            
            # Evaluate on query set
            query_loss, query_acc = self._evaluate_task(adapted_model, query_set)
            
            adaptation_metrics["steps"].append(step + 1)
            adaptation_metrics["losses"].append(query_loss)
            adaptation_metrics["accuracies"].append(query_acc)
            
            logger.info(f"  Step {step+1}/{max_steps}: Loss={query_loss:.4f}, Acc={query_acc:.2%}")
            
            # Check if target reached
            if query_acc >= target_accuracy and not adaptation_metrics["target_reached"]:
                adaptation_metrics["target_reached"] = True
                adaptation_metrics["steps_to_target"] = step + 1
                logger.info(f"✓ Target accuracy {target_accuracy:.0%} reached in {step+1} steps!")
                break
        
        # Final metrics
        adaptation_metrics["final_accuracy"] = adaptation_metrics["accuracies"][-1]
        adaptation_metrics["final_loss"] = adaptation_metrics["losses"][-1]
        
        if not adaptation_metrics["target_reached"]:
            logger.warning(
                f"Target accuracy not reached. Best: {max(adaptation_metrics['accuracies']):.2%} "
                f"at step {adaptation_metrics['accuracies'].index(max(adaptation_metrics['accuracies'])) + 1}"
            )
        
        # Store in history
        self.adaptation_history.append({
            "timestamp": datetime.now().isoformat(),
            "metrics": adaptation_metrics
        })
        
        return adaptation_metrics
    
    def _clone_model(self) -> nn.Module:
        """Clone the meta-model with current meta-weights"""
        # Create a fresh copy
        cloned_model = type(self.meta_model)(self.meta_model.config)
        cloned_model.load_state_dict(self.meta_model.state_dict())
        cloned_model.to(self.device)
        cloned_model.train()
        return cloned_model
    
    def _sample_batch(
        self,
        data: List[Dict[str, str]],
        batch_size: int
    ) -> List[Dict[str, str]]:
        """Sample a batch from data"""
        import random
        return random.sample(data, min(batch_size, len(data)))
    
    def _sample_tasks(
        self,
        task_batches: List[List[Dict[str, str]]],
        num_tasks: int
    ) -> List[List[Dict[str, str]]]:
        """Sample a batch of tasks"""
        import random
        return random.sample(task_batches, min(num_tasks, len(task_batches)))

    def _resolve_task_split(
        self,
        task_data: Any,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """Return support/query sets from either pre-split task descriptors or raw samples."""
        if isinstance(task_data, dict) and "support_set" in task_data and "query_set" in task_data:
            support_set = task_data.get("support_set") or []
            query_set = task_data.get("query_set") or []
            if support_set and query_set:
                return support_set, query_set

            interactions = task_data.get("interactions") or []
            return self._split_support_query(interactions)

        return self._split_support_query(task_data)
    
    def _split_support_query(
        self,
        data: List[Dict[str, str]],
        support_ratio: float = 0.8
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """Split data into support and query sets"""
        import random
        shuffled = data.copy()
        random.shuffle(shuffled)
        
        split_idx = int(len(shuffled) * support_ratio)
        support = shuffled[:split_idx]
        query = shuffled[split_idx:]
        
        return support, query
    
    def _prepare_inputs(self, batch: List[Dict[str, str]]) -> Dict[str, torch.Tensor]:
        """Prepare batch for model input"""
        texts = []
        for sample in batch:
            text = f"{sample['input']}\n{sample['output']}{self.tokenizer.eos_token}"
            texts.append(text)
        
        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.config.max_seq_length,
            return_tensors="pt"
        ).to(self.device)
        
        inputs["labels"] = inputs["input_ids"].clone()
        
        return inputs
    
    def _evaluate_task(
        self,
        model: nn.Module,
        query_set: List[Dict[str, str]]
    ) -> Tuple[float, float]:
        """
        Evaluate model on query set.
        
        Returns:
            Tuple of (loss, accuracy)
        """
        model.eval()
        
        with torch.no_grad():
            inputs = self._prepare_inputs(query_set)
            outputs = model(**inputs)
            loss = outputs.loss.item()
            
            # Calculate accuracy (simplified: correct token predictions)
            logits = outputs.logits
            predictions = torch.argmax(logits, dim=-1)
            labels = inputs["labels"]
            
            # Mask padding tokens
            mask = labels != self.tokenizer.pad_token_id
            correct = (predictions == labels) & mask
            accuracy = correct.sum().item() / mask.sum().item()
        
        model.train()
        
        return loss, accuracy
    
    def get_meta_weights(self) -> Dict[str, torch.Tensor]:
        """Get current meta-weights"""
        return self.meta_weights
    
    def load_meta_weights(self, weights: Dict[str, torch.Tensor]):
        """Load meta-weights into model"""
        logger.info("Loading meta-weights...")
        
        for name, param in self.meta_model.named_parameters():
            if name in weights:
                param.data = weights[name].to(self.device)
        
        self.meta_weights = weights
        logger.info("✓ Meta-weights loaded")
    
    def get_adaptation_history(self) -> List[Dict[str, Any]]:
        """Get adaptation history"""
        return self.adaptation_history
    
    def save_checkpoint(self, path: str, metadata: Optional[Dict] = None):
        """Save MAML checkpoint"""
        logger.info(f"Saving MAML checkpoint to {path}")
        
        checkpoint = {
            "meta_weights": self.meta_weights,
            "task_embeddings": self.task_embeddings,
            "adaptation_history": self.adaptation_history,
            "config": {
                "inner_lr": self.inner_lr,
                "outer_lr": self.outer_lr,
                "num_inner_steps": self.num_inner_steps,
                "num_outer_steps": self.num_outer_steps,
                "target_accuracy": self.target_accuracy,
                "max_adaptation_steps": self.max_adaptation_steps
            },
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        }
        
        torch.save(checkpoint, path)
        logger.info("✓ Checkpoint saved")
    
    def load_checkpoint(self, path: str):
        """Load MAML checkpoint"""
        logger.info(f"Loading MAML checkpoint from {path}")
        
        checkpoint = torch.load(path, map_location=self.device)
        
        self.meta_weights = checkpoint["meta_weights"]
        self.task_embeddings = checkpoint.get("task_embeddings", {})
        self.adaptation_history = checkpoint.get("adaptation_history", [])
        
        # Load weights into model if initialized
        if self.meta_model is not None:
            self.load_meta_weights(self.meta_weights)
        
        logger.info("✓ Checkpoint loaded")
        logger.info(f"  Timestamp: {checkpoint.get('timestamp', 'unknown')}")
        logger.info(f"  Tasks learned: {len(self.task_embeddings)}")
