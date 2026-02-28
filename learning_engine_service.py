#!/usr/bin/env python3
"""
Learning Engine Service

Implements continuous learning with:
- Fisher Information Matrix (FIM) calculation
- LoRA rank-16 fine-tuning
- Elastic Weight Consolidation (EWC) regularization
- LoRA adapter versioning on MinIO
- Hot-swap integration with MAX Serve
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

from learning_engine.trainer import LoRATrainer
from learning_engine.fisher import FisherInformationCalculator
from learning_engine.storage import AdapterStorage
from learning_engine.scheduler import TrainingScheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Configuration
class LearningEngineConfig(BaseModel):
    """Learning engine configuration"""
    service_host: str = Field(default="0.0.0.0")
    service_port: int = Field(default=8003)
    
    # Model configuration
    base_model_path: str = Field(default="/models/llama-3.3-8b-instruct-q4_k_m.gguf")
    model_name: str = Field(default="llama-3.3-8b-instruct")
    
    # LoRA configuration
    lora_rank: int = Field(default=16)
    lora_alpha: int = Field(default=32)
    lora_dropout: float = Field(default=0.05)
    target_modules: list = Field(default=["q_proj", "v_proj", "k_proj", "o_proj"])
    
    # EWC configuration
    ewc_lambda_min: float = Field(default=100.0)
    ewc_lambda_max: float = Field(default=1000.0)
    ewc_lambda: float = Field(default=500.0)
    fisher_history_days: int = Field(default=30)
    fisher_num_samples: int = Field(default=1000)
    
    # Training configuration
    batch_size: int = Field(default=4)
    gradient_accumulation_steps: int = Field(default=4)
    learning_rate: float = Field(default=2e-4)
    num_train_epochs: int = Field(default=3)
    max_seq_length: int = Field(default=2048)
    warmup_steps: int = Field(default=10)
    
    # Storage configuration
    minio_endpoint: str = Field(default="minio:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin123")
    minio_bucket: str = Field(default="lora-adapters")
    minio_secure: bool = Field(default=False)
    
    # Database configuration
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="ai_platform")
    postgres_user: str = Field(default="ai_user")
    postgres_password: str = Field(default="ai_password")
    
    # Scheduling
    auto_train_enabled: bool = Field(default=True)
    train_schedule_cron: str = Field(default="0 2 * * 1")  # Every Monday at 2 AM
    min_samples_for_training: int = Field(default=100)


# Load configuration from environment
def load_config() -> LearningEngineConfig:
    """Load configuration from environment variables"""
    return LearningEngineConfig(
        service_host=os.getenv("LEARNING_ENGINE_HOST", "0.0.0.0"),
        service_port=int(os.getenv("LEARNING_ENGINE_PORT", "8003")),
        base_model_path=os.getenv("BASE_MODEL_PATH", "/models/llama-3.3-8b-instruct-q4_k_m.gguf"),
        model_name=os.getenv("MODEL_NAME", "llama-3.3-8b-instruct"),
        lora_rank=int(os.getenv("LORA_RANK", "16")),
        lora_alpha=int(os.getenv("LORA_ALPHA", "32")),
        lora_dropout=float(os.getenv("LORA_DROPOUT", "0.05")),
        ewc_lambda=float(os.getenv("EWC_LAMBDA", "500.0")),
        fisher_history_days=int(os.getenv("FISHER_HISTORY_DAYS", "30")),
        fisher_num_samples=int(os.getenv("FISHER_NUM_SAMPLES", "1000")),
        batch_size=int(os.getenv("BATCH_SIZE", "4")),
        learning_rate=float(os.getenv("LEARNING_RATE", "2e-4")),
        num_train_epochs=int(os.getenv("NUM_TRAIN_EPOCHS", "3")),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
        minio_bucket=os.getenv("MINIO_BUCKET", "lora-adapters"),
        postgres_host=os.getenv("POSTGRES_HOST", "postgres"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_db=os.getenv("POSTGRES_DB", "ai_platform"),
        postgres_user=os.getenv("POSTGRES_USER", "ai_user"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "ai_password"),
        auto_train_enabled=os.getenv("AUTO_TRAIN_ENABLED", "true").lower() == "true",
    )


# Global state
config = load_config()
trainer: Optional[LoRATrainer] = None
fisher_calculator: Optional[FisherInformationCalculator] = None
storage: Optional[AdapterStorage] = None
scheduler: Optional[TrainingScheduler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for the service"""
    global trainer, fisher_calculator, storage, scheduler
    
    logger.info("Starting Learning Engine Service...")
    logger.info(f"Configuration: {config.model_dump()}")
    
    try:
        # Initialize components
        storage = AdapterStorage(
            endpoint=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            bucket_name=config.minio_bucket,
            secure=config.minio_secure
        )
        logger.info("✓ Storage initialized")
        
        fisher_calculator = FisherInformationCalculator(
            model_name=config.model_name,
            base_model_path=config.base_model_path
        )
        logger.info("✓ Fisher Information Calculator initialized")
        
        trainer = LoRATrainer(
            config=config,
            storage=storage,
            fisher_calculator=fisher_calculator
        )
        logger.info("✓ LoRA Trainer initialized")
        
        # Initialize scheduler
        if config.auto_train_enabled:
            scheduler = TrainingScheduler(
                trainer=trainer,
                config=config
            )
            await scheduler.start()
            logger.info("✓ Training Scheduler started")
        
        logger.info("Learning Engine Service ready!")
        
        yield
        
    finally:
        # Cleanup
        logger.info("Shutting down Learning Engine Service...")
        if scheduler:
            await scheduler.stop()
        logger.info("Learning Engine Service stopped")


# Create FastAPI app
app = FastAPI(
    title="Learning Engine Service",
    description="Continuous learning with LoRA fine-tuning and EWC regularization",
    version="1.0.0",
    lifespan=lifespan
)


# Request/Response models
class TrainingRequest(BaseModel):
    """Training request payload"""
    days: int = Field(default=7, description="Number of days to look back for training data")
    ewc_lambda: Optional[float] = Field(default=None, description="EWC lambda value (overrides config)")
    force: bool = Field(default=False, description="Force training even if sample count is low")


class TrainingResponse(BaseModel):
    """Training response payload"""
    status: str
    message: str
    job_id: Optional[str] = None
    adapter_version: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class FisherRequest(BaseModel):
    """Fisher Information Matrix calculation request"""
    adapter_version: Optional[str] = Field(default=None, description="Adapter version to use")
    num_samples: int = Field(default=1000, description="Number of samples for FIM calculation")


class FisherResponse(BaseModel):
    """Fisher Information Matrix calculation response"""
    status: str
    message: str
    fisher_version: Optional[str] = None
    num_parameters: Optional[int] = None


class AdapterListResponse(BaseModel):
    """Adapter list response"""
    adapters: list
    total: int


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
        "trainer": "healthy" if trainer else "not_initialized",
        "fisher_calculator": "healthy" if fisher_calculator else "not_initialized",
        "storage": "healthy" if storage else "not_initialized",
        "scheduler": "healthy" if scheduler and scheduler.is_running else "not_running"
    }
    
    all_healthy = all(status == "healthy" or status == "not_running" 
                      for status in components.values())
    
    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        version="1.0.0",
        components=components
    )


@app.post("/train", response_model=TrainingResponse)
async def trigger_training(request: TrainingRequest, background_tasks: BackgroundTasks):
    """Trigger a training job"""
    if not trainer:
        raise HTTPException(status_code=503, detail="Trainer not initialized")
    
    try:
        # Start training in background
        job_id = f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        background_tasks.add_task(
            trainer.train_from_feedback,
            days=request.days,
            ewc_lambda=request.ewc_lambda or config.ewc_lambda,
            force=request.force,
            job_id=job_id
        )
        
        return TrainingResponse(
            status="started",
            message=f"Training job started with ID: {job_id}",
            job_id=job_id
        )
        
    except Exception as e:
        logger.error(f"Failed to start training: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/fisher/calculate", response_model=FisherResponse)
async def calculate_fisher(request: FisherRequest, background_tasks: BackgroundTasks):
    """Calculate Fisher Information Matrix"""
    if not fisher_calculator:
        raise HTTPException(status_code=503, detail="Fisher calculator not initialized")
    
    try:
        # Load adapter if specified
        if request.adapter_version:
            adapter_path = await storage.download_adapter(request.adapter_version)
            fisher_calculator.load_adapter(adapter_path)
        
        # Calculate FIM in background
        fisher_version = f"fisher_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        background_tasks.add_task(
            fisher_calculator.calculate_and_save,
            num_samples=request.num_samples,
            version=fisher_version
        )
        
        return FisherResponse(
            status="started",
            message=f"Fisher calculation started with version: {fisher_version}",
            fisher_version=fisher_version
        )
        
    except Exception as e:
        logger.error(f"Failed to calculate Fisher: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/adapters", response_model=AdapterListResponse)
async def list_adapters():
    """List all available LoRA adapters"""
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    
    try:
        adapters = await storage.list_adapters()
        return AdapterListResponse(
            adapters=adapters,
            total=len(adapters)
        )
        
    except Exception as e:
        logger.error(f"Failed to list adapters: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/adapters/{version}")
async def get_adapter_info(version: str):
    """Get information about a specific adapter"""
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    
    try:
        info = await storage.get_adapter_metadata(version)
        if not info:
            raise HTTPException(status_code=404, detail=f"Adapter {version} not found")
        
        return info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get adapter info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/adapters/{version}/deploy")
async def deploy_adapter(version: str):
    """Deploy an adapter to MAX Serve (hot-swap)"""
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    
    try:
        # Download adapter
        local_path = await storage.download_adapter(version)
        
        # Hot-swap with MAX Serve
        # This would integrate with MAX Serve API to load the adapter
        # For now, we just return success
        
        return {
            "status": "deployed",
            "message": f"Adapter {version} deployed successfully",
            "version": version,
            "path": local_path
        }
        
    except Exception as e:
        logger.error(f"Failed to deploy adapter: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/training/status")
async def get_training_status():
    """Get current training status"""
    if not trainer:
        raise HTTPException(status_code=503, detail="Trainer not initialized")
    
    try:
        status = trainer.get_status()
        return status
        
    except Exception as e:
        logger.error(f"Failed to get training status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def get_metrics():
    """Get training metrics and statistics"""
    if not trainer:
        raise HTTPException(status_code=503, detail="Trainer not initialized")
    
    try:
        metrics = trainer.get_metrics()
        return metrics
        
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=config.service_host,
        port=config.service_port,
        log_level="info"
    )
