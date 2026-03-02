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
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
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
    lora_enabled: bool = Field(default=True)
    initial_adapter_version: Optional[str] = Field(default=None)
    lora_rank: int = Field(default=16)
    lora_alpha: int = Field(default=32)
    lora_dropout: float = Field(default=0.05)
    target_modules: list = Field(default=["q_proj", "v_proj", "k_proj", "o_proj"])
    lora_control_base_url: Optional[str] = Field(default=None)
    lora_reload_endpoint_path: str = Field(default="/internal/lora/reload")
    lora_rollback_endpoint_path: str = Field(default="/internal/lora/rollback")
    lora_operation_timeout_seconds: float = Field(default=120.0)
    
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

    # Golden-set validation configuration
    golden_validation_enabled: bool = Field(default=True)
    golden_validation_required: bool = Field(default=False)
    golden_suite_path: str = Field(
        default="tests/contract/fixtures/lora_regression_prompts.ndjson"
    )
    golden_baseline_output_path: str = Field(
        default="tests/contract/fixtures/lora_baseline_outputs.ndjson"
    )
    golden_candidate_output_dir: str = Field(default="./lora_validation")
    golden_validation_max_new_tokens: int = Field(default=192)
    golden_max_regressions: int = Field(default=1)
    golden_max_mean_score_drop: float = Field(default=0.15)
    golden_min_pass_rate: float = Field(default=0.85)
    golden_max_unsafe_cases: int = Field(default=0)
    
    # Storage configuration
    minio_endpoint: str = Field(default="minio:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin123")
    minio_bucket: str = Field(default="lora-adapters")
    minio_secure: bool = Field(default=False)
    lora_project: str = Field(default="default")
    
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
        lora_enabled=os.getenv("LORA_ENABLED", "true").lower() == "true",
        initial_adapter_version=os.getenv("ACTIVE_LORA_ADAPTER"),
        lora_rank=int(os.getenv("LORA_RANK", "16")),
        lora_alpha=int(os.getenv("LORA_ALPHA", "32")),
        lora_dropout=float(os.getenv("LORA_DROPOUT", "0.05")),
        lora_control_base_url=os.getenv("LORA_CONTROL_BASE_URL"),
        lora_reload_endpoint_path=os.getenv("LORA_RELOAD_ENDPOINT_PATH", "/internal/lora/reload"),
        lora_rollback_endpoint_path=os.getenv("LORA_ROLLBACK_ENDPOINT_PATH", "/internal/lora/rollback"),
        lora_operation_timeout_seconds=float(os.getenv("LORA_OPERATION_TIMEOUT_SECONDS", "120")),
        ewc_lambda=float(os.getenv("EWC_LAMBDA", "500.0")),
        fisher_history_days=int(os.getenv("FISHER_HISTORY_DAYS", "30")),
        fisher_num_samples=int(os.getenv("FISHER_NUM_SAMPLES", "1000")),
        batch_size=int(os.getenv("BATCH_SIZE", "4")),
        learning_rate=float(os.getenv("LEARNING_RATE", "2e-4")),
        num_train_epochs=int(os.getenv("NUM_TRAIN_EPOCHS", "3")),
        golden_validation_enabled=os.getenv("GOLDEN_VALIDATION_ENABLED", "true").lower() == "true",
        golden_validation_required=os.getenv("GOLDEN_VALIDATION_REQUIRED", "false").lower() == "true",
        golden_suite_path=os.getenv(
            "GOLDEN_SUITE_PATH",
            "tests/contract/fixtures/lora_regression_prompts.ndjson",
        ),
        golden_baseline_output_path=os.getenv(
            "GOLDEN_BASELINE_OUTPUT_PATH",
            "tests/contract/fixtures/lora_baseline_outputs.ndjson",
        ),
        golden_candidate_output_dir=os.getenv(
            "GOLDEN_CANDIDATE_OUTPUT_DIR",
            "./lora_validation",
        ),
        golden_validation_max_new_tokens=int(
            os.getenv("GOLDEN_VALIDATION_MAX_NEW_TOKENS", "192")
        ),
        golden_max_regressions=int(os.getenv("GOLDEN_MAX_REGRESSIONS", "1")),
        golden_max_mean_score_drop=float(
            os.getenv("GOLDEN_MAX_MEAN_SCORE_DROP", "0.15")
        ),
        golden_min_pass_rate=float(os.getenv("GOLDEN_MIN_PASS_RATE", "0.85")),
        golden_max_unsafe_cases=int(os.getenv("GOLDEN_MAX_UNSAFE_CASES", "0")),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
        minio_bucket=os.getenv("MINIO_BUCKET", "lora-adapters"),
        lora_project=os.getenv("LORA_PROJECT", "default"),
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


class LoRAState:
    """In-memory runtime state for LoRA kill-switch and rollback operations."""

    def __init__(self, enabled: bool, active_version: Optional[str]):
        self.enabled = enabled
        self.active_adapter_version = active_version
        self.previous_adapter_version: Optional[str] = None
        self.known_good_adapter_version: Optional[str] = active_version
        self.last_operation: str = "initialized"
        self.last_reason: Optional[str] = None
        self.updated_at = datetime.utcnow()
        self.activation_history: List[Dict[str, Any]] = []
        self.rollback_history: List[Dict[str, Any]] = []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "active_adapter_version": self.active_adapter_version,
            "previous_adapter_version": self.previous_adapter_version,
            "known_good_adapter_version": self.known_good_adapter_version,
            "last_operation": self.last_operation,
            "last_reason": self.last_reason,
            "updated_at": self.updated_at.isoformat() + "Z",
            "activation_history": self.activation_history,
            "rollback_history": self.rollback_history,
        }


lora_state = LoRAState(
    enabled=config.lora_enabled,
    active_version=config.initial_adapter_version,
)


MAX_LORA_HISTORY_ENTRIES = 100


def _append_history(history: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    history.append(entry)
    if len(history) > MAX_LORA_HISTORY_ENTRIES:
        del history[:-MAX_LORA_HISTORY_ENTRIES]


def _decode_control_plane_body(raw_body: bytes) -> Any:
    if not raw_body:
        return None

    payload = raw_body.decode("utf-8", errors="replace")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return payload


def _build_control_plane_url(endpoint_path: str) -> str:
    base_url = (config.lora_control_base_url or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail="LoRA control plane is not configured. Set LORA_CONTROL_BASE_URL."
        )

    normalized_path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", normalized_path.lstrip("/"))


def _request_lora_control_plane(
    method: str,
    endpoint_path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = _build_control_plane_url(endpoint_path)
    body = None
    headers: Dict[str, str] = {}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url=url,
        data=body,
        headers=headers,
        method=method.upper(),
    )

    try:
        with urllib.request.urlopen(request, timeout=config.lora_operation_timeout_seconds) as response:  # nosec B310
            return {
                "status_code": response.status,
                "url": url,
                "body": _decode_control_plane_body(response.read()),
            }
    except urllib.error.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "lora_control_plane_http_error",
                "status_code": exc.code,
                "url": url,
                "details": _decode_control_plane_body(exc.read()),
            }
        ) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "lora_control_plane_unreachable",
                "url": url,
                "details": str(exc.reason),
            }
        ) from exc


async def _call_lora_control_plane(
    method: str,
    endpoint_path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _request_lora_control_plane,
        method,
        endpoint_path,
        payload,
    )


async def _activate_adapter_version(
    version: str,
    reason: str,
    operation: str,
    model_name: Optional[str] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not initialized")

    from_version = lora_state.active_adapter_version
    started_at = time.monotonic()

    local_path = await storage.download_adapter(version, model_name=model_name, project_name=project)
    control_plane = await _call_lora_control_plane(
        method="POST",
        endpoint_path=config.lora_reload_endpoint_path,
        payload={"adapter_path": local_path, "adapter_version": version},
    )
    duration_ms = int((time.monotonic() - started_at) * 1000)

    lora_state.previous_adapter_version = from_version
    lora_state.active_adapter_version = version
    lora_state.enabled = True
    lora_state.last_operation = operation
    lora_state.last_reason = reason
    lora_state.updated_at = datetime.utcnow()

    # Previous active adapter becomes the fast rollback target.
    if from_version and from_version != version:
        lora_state.known_good_adapter_version = from_version
    elif lora_state.known_good_adapter_version is None:
        lora_state.known_good_adapter_version = version

    _append_history(
        lora_state.activation_history,
        {
            "timestamp": lora_state.updated_at.isoformat() + "Z",
            "operation": operation,
            "from_version": from_version,
            "to_version": version,
            "reason": reason,
            "duration_ms": duration_ms,
            "control_plane_status": control_plane["status_code"],
        },
    )

    return {
        "version": version,
        "path": local_path,
        "from_version": from_version,
        "duration_ms": duration_ms,
        "control_plane": control_plane,
    }


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
            secure=config.minio_secure,
            model_name=config.model_name,
            project_name=config.lora_project,
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
    trigger_source: Optional[str] = Field(default="manual", description="Source that triggered training")
    audit_context: Optional[Dict[str, Any]] = Field(default=None, description="Audit metadata for the trigger")
    dataset_id: Optional[str] = Field(default=None, description="Training dataset identifier")
    author: Optional[str] = Field(default=None, description="Author for this adapter version")
    validation_metrics: Dict[str, Any] = Field(default_factory=dict, description="Validation metrics metadata")
    golden_validation_enabled: Optional[bool] = Field(
        default=None, description="Enable/disable golden-set validation for this run"
    )
    golden_validation_required: Optional[bool] = Field(
        default=None, description="Block promotion when golden-set validation fails"
    )
    golden_suite_path: Optional[str] = Field(
        default=None, description="Path to golden regression prompt suite"
    )
    golden_baseline_output_path: Optional[str] = Field(
        default=None, description="Path to golden baseline outputs JSON"
    )
    golden_candidate_output_path: Optional[str] = Field(
        default=None,
        description=(
            "Optional path to candidate outputs JSON. "
            "If omitted, outputs are generated from the trained adapter."
        ),
    )
    golden_thresholds: Dict[str, Any] = Field(
        default_factory=dict,
        description="Threshold overrides for golden-set gate",
    )


class JsonlTrainingRequest(BaseModel):
    """JSONL training request payload"""
    dataset_path: str = Field(..., description="Path to the JSONL dataset file")
    learning_rate: Optional[float] = Field(default=None, gt=0, description="Learning rate override")
    epochs: Optional[int] = Field(default=None, gt=0, description="Epoch count override")
    batch_size: Optional[int] = Field(default=None, gt=0, description="Batch size override")


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


class LoRAStatusResponse(BaseModel):
    """Current LoRA runtime state."""
    enabled: bool
    active_adapter_version: Optional[str] = None
    previous_adapter_version: Optional[str] = None
    known_good_adapter_version: Optional[str] = None
    last_operation: str
    last_reason: Optional[str] = None
    updated_at: str
    activation_history: List[Dict[str, Any]] = Field(default_factory=list)
    rollback_history: List[Dict[str, Any]] = Field(default_factory=list)


class LoRAOperationRequest(BaseModel):
    """Payload for LoRA control operations."""
    adapter_version: Optional[str] = Field(default=None, description="Target adapter version")
    reason: str = Field(default="manual_operation", description="Reason for the operation")


class AdapterDeployRequest(BaseModel):
    """Payload for adapter deployment / activation."""
    reason: str = Field(default="manual_deploy", description="Reason for adapter activation")
class GoldenValidationRequest(BaseModel):
    """Payload for explicit golden-set validation runs."""

    suite_path: str = Field(
        default="tests/contract/fixtures/lora_regression_prompts.ndjson",
        description="Path to golden regression prompt suite",
    )
    baseline_output_path: str = Field(
        default="tests/contract/fixtures/lora_baseline_outputs.ndjson",
        description="Path to baseline outputs JSON",
    )
    candidate_output_path: str = Field(
        ...,
        description="Path to candidate outputs JSON",
    )
    thresholds: Dict[str, Any] = Field(
        default_factory=dict,
        description="Validation threshold overrides",
    )


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


@app.get("/lora/status", response_model=LoRAStatusResponse)
async def get_lora_status():
    """Get LoRA kill-switch status and current adapter context."""
    return LoRAStatusResponse(**lora_state.as_dict())


@app.post("/lora/disable", response_model=LoRAStatusResponse)
async def disable_lora(request: LoRAOperationRequest):
    """Disable LoRA adapters and route inference back to the base model."""
    if lora_state.active_adapter_version:
        lora_state.known_good_adapter_version = lora_state.active_adapter_version

    lora_state.previous_adapter_version = lora_state.active_adapter_version
    lora_state.active_adapter_version = None
    lora_state.enabled = False
    lora_state.last_operation = "disabled"
    lora_state.last_reason = request.reason
    lora_state.updated_at = datetime.utcnow()

    return LoRAStatusResponse(**lora_state.as_dict())


@app.post("/lora/enable", response_model=LoRAStatusResponse)
async def enable_lora(request: LoRAOperationRequest):
    """Enable LoRA adapters and optionally pin a specific adapter version."""
    if request.adapter_version:
        await _activate_adapter_version(
            version=request.adapter_version,
            reason=request.reason,
            operation="enabled",
        )
    else:
        lora_state.enabled = True
        lora_state.last_operation = "enabled"
        lora_state.last_reason = request.reason
        lora_state.updated_at = datetime.utcnow()

        if lora_state.active_adapter_version and lora_state.known_good_adapter_version is None:
            lora_state.known_good_adapter_version = lora_state.active_adapter_version

    return LoRAStatusResponse(**lora_state.as_dict())


@app.post("/lora/rollback", response_model=LoRAStatusResponse)
async def rollback_lora(request: LoRAOperationRequest):
    """Rollback to previous known-good adapter version."""
    from_version = lora_state.active_adapter_version
    operation_started_at = time.monotonic()

    # Default rollback target is the last known-good adapter.
    target_version = (
        request.adapter_version
        if request.adapter_version is not None
        else lora_state.known_good_adapter_version or lora_state.previous_adapter_version
    )

    control_plane: Optional[Dict[str, Any]] = None
    if target_version is None:
        control_plane = await _call_lora_control_plane(
            method="POST",
            endpoint_path=config.lora_rollback_endpoint_path,
            payload={},
        )
        payload = control_plane.get("body")
        if isinstance(payload, dict):
            active_adapter = payload.get("active_adapter", {})
            if isinstance(active_adapter, dict):
                target_version = active_adapter.get("adapter_version")

        if target_version is None:
            raise HTTPException(
                status_code=409,
                detail="No known-good adapter available for rollback.",
            )
    else:
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not initialized")
        local_path = await storage.download_adapter(target_version)
        control_plane = await _call_lora_control_plane(
            method="POST",
            endpoint_path=config.lora_reload_endpoint_path,
            payload={"adapter_path": local_path, "adapter_version": target_version},
        )

    duration_ms = int((time.monotonic() - operation_started_at) * 1000)
    target_ms = int(config.lora_operation_timeout_seconds * 1000)
    rollback_within_target = duration_ms <= target_ms

    if not rollback_within_target:
        logger.warning(
            "LoRA rollback exceeded expected duration",
            extra={
                "duration_ms": duration_ms,
                "target_ms": target_ms,
                "from_version": from_version,
                "to_version": target_version,
            },
        )

    lora_state.previous_adapter_version = from_version
    lora_state.active_adapter_version = target_version
    lora_state.known_good_adapter_version = target_version
    lora_state.enabled = True
    lora_state.last_operation = "rollback"
    lora_state.last_reason = request.reason
    lora_state.updated_at = datetime.utcnow()

    _append_history(
        lora_state.rollback_history,
        {
            "timestamp": lora_state.updated_at.isoformat() + "Z",
            "from_version": from_version,
            "to_version": target_version,
            "reason": request.reason,
            "duration_ms": duration_ms,
            "target_ms": target_ms,
            "within_target": rollback_within_target,
            "control_plane_status": control_plane["status_code"] if control_plane else None,
        },
    )

    return LoRAStatusResponse(**lora_state.as_dict())


@app.post("/lora/activate", response_model=LoRAStatusResponse)
async def activate_lora(request: LoRAOperationRequest):
    """Activate a specific adapter version through hot-swap."""
    if not request.adapter_version:
        raise HTTPException(status_code=400, detail="adapter_version is required for activation")

    await _activate_adapter_version(
        version=request.adapter_version,
        reason=request.reason,
        operation="activated",
    )
    return LoRAStatusResponse(**lora_state.as_dict())


@app.post("/train", response_model=TrainingResponse)
async def trigger_training(request: TrainingRequest, background_tasks: BackgroundTasks):
    """Trigger a training job"""
    if not trainer:
        raise HTTPException(status_code=503, detail="Trainer not initialized")
    
    try:
        # Start training in background
        job_id = f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(
            "Training trigger received",
            extra={
                "job_id": job_id,
                "trigger_source": request.trigger_source,
                "audit_context": request.audit_context or {}
            }
        )

        background_tasks.add_task(
            trainer.train_from_feedback,
            days=request.days,
            ewc_lambda=request.ewc_lambda or config.ewc_lambda,
            force=request.force,
            job_id=job_id,
            dataset_id=request.dataset_id,
            author=request.author,
            validation_metrics=request.validation_metrics,
            golden_suite_path=request.golden_suite_path,
            golden_baseline_output_path=request.golden_baseline_output_path,
            golden_candidate_output_path=request.golden_candidate_output_path,
            golden_validation_required=request.golden_validation_required,
            golden_validation_enabled=request.golden_validation_enabled,
            golden_thresholds=request.golden_thresholds,
        )
        
        return TrainingResponse(
            status="started",
            message=f"Training job started with ID: {job_id}",
            job_id=job_id
        )
        
    except Exception as e:
        logger.error(f"Failed to start training: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/validation/golden-set")
async def validate_golden_set(request: GoldenValidationRequest):
    """Run explicit golden-set validation for candidate LoRA outputs."""
    if not trainer:
        raise HTTPException(status_code=503, detail="Trainer not initialized")

    try:
        report = await asyncio.to_thread(
            trainer.validate_golden_set,
            suite_path=request.suite_path,
            baseline_output_path=request.baseline_output_path,
            candidate_output_path=request.candidate_output_path,
            thresholds=request.thresholds,
        )
        return report
    except Exception as e:
        logger.error("Golden-set validation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/train/jsonl", response_model=TrainingResponse)
async def trigger_jsonl_training(request: JsonlTrainingRequest, background_tasks: BackgroundTasks):
    """Trigger LoRA training from a JSONL dataset."""
    if not trainer:
        raise HTTPException(status_code=503, detail="Trainer not initialized")

    try:
        job_id = f"train_jsonl_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        background_tasks.add_task(
            trainer.train_from_jsonl,
            dataset_path=request.dataset_path,
            learning_rate=request.learning_rate,
            epochs=request.epochs,
            batch_size=request.batch_size,
            job_id=job_id,
        )

        return TrainingResponse(
            status="started",
            message=f"JSONL training job started with ID: {job_id}",
            job_id=job_id
        )

    except Exception as e:
        logger.error(f"Failed to start JSONL training: {e}", exc_info=True)
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
async def list_adapters(model_name: Optional[str] = None, project: Optional[str] = None):
    """List all available LoRA adapters"""
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    
    try:
        adapters = await storage.list_adapters(model_name=model_name, project_name=project)
        return AdapterListResponse(
            adapters=adapters,
            total=len(adapters)
        )
        
    except Exception as e:
        logger.error(f"Failed to list adapters: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/adapters/{version}")
async def get_adapter_info(version: str, model_name: Optional[str] = None, project: Optional[str] = None):
    """Get information about a specific adapter"""
    if not storage:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    
    try:
        info = await storage.get_adapter_metadata(version, model_name=model_name, project_name=project)
        if not info:
            raise HTTPException(status_code=404, detail=f"Adapter {version} not found")
        
        return info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get adapter info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/adapters/{version}/deploy")
async def deploy_adapter(
    version: str,
    request: Optional[AdapterDeployRequest] = None,
    model_name: Optional[str] = None,
    project: Optional[str] = None,
):
    """Deploy an adapter to MAX Serve (hot-swap)"""
    if not lora_state.enabled:
        raise HTTPException(
            status_code=409,
            detail="LoRA is disabled by kill-switch. Re-enable via POST /lora/enable before deploying adapters."
        )
    
    try:
        operation = await _activate_adapter_version(
            version=version,
            reason=request.reason if request else "manual_deploy",
            operation="hot_swap",
            model_name=model_name,
            project=project,
        )
        
        return {
            "status": "deployed",
            "message": f"Adapter {version} deployed successfully",
            "version": version,
            "path": operation["path"],
            "from_version": operation["from_version"],
            "duration_ms": operation["duration_ms"],
            "known_good_adapter_version": lora_state.known_good_adapter_version,
            "control_plane": operation["control_plane"],
        }
        
    except Exception as e:
        logger.error(f"Failed to deploy adapter: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise
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
