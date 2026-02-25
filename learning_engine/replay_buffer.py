"""
Weighted Replay Buffer for Failed Plans

Implements a replay buffer with 3x weight multiplier for failed plans to help
the model learn from mistakes and improve on difficult tasks.
"""

import logging
import random
from typing import List, Dict, Optional, Any
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)


class WeightedReplayBuffer:
    """
    Replay buffer with weighted sampling for failed plans.
    
    Failed plans (negative feedback) receive 3x weight, ensuring the model
    learns more from its mistakes during meta-learning.
    """
    
    def __init__(
        self,
        max_size: int = 10000,
        failed_plan_weight: float = 3.0,
        positive_weight: float = 1.0,
        negative_weight: float = 0.5
    ):
        """
        Initialize replay buffer.
        
        Args:
            max_size: Maximum buffer size
            failed_plan_weight: Weight multiplier for failed plans
            positive_weight: Weight for positive feedback
            negative_weight: Weight for negative feedback (non-failed)
        """
        self.max_size = max_size
        self.failed_plan_weight = failed_plan_weight
        self.positive_weight = positive_weight
        self.negative_weight = negative_weight
        
        self.buffer = deque(maxlen=max_size)
        self.failed_plans_buffer = deque(maxlen=max_size // 2)  # Separate buffer for failed plans
        
        logger.info(
            f"Replay buffer initialized: max_size={max_size}, "
            f"failed_weight={failed_plan_weight}x"
        )
    
    def add_sample(self, sample: Dict[str, Any]):
        """
        Add a sample to the buffer.
        
        Args:
            sample: Training sample with 'rating' field
        """
        # Set weight based on feedback type
        rating = sample.get('rating', 0)
        
        if rating == -1:  # Failed plan
            sample['weight'] = self.failed_plan_weight
            self.failed_plans_buffer.append(sample)
        elif rating == 1:  # Positive feedback
            sample['weight'] = self.positive_weight
        else:  # Other negative feedback
            sample['weight'] = self.negative_weight
        
        self.buffer.append(sample)
    
    def add_samples(self, samples: List[Dict[str, Any]]):
        """Add multiple samples to the buffer"""
        for sample in samples:
            self.add_sample(sample)
    
    def sample(self, batch_size: int, prioritize_failed: bool = True) -> List[Dict[str, Any]]:
        """
        Sample a batch from the buffer using weighted sampling.
        
        Args:
            batch_size: Number of samples to return
            prioritize_failed: If True, oversample failed plans
        
        Returns:
            List of samples
        """
        if len(self.buffer) == 0:
            return []
        
        # Calculate sampling probabilities based on weights
        samples = list(self.buffer)
        weights = [s.get('weight', 1.0) for s in samples]
        
        # If prioritizing failed plans, add failed plans multiple times
        if prioritize_failed and len(self.failed_plans_buffer) > 0:
            failed_samples = list(self.failed_plans_buffer)
            # Add failed plans 2 additional times for 3x total representation
            samples.extend(failed_samples * 2)
            weights.extend([s.get('weight', self.failed_plan_weight) for s in failed_samples] * 2)
        
        # Normalize weights
        total_weight = sum(weights)
        probabilities = [w / total_weight for w in weights]
        
        # Sample with replacement according to weights
        sampled = random.choices(
            samples,
            weights=probabilities,
            k=min(batch_size, len(samples))
        )
        
        return sampled
    
    def get_all_samples(self) -> List[Dict[str, Any]]:
        """Get all samples from buffer"""
        return list(self.buffer)
    
    def get_failed_plans(self) -> List[Dict[str, Any]]:
        """Get all failed plans"""
        return list(self.failed_plans_buffer)
    
    def clear(self):
        """Clear the buffer"""
        self.buffer.clear()
        self.failed_plans_buffer.clear()
        logger.info("Replay buffer cleared")
    
    def size(self) -> int:
        """Get current buffer size"""
        return len(self.buffer)
    
    def failed_plans_count(self) -> int:
        """Get number of failed plans"""
        return len(self.failed_plans_buffer)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get buffer statistics.
        
        Returns:
            Statistics dictionary
        """
        samples = list(self.buffer)
        
        if not samples:
            return {
                "total_samples": 0,
                "failed_plans": 0,
                "positive_samples": 0,
                "negative_samples": 0,
                "avg_weight": 0.0
            }
        
        failed_count = sum(1 for s in samples if s.get('rating') == -1)
        positive_count = sum(1 for s in samples if s.get('rating') == 1)
        negative_count = sum(1 for s in samples if s.get('rating', 0) < 1)
        
        weights = [s.get('weight', 1.0) for s in samples]
        avg_weight = sum(weights) / len(weights)
        
        return {
            "total_samples": len(samples),
            "failed_plans": failed_count,
            "positive_samples": positive_count,
            "negative_samples": negative_count,
            "avg_weight": avg_weight,
            "failed_plans_separate_buffer": len(self.failed_plans_buffer),
            "effective_failed_representation": failed_count * self.failed_plan_weight
        }
    
    def balance_buffer(
        self,
        target_failed_ratio: float = 0.3,
        target_positive_ratio: float = 0.5
    ):
        """
        Balance the buffer to achieve target ratios of sample types.
        
        Args:
            target_failed_ratio: Target ratio of failed plans
            target_positive_ratio: Target ratio of positive samples
        """
        logger.info(
            f"Balancing buffer: target_failed={target_failed_ratio:.1%}, "
            f"target_positive={target_positive_ratio:.1%}"
        )
        
        samples = list(self.buffer)
        
        if not samples:
            return
        
        # Categorize samples
        failed = [s for s in samples if s.get('rating') == -1]
        positive = [s for s in samples if s.get('rating') == 1]
        other = [s for s in samples if s.get('rating', 0) not in [-1, 1]]
        
        current_size = len(samples)
        
        # Calculate target sizes
        target_failed_size = int(current_size * target_failed_ratio)
        target_positive_size = int(current_size * target_positive_ratio)
        target_other_size = current_size - target_failed_size - target_positive_size
        
        # Sample to reach targets
        balanced_samples = []
        
        if len(failed) >= target_failed_size:
            balanced_samples.extend(random.sample(failed, target_failed_size))
        else:
            balanced_samples.extend(failed)
        
        if len(positive) >= target_positive_size:
            balanced_samples.extend(random.sample(positive, target_positive_size))
        else:
            balanced_samples.extend(positive)
        
        if len(other) >= target_other_size and target_other_size > 0:
            balanced_samples.extend(random.sample(other, target_other_size))
        elif target_other_size > 0:
            balanced_samples.extend(other)
        
        # Replace buffer
        self.buffer.clear()
        for sample in balanced_samples:
            self.buffer.append(sample)
        
        stats = self.get_statistics()
        logger.info(f"✓ Buffer balanced: {stats}")
    
    def export_samples(
        self,
        file_path: str,
        include_failed_only: bool = False
    ):
        """
        Export samples to a file.
        
        Args:
            file_path: Output file path
            include_failed_only: If True, only export failed plans
        """
        import json
        
        if include_failed_only:
            samples = list(self.failed_plans_buffer)
        else:
            samples = list(self.buffer)
        
        with open(file_path, 'w') as f:
            json.dump(samples, f, indent=2, default=str)
        
        logger.info(f"✓ Exported {len(samples)} samples to {file_path}")
    
    def import_samples(self, file_path: str):
        """
        Import samples from a file.
        
        Args:
            file_path: Input file path
        """
        import json
        
        with open(file_path, 'r') as f:
            samples = json.load(f)
        
        self.add_samples(samples)
        
        logger.info(f"✓ Imported {len(samples)} samples from {file_path}")


class PrioritizedReplayBuffer(WeightedReplayBuffer):
    """
    Prioritized replay buffer using TD-error or loss-based priorities.
    
    Extends WeightedReplayBuffer with priority-based sampling, where samples
    with higher loss/error are sampled more frequently.
    """
    
    def __init__(self, *args, alpha: float = 0.6, beta: float = 0.4, **kwargs):
        """
        Initialize prioritized replay buffer.
        
        Args:
            alpha: Priority exponent (0 = uniform, 1 = full prioritization)
            beta: Importance sampling exponent (0 = no correction, 1 = full correction)
        """
        super().__init__(*args, **kwargs)
        self.alpha = alpha
        self.beta = beta
        self.priorities = deque(maxlen=self.max_size)
        
        logger.info(f"Prioritized replay buffer: alpha={alpha}, beta={beta}")
    
    def add_sample(self, sample: Dict[str, Any], priority: Optional[float] = None):
        """
        Add sample with priority.
        
        Args:
            sample: Training sample
            priority: Sample priority (uses max priority if None)
        """
        super().add_sample(sample)
        
        # Set priority
        if priority is None:
            # Use max priority for new samples
            priority = max(self.priorities) if self.priorities else 1.0
        
        self.priorities.append(priority)
    
    def sample(
        self,
        batch_size: int,
        prioritize_failed: bool = True
    ) -> tuple[List[Dict[str, Any]], List[float]]:
        """
        Sample with priorities and return importance sampling weights.
        
        Returns:
            Tuple of (samples, importance_weights)
        """
        if len(self.buffer) == 0:
            return [], []
        
        samples = list(self.buffer)
        priorities = list(self.priorities)
        
        # Apply priority exponent
        probs = [(p ** self.alpha) for p in priorities]
        total_prob = sum(probs)
        probs = [p / total_prob for p in probs]
        
        # Sample indices
        indices = random.choices(
            range(len(samples)),
            weights=probs,
            k=min(batch_size, len(samples))
        )
        
        # Get samples
        sampled = [samples[i] for i in indices]
        
        # Calculate importance sampling weights
        N = len(samples)
        importance_weights = [(N * probs[i]) ** (-self.beta) for i in indices]
        max_weight = max(importance_weights)
        importance_weights = [w / max_weight for w in importance_weights]
        
        return sampled, importance_weights
    
    def update_priorities(self, indices: List[int], priorities: List[float]):
        """
        Update priorities for sampled indices.
        
        Args:
            indices: Sample indices
            priorities: New priorities
        """
        for idx, priority in zip(indices, priorities):
            if idx < len(self.priorities):
                self.priorities[idx] = priority
