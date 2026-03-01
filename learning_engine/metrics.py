#!/usr/bin/env python3
"""
Prometheus metrics for Learning Engine.

Exports metrics for:
- Training/validation loss
- Training duration and samples
- EWC lambda values
- LoRA version tracking
"""

from prometheus_client import Counter, Gauge, Histogram, Info


# Training metrics
training_loss = Gauge(
    'training_loss',
    'Current training loss',
    ['model', 'version_id']
)

validation_loss = Gauge(
    'validation_loss',
    'Current validation loss',
    ['model', 'version_id']
)

training_duration_seconds = Gauge(
    'training_duration_seconds',
    'Duration of last training run in seconds',
    ['model', 'version_id']
)

training_samples_total = Gauge(
    'training_samples_total',
    'Total number of training samples used',
    ['model', 'version_id']
)

# EWC metrics
ewc_lambda = Gauge(
    'ewc_lambda',
    'Current EWC regularization lambda value',
    ['model', 'version_id']
)

ewc_loss = Gauge(
    'ewc_loss',
    'EWC regularization loss contribution',
    ['model', 'version_id']
)

# LoRA version metrics
lora_versions_total = Gauge(
    'lora_versions_total',
    'Total number of LoRA versions created',
    ['model']
)

lora_active_version = Info(
    'lora_active_version',
    'Currently active LoRA version'
)

# Training events
training_runs_total = Counter(
    'training_runs_total',
    'Total number of training runs',
    ['model', 'status']  # status: success, skipped, failed
)

training_epochs_total = Counter(
    'training_epochs_total',
    'Total number of training epochs',
    ['model']
)

# Model performance
model_perplexity = Gauge(
    'model_perplexity',
    'Model perplexity score',
    ['model', 'version_id']
)

model_accuracy = Gauge(
    'model_accuracy',
    'Model accuracy on validation set',
    ['model', 'version_id']
)

# Fisher information metrics
fisher_computation_duration_seconds = Histogram(
    'fisher_computation_duration_seconds',
    'Duration to compute Fisher information matrix',
    ['model'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

fisher_matrix_size_bytes = Gauge(
    'fisher_matrix_size_bytes',
    'Size of Fisher information matrix in bytes',
    ['model']
)

# Replay buffer metrics
replay_buffer_size = Gauge(
    'replay_buffer_size',
    'Current size of replay buffer',
    ['model']
)

replay_buffer_capacity = Gauge(
    'replay_buffer_capacity',
    'Maximum capacity of replay buffer',
    ['model']
)

# MAML metrics (if using meta-learning)
maml_inner_steps = Gauge(
    'maml_inner_steps',
    'Number of inner adaptation steps',
    ['model']
)

maml_outer_lr = Gauge(
    'maml_outer_lr',
    'MAML outer learning rate',
    ['model']
)

maml_inner_lr = Gauge(
    'maml_inner_lr',
    'MAML inner learning rate',
    ['model']
)

# Gradient metrics
gradient_norm = Gauge(
    'gradient_norm',
    'L2 norm of gradients',
    ['model', 'version_id']
)

parameter_updates_total = Counter(
    'parameter_updates_total',
    'Total number of parameter updates',
    ['model']
)
