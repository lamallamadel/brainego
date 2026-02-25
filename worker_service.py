#!/usr/bin/env python3
"""
Worker Service
Runs RQ workers to process ingestion jobs.
"""

import os
import logging
import signal
import sys
from typing import List

from rq import Worker
from data_collectors.ingestion_queue import IngestionQueue

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info("Shutdown signal received, stopping workers...")
    sys.exit(0)


def main():
    """Run worker service."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_db = int(os.getenv("REDIS_DB", "0"))
    num_workers = int(os.getenv("NUM_WORKERS", "4"))
    
    logger.info(f"Starting {num_workers} ingestion workers")
    logger.info(f"Redis: {redis_host}:{redis_port}/{redis_db}")
    
    ingestion_queue = IngestionQueue(
        redis_host=redis_host,
        redis_port=redis_port,
        redis_db=redis_db
    )
    
    workers = ingestion_queue.create_worker(num_workers=1)
    
    if workers:
        worker = workers[0]
        logger.info(f"Starting worker: {worker.name}")
        worker.work()
    else:
        logger.error("Failed to create worker")
        sys.exit(1)


if __name__ == "__main__":
    main()
