"""
Fisher Information Matrix Calculator

Calculates the Fisher Information Matrix for EWC regularization.
The FIM approximates the importance of each parameter for the current task.
"""

import os
import logging
import torch
import torch.nn.functional as F
from typing import Dict, Optional, List
from pathlib import Path
import json

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

logger = logging.getLogger(__name__)


class FisherInformationCalculator:
    """
    Calculates Fisher Information Matrix for model parameters.
    
    The FIM diagonal approximation is computed as:
    F_i = E[(∂log p(y|x;θ) / ∂θ_i)^2]
    
    This measures how much each parameter affects the loss on current data.
    """
    
    def __init__(
        self,
        model_name: str,
        base_model_path: Optional[str] = None,
        device: str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        """
        Initialize Fisher calculator.
        
        Args:
            model_name: Name/path of the base model
            base_model_path: Path to base model checkpoint
            device: Device to use for computation
        """
        self.model_name = model_name
        self.base_model_path = base_model_path
        self.device = device
        
        self.model = None
        self.tokenizer = None
        self.fisher_dict: Dict[str, torch.Tensor] = {}
        
        logger.info(f"Fisher calculator initialized for {model_name} on {device}")
    
    def load_model(self, adapter_path: Optional[str] = None):
        """
        Load the model for Fisher calculation.
        
        Args:
            adapter_path: Optional path to LoRA adapter
        """
        logger.info(f"Loading model: {self.model_name}")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        # Load base model
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16,
            device_map=self.device,
            trust_remote_code=True
        )
        
        # Load adapter if provided
        if adapter_path and os.path.exists(adapter_path):
            logger.info(f"Loading LoRA adapter from {adapter_path}")
            self.model = PeftModel.from_pretrained(self.model, adapter_path)
        
        self.model.eval()
        logger.info("✓ Model loaded successfully")
    
    def load_adapter(self, adapter_path: str):
        """Load a LoRA adapter onto the base model"""
        if self.model is None:
            self.load_model(adapter_path)
        else:
            logger.info(f"Loading LoRA adapter from {adapter_path}")
            self.model = PeftModel.from_pretrained(self.model, adapter_path)
            self.model.eval()
    
    def calculate_fim(
        self,
        dataset: List[Dict[str, str]],
        num_samples: Optional[int] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Calculate Fisher Information Matrix diagonal.
        
        Args:
            dataset: List of training samples with 'input' and 'output' keys
            num_samples: Number of samples to use (None = use all)
        
        Returns:
            Dictionary mapping parameter names to Fisher values
        """
        if self.model is None:
            self.load_model()
        
        logger.info("Calculating Fisher Information Matrix...")
        
        # Limit samples if specified
        if num_samples and num_samples < len(dataset):
            dataset = dataset[:num_samples]
        
        logger.info(f"Using {len(dataset)} samples for FIM calculation")
        
        # Initialize Fisher dict
        fisher_dict = {}
        for name, param in self.model.named_parameters():
            if param.requires_grad:
                fisher_dict[name] = torch.zeros_like(param.data)
        
        # Calculate Fisher for each sample
        self.model.eval()
        for idx, sample in enumerate(dataset):
            if idx % 100 == 0:
                logger.info(f"Processing sample {idx}/{len(dataset)}")
            
            # Prepare input
            text = f"{sample['input']}\n{sample['output']}"
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=2048
            ).to(self.device)
            
            # Forward pass
            outputs = self.model(**inputs, labels=inputs["input_ids"])
            loss = outputs.loss
            
            # Backward pass to get gradients
            self.model.zero_grad()
            loss.backward()
            
            # Accumulate squared gradients (Fisher diagonal approximation)
            for name, param in self.model.named_parameters():
                if param.requires_grad and param.grad is not None:
                    fisher_dict[name] += param.grad.data ** 2
        
        # Average over samples
        for name in fisher_dict:
            fisher_dict[name] /= len(dataset)
        
        self.fisher_dict = fisher_dict
        logger.info("✓ Fisher Information Matrix calculated")
        
        return fisher_dict
    
    def save_fisher(self, output_path: str, metadata: Optional[Dict] = None):
        """
        Save Fisher Information Matrix to disk.
        
        Args:
            output_path: Path to save Fisher matrix
            metadata: Optional metadata to save alongside Fisher matrix
        """
        logger.info(f"Saving Fisher matrix to {output_path}")
        
        # Create directory if needed
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Save Fisher values
        torch.save(self.fisher_dict, output_path)
        
        # Save metadata
        if metadata:
            metadata_path = output_path.replace(".pt", "_metadata.json")
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)
        
        # Calculate statistics
        total_params = sum(v.numel() for v in self.fisher_dict.values())
        mean_fisher = sum(v.sum().item() for v in self.fisher_dict.values()) / total_params
        
        logger.info(f"✓ Fisher matrix saved")
        logger.info(f"  Total parameters: {total_params:,}")
        logger.info(f"  Mean Fisher value: {mean_fisher:.6f}")
    
    def load_fisher(self, fisher_path: str) -> Dict[str, torch.Tensor]:
        """
        Load Fisher Information Matrix from disk.
        
        Args:
            fisher_path: Path to Fisher matrix file
        
        Returns:
            Dictionary mapping parameter names to Fisher values
        """
        logger.info(f"Loading Fisher matrix from {fisher_path}")
        
        self.fisher_dict = torch.load(fisher_path, map_location=self.device)
        
        logger.info(f"✓ Fisher matrix loaded with {len(self.fisher_dict)} parameters")
        return self.fisher_dict
    
    def calculate_and_save(
        self,
        dataset: Optional[List[Dict[str, str]]] = None,
        num_samples: int = 1000,
        version: str = "latest",
        output_dir: str = "./fisher_matrices"
    ):
        """
        Calculate and save Fisher matrix (convenience method).
        
        Args:
            dataset: Training dataset (if None, loads from feedback)
            num_samples: Number of samples to use
            version: Version identifier
            output_dir: Output directory for Fisher matrices
        """
        # Load dataset if not provided
        if dataset is None:
            from .data_loader import load_feedback_dataset
            dataset = load_feedback_dataset(days=7)
        
        # Calculate Fisher
        self.calculate_fim(dataset, num_samples=num_samples)
        
        # Save Fisher matrix
        output_path = os.path.join(output_dir, f"fisher_{version}.pt")
        metadata = {
            "version": version,
            "num_samples": len(dataset) if num_samples is None else min(num_samples, len(dataset)),
            "model_name": self.model_name,
            "timestamp": torch.cuda.Event(enable_timing=False).elapsed_time(torch.cuda.Event(enable_timing=False))
        }
        
        self.save_fisher(output_path, metadata)
        
        return output_path
    
    def get_fisher_dict(self) -> Dict[str, torch.Tensor]:
        """Get the current Fisher dictionary"""
        return self.fisher_dict
    
    def compute_ewc_loss(
        self,
        model: torch.nn.Module,
        old_params: Dict[str, torch.Tensor],
        ewc_lambda: float = 500.0
    ) -> torch.Tensor:
        """
        Compute EWC regularization loss.
        
        Loss = λ/2 * Σ F_i * (θ_i - θ*_i)^2
        
        Args:
            model: Model being fine-tuned
            old_params: Parameters from previous task
            ewc_lambda: EWC regularization strength
        
        Returns:
            EWC loss tensor
        """
        if not self.fisher_dict:
            logger.warning("Fisher matrix not calculated, returning zero loss")
            return torch.tensor(0.0, device=self.device)
        
        try:
            first_param = next(model.parameters())
            loss = torch.tensor(0.0, device=first_param.device)
        except StopIteration:
            return torch.tensor(0.0, device=self.device)

        for name, param in model.named_parameters():
            if param.requires_grad and name in self.fisher_dict and name in old_params:
                fisher = self.fisher_dict[name].to(param.device)
                old_param = old_params[name].to(param.device)
                loss = loss + (fisher * (param - old_param) ** 2).sum()

        return (ewc_lambda / 2) * loss
