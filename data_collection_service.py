#!/usr/bin/env python3
"""
Data Collection Service
Main service that integrates webhooks, scheduler, and workers.
"""

import os
import logging
import asyncio
from typing import Optional
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import multiprocessing

from data_collectors.webhook_endpoints import router as webhook_router
from data_collectors.scheduler import CollectionScheduler
from data_collectors.ingestion_queue import IngestionQueue

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Data Collection Service",
    description="Automated data collection pipeline with webhooks and scheduled jobs",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)

scheduler: Optional[CollectionScheduler] = None
ingestion_queue: Optional[IngestionQueue] = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global scheduler, ingestion_queue
    
    logger.info("Starting Data Collection Service")
    
    ingestion_queue = IngestionQueue(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        redis_db=int(os.getenv("REDIS_DB", "0"))
    )
    
    scheduler = CollectionScheduler(queue=ingestion_queue)
    scheduler.setup_schedules()
    
    asyncio.create_task(run_scheduler())
    
    logger.info("Data Collection Service started")


async def run_scheduler():
    """Run scheduler in background task."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scheduler.run)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "data-collection",
        "scheduler_running": scheduler.running if scheduler else False
    }


@app.get("/stats")
async def get_stats():
    """Get service statistics."""
    queue_stats = ingestion_queue.get_queue_stats() if ingestion_queue else {}
    scheduled_jobs = scheduler.get_scheduled_jobs() if scheduler else []
    
    return {
        "queue_stats": queue_stats,
        "scheduled_jobs": scheduled_jobs,
        "scheduler_running": scheduler.running if scheduler else False
    }


@app.post("/trigger/{source}")
async def trigger_collection(source: str, config: dict):
    """Manually trigger a collection job."""
    if not scheduler:
        return {"error": "Scheduler not initialized"}
    
    job_id = scheduler.trigger_immediate_collection(source, config)
    
    return {
        "status": "triggered",
        "source": source,
        "job_id": job_id
    }


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a specific job."""
    if not ingestion_queue:
        return {"error": "Queue not initialized"}
    
    return ingestion_queue.get_job_status(job_id)


if __name__ == "__main__":
    port = int(os.getenv("DATA_COLLECTION_PORT", "8002"))
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
