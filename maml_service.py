#!/usr/bin/env python3
"""
MAML Meta-Learning Service

Implements complete MAML pipeline with:
- Per-project task extraction
- Meta-weight optimization for fast adaptation
- Monthly CronJob execution
- Adaptation metrics tracking (target <10 steps to 80% accuracy)
- Meta-weights storage on MinIO with versioning
- 3x weighted replay buffer for failed plans
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from learning_engine.maml import MAMLLearner
from learning_engine.task_extractor import TaskExtractor
from learning_engine.replay_buffer import WeightedReplayBuffer
from learning_engine.meta_storage import MetaWeightsStorage
from learning_engine.adaptation_metrics import AdaptationMetricsTracker
from learning_engine.maml_scheduler import MAMLScheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Configuration
class MAMLConfig(BaseModel):
    """MAML service configuration"""
    service_host: str = Field(default="0.0.0.0")
    service_port: int = Field(default=8005)
    
    # Model configuration
    model_name: str = Field(default="meta-llama/Llama-3.3-8B-Instruct")
    
    # LoRA configuration
    lora_rank: int = Field(default=16)
    lora_alpha: int = Field(default=32)
    lora_dropout: float = Field(default=0.05)
    target_modules: list = Field(default=["q_proj", "v_proj", "k_proj", "o_proj"])
    max_seq_length: int = Field(default=2048)
    
    # MAML hyperparameters
    maml_inner_lr: float = Field(default=1e-3)
    maml_outer_lr: float = Field(default=1e-4)
    maml_inner_steps: int = Field(default=5)
    maml_outer_steps: int = Field(default=100)
    maml_inner_batch_size: int = Field(default=4)
    maml_outer_batch_size: int = Field(default=2)
    maml_target_accuracy: float = Field(default=0.80)
    maml_max_adaptation_steps: int = Field(default=10)
    
    # Task extraction
    task_extraction_days: int = Field(default=30)
    min_samples_per_task: int = Field(default=20)
    task_strategy: str = Field(default="mixed")  # project, intent, temporal, mixed
    
    # Replay buffer
    replay_buffer_size: int = Field(default=10000)
    failed_plan_weight: float = Field(default=3.0)
    
    # Storage configuration
    minio_endpoint: str = Field(default="minio:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin123")
    minio_secure: bool = Field(default=False)
    
    # Database configuration
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="ai_platform")
    postgres_user: str = Field(default="ai_user")
    postgres_password: str = Field(default="ai_password")
    
    # Scheduling
    maml_schedule_enabled: bool = Field(default=True)
    maml_cron_schedule: str = Field(default="0 2 1 * *")  # Monthly: 1st day at 2 AM


# Load configuration
def load_config() -> MAMLConfig:
    """Load configuration from environment variables"""
    return MAMLConfig(
        service_host=os.getenv("MAML_SERVICE_HOST", "0.0.0.0"),
        service_port=int(os.getenv("MAML_SERVICE_PORT", "8005")),
        model_name=os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-8B-Instruct"),
        lora_rank=int(os.getenv("LORA_RANK", "16")),
        lora_alpha=int(os.getenv("LORA_ALPHA", "32")),
        lora_dropout=float(os.getenv("LORA_DROPOUT", "0.05")),
        maml_inner_lr=float(os.getenv("MAML_INNER_LR", "1e-3")),
        maml_outer_lr=float(os.getenv("MAML_OUTER_LR", "1e-4")),
        maml_inner_steps=int(os.getenv("MAML_INNER_STEPS", "5")),
        maml_outer_steps=int(os.getenv("MAML_OUTER_STEPS", "100")),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
        postgres_host=os.getenv("POSTGRES_HOST", "postgres"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_db=os.getenv("POSTGRES_DB", "ai_platform"),
        postgres_user=os.getenv("POSTGRES_USER", "ai_user"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "ai_password"),
        maml_schedule_enabled=os.getenv("MAML_SCHEDULE_ENABLED", "true").lower() == "true",
        maml_cron_schedule=os.getenv("MAML_CRON_SCHEDULE", "0 2 1 * *"),
    )


# Global state
config = load_config()
maml_learner: Optional[MAMLLearner] = None
task_extractor: Optional[TaskExtractor] = None
replay_buffer: Optional[WeightedReplayBuffer] = None
meta_storage: Optional[MetaWeightsStorage] = None
metrics_tracker: Optional[AdaptationMetricsTracker] = None
scheduler: Optional[MAMLScheduler] = None


async def run_meta_training():
    """Execute MAML meta-training"""
    global maml_learner, task_extractor, replay_buffer, meta_storage, metrics_tracker
    
    try:
        logger.info("=" * 60)
        logger.info("Starting MAML Meta-Training Pipeline")
        logger.info("=" * 60)
        
        # Extract tasks from feedback data
        logger.info("Step 1: Extracting per-project tasks...")
        task_batches = task_extractor.extract_all_tasks(
            days=config.task_extraction_days,
            min_samples=config.min_samples_per_task,
            strategy=config.task_strategy
        )
        
        if len(task_batches) == 0:
            logger.warning("No tasks extracted. Skipping meta-training.")
            return
        
        logger.info(f"✓ Extracted {len(task_batches)} tasks")
        
        # Load failed plans into replay buffer
        logger.info("Step 2: Loading failed plans into replay buffer...")
        failed_plans = task_extractor.get_failed_plans(
            days=config.task_extraction_days
        )
        
        if failed_plans:
            replay_buffer.add_samples(failed_plans)
            logger.info(f"✓ Loaded {len(failed_plans)} failed plans (3x weighted)")
        
        # Augment tasks with replay buffer samples
        for task_batch in task_batches:
            # Add some failed plan samples to each task
            replay_samples = replay_buffer.sample(
                batch_size=min(len(task_batch) // 4, 10),
                prioritize_failed=True
            )
            task_batch.extend(replay_samples)
        
        logger.info(f"✓ Augmented tasks with replay buffer")
        
        # Initialize MAML learner if not already initialized
        if maml_learner.meta_model is None:
            logger.info("Step 3: Initializing MAML meta-model...")
            maml_learner.initialize_model()
        
        # Run meta-training (outer loop)
        logger.info("Step 4: Running MAML meta-training (outer loop)...")
        start_time = datetime.now()
        
        training_metrics = maml_learner.outer_loop(
            task_batches=task_batches,
            num_steps=config.maml_outer_steps
        )
        
        training_duration = (datetime.now() - start_time).total_seconds()
        training_metrics['training_duration_seconds'] = training_duration
        
        # Generate version
        version = f"maml_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info("Step 5: Saving meta-weights to MinIO...")
        meta_weights = maml_learner.get_meta_weights()
        
        metadata = {
            "version": version,
            "num_tasks": len(task_batches),
            "num_outer_steps": config.maml_outer_steps,
            "num_inner_steps": config.maml_inner_steps,
            "metrics": training_metrics,
            "config": config.model_dump(),
            "failed_plans_count": len(failed_plans),
            "replay_buffer_stats": replay_buffer.get_statistics()
        }
        
        meta_storage.upload_meta_weights(
            weights=meta_weights,
            version=version,
            metadata=metadata
        )
        
        logger.info("Step 6: Recording meta-training metrics...")
        metrics_tracker.record_meta_training(
            version=version,
            metrics=training_metrics,
            training_metadata=metadata
        )
        
        logger.info("=" * 60)
        logger.info("MAML Meta-Training Complete!")
        logger.info("=" * 60)
        logger.info(f"Version: {version}")
        logger.info(f"Tasks trained: {len(task_batches)}")
        logger.info(f"Meta loss: {training_metrics['final_meta_loss']:.4f}")
        logger.info(f"Mean task accuracy: {training_metrics['mean_task_accuracy']:.2%}")
        logger.info(f"Duration: {training_duration:.2f}s")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Meta-training failed: {e}", exc_info=True)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    global maml_learner, task_extractor, replay_buffer, meta_storage, metrics_tracker, scheduler
    
    logger.info("Starting MAML Meta-Learning Service...")
    logger.info(f"Configuration: {config.model_dump()}")
    
    try:
        # Initialize components
        task_extractor = TaskExtractor(
            postgres_host=config.postgres_host,
            postgres_port=config.postgres_port,
            postgres_db=config.postgres_db,
            postgres_user=config.postgres_user,
            postgres_password=config.postgres_password
        )
        logger.info("✓ Task extractor initialized")
        
        replay_buffer = WeightedReplayBuffer(
            max_size=config.replay_buffer_size,
            failed_plan_weight=config.failed_plan_weight
        )
        logger.info("✓ Replay buffer initialized")
        
        meta_storage = MetaWeightsStorage(
            endpoint=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            bucket_name="meta-weights",
            secure=config.minio_secure
        )
        logger.info("✓ Meta-weights storage initialized")
        
        metrics_tracker = AdaptationMetricsTracker(
            postgres_host=config.postgres_host,
            postgres_port=config.postgres_port,
            postgres_db=config.postgres_db,
            postgres_user=config.postgres_user,
            postgres_password=config.postgres_password
        )
        logger.info("✓ Metrics tracker initialized")
        
        maml_learner = MAMLLearner(
            model_name=config.model_name,
            config=config
        )
        logger.info("✓ MAML learner initialized")
        
        # Initialize scheduler
        if config.maml_schedule_enabled:
            scheduler = MAMLScheduler(
                cron_schedule=config.maml_cron_schedule,
                callback=run_meta_training
            )
            await scheduler.start()
            logger.info("✓ MAML scheduler started")
        
        logger.info("MAML Meta-Learning Service ready!")
        
        yield
        
    finally:
        logger.info("Shutting down MAML Meta-Learning Service...")
        if scheduler:
            await scheduler.stop()
        logger.info("MAML Service stopped")


# Create FastAPI app
app = FastAPI(
    title="MAML Meta-Learning Service",
    description="MAML meta-learning pipeline for fast adaptation across projects",
    version="1.0.0",
    lifespan=lifespan
)


# Request/Response models
class MetaTrainingRequest(BaseModel):
    """Meta-training request"""
    days: int = Field(default=30, description="Days of data to use")
    task_strategy: Optional[str] = Field(default=None, description="Task extraction strategy")
    num_outer_steps: Optional[int] = Field(default=None, description="Override outer steps")
    force: bool = Field(default=False, description="Force training even if insufficient tasks")


class AdaptationRequest(BaseModel):
    """Fast adaptation request"""
    project: str = Field(description="Project identifier for adaptation")
    days: int = Field(default=7, description="Days of project data to use")
    target_accuracy: Optional[float] = Field(default=None, description="Target accuracy")
    max_steps: Optional[int] = Field(default=None, description="Maximum adaptation steps")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    components: Dict[str, str]


# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    components = {
        "maml_learner": "healthy" if maml_learner else "not_initialized",
        "task_extractor": "healthy" if task_extractor else "not_initialized",
        "replay_buffer": "healthy" if replay_buffer else "not_initialized",
        "meta_storage": "healthy" if meta_storage else "not_initialized",
        "metrics_tracker": "healthy" if metrics_tracker else "not_initialized",
        "scheduler": "healthy" if scheduler and scheduler.is_running else "not_running"
    }
    
    all_healthy = all(status in ["healthy", "not_running"] for status in components.values())
    
    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        version="1.0.0",
        components=components
    )


@app.post("/meta-train")
async def trigger_meta_training(
    request: MetaTrainingRequest,
    background_tasks: BackgroundTasks
):
    """Trigger MAML meta-training"""
    if not maml_learner:
        raise HTTPException(status_code=503, detail="MAML learner not initialized")
    
    try:
        # Override config if provided
        if request.task_strategy:
            config.task_strategy = request.task_strategy
        if request.num_outer_steps:
            config.maml_outer_steps = request.num_outer_steps
        
        config.task_extraction_days = request.days
        
        # Start meta-training in background
        background_tasks.add_task(run_meta_training)
        
        return {
            "status": "started",
            "message": "Meta-training started in background",
            "config": {
                "days": request.days,
                "task_strategy": config.task_strategy,
                "num_outer_steps": config.maml_outer_steps
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to start meta-training: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/adapt")
async def fast_adaptation(request: AdaptationRequest):
    """Fast adaptation to a new project/task"""
    if not maml_learner or not task_extractor or not metrics_tracker:
        raise HTTPException(status_code=503, detail="Service not fully initialized")
    
    try:
        logger.info(f"Fast adaptation requested for project: {request.project}")
        
        # Extract project task data
        project_tasks = task_extractor.extract_project_tasks(
            days=request.days,
            min_samples_per_project=1  # Lower threshold for adaptation
        )
        
        if request.project not in project_tasks:
            raise HTTPException(
                status_code=404,
                detail=f"Project '{request.project}' not found or insufficient data"
            )
        
        task_data = project_tasks[request.project]
        
        # Run adaptation
        adaptation_metrics = maml_learner.adapt_to_task(
            task_data=task_data,
            target_accuracy=request.target_accuracy,
            max_steps=request.max_steps
        )
        
        # Record metrics
        task_metadata = {
            "project": request.project,
            "task_type": "project_adaptation",
            "num_support_samples": len(task_data),
            "meta_version": meta_storage.get_latest_version()
        }
        
        metrics_tracker.record_adaptation(
            task_id=f"{request.project}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            metrics=adaptation_metrics,
            task_metadata=task_metadata
        )
        
        return {
            "status": "success",
            "project": request.project,
            "metrics": adaptation_metrics,
            "target_met": adaptation_metrics.get('target_reached', False)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Adaptation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/meta-weights/versions")
async def list_meta_weight_versions():
    """List all meta-weights versions"""
    if not meta_storage:
        raise HTTPException(status_code=503, detail="Meta-storage not initialized")
    
    try:
        versions = meta_storage.list_versions()
        return {
            "versions": versions,
            "total": len(versions),
            "latest": meta_storage.get_latest_version()
        }
    except Exception as e:
        logger.error(f"Failed to list versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics/adaptation")
async def get_adaptation_metrics(days: int = 30, project: Optional[str] = None):
    """Get adaptation performance metrics"""
    if not metrics_tracker:
        raise HTTPException(status_code=503, detail="Metrics tracker not initialized")
    
    try:
        stats = metrics_tracker.get_adaptation_statistics(days=days, project=project)
        target_check = metrics_tracker.check_target_performance(days=7)
        
        return {
            "statistics": stats,
            "target_performance": target_check,
            "recent_adaptations": metrics_tracker.get_recent_adaptations(limit=5, project=project)
        }
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics/projects")
async def get_project_metrics(days: int = 30):
    """Get per-project adaptation performance"""
    if not metrics_tracker:
        raise HTTPException(status_code=503, detail="Metrics tracker not initialized")
    
    try:
        projects = metrics_tracker.get_project_adaptation_performance(days=days)
        return {
            "projects": projects,
            "total_projects": len(projects),
            "days": days
        }
    except Exception as e:
        logger.error(f"Failed to get project metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scheduler/info")
async def get_scheduler_info():
    """Get scheduler information"""
    if not scheduler:
        return {"enabled": False, "message": "Scheduler not enabled"}
    
    return {
        "enabled": True,
        **scheduler.get_schedule_info()
    }


@app.post("/scheduler/trigger")
async def trigger_scheduler_now(background_tasks: BackgroundTasks):
    """Manually trigger scheduled meta-training"""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not enabled")
    
    background_tasks.add_task(scheduler.trigger_now)
    
    return {
        "status": "triggered",
        "message": "Meta-training triggered manually"
    }


@app.get("/replay-buffer/stats")
async def get_replay_buffer_stats():
    """Get replay buffer statistics"""
    if not replay_buffer:
        raise HTTPException(status_code=503, detail="Replay buffer not initialized")
    
    try:
        stats = replay_buffer.get_statistics()
        return stats
    except Exception as e:
        logger.error(f"Failed to get buffer stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=config.service_host,
        port=config.service_port,
        log_level="info"
    )
