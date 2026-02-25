#!/usr/bin/env python3
"""
Ingestion Queue Service
Manages Redis Queue for buffering and processing ingestion tasks.
"""

import os
import logging
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
from redis import Redis
from rq import Queue, Worker
from rq.job import Job

logger = logging.getLogger(__name__)


class IngestionQueue:
    """Manages ingestion queue using Redis Queue."""
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        queue_name: str = "ingestion"
    ):
        """
        Initialize ingestion queue.
        
        Args:
            redis_host: Redis host
            redis_port: Redis port
            redis_db: Redis database number
            queue_name: Name of the queue
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.queue_name = queue_name
        
        self.redis_conn = Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=False
        )
        
        self.queue = Queue(queue_name, connection=self.redis_conn)
        
        logger.info(f"Initialized IngestionQueue: {queue_name} at {redis_host}:{redis_port}")
    
    def enqueue_documents(
        self,
        documents: List[Dict[str, Any]],
        priority: str = "normal"
    ) -> List[str]:
        """
        Enqueue documents for ingestion.
        
        Args:
            documents: List of documents to ingest
            priority: Priority level (high, normal, low)
            
        Returns:
            List of job IDs
        """
        job_ids = []
        
        for doc in documents:
            try:
                job = self.queue.enqueue(
                    'data_collectors.ingestion_worker.process_document',
                    doc,
                    job_timeout='5m',
                    result_ttl=3600,
                    failure_ttl=86400
                )
                job_ids.append(job.id)
                
            except Exception as e:
                logger.error(f"Error enqueuing document: {e}")
        
        logger.info(f"Enqueued {len(job_ids)} documents for ingestion")
        return job_ids
    
    def enqueue_collection_job(
        self,
        source: str,
        config: Dict[str, Any]
    ) -> str:
        """
        Enqueue a data collection job.
        
        Args:
            source: Data source (github, notion, slack)
            config: Collection configuration
            
        Returns:
            Job ID
        """
        job = self.queue.enqueue(
            'data_collectors.ingestion_worker.collect_and_process',
            source,
            config,
            job_timeout='30m',
            result_ttl=3600,
            failure_ttl=86400
        )
        
        logger.info(f"Enqueued collection job for {source}: {job.id}")
        return job.id
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get status of a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job status dictionary
        """
        try:
            job = Job.fetch(job_id, connection=self.redis_conn)
            
            return {
                "job_id": job.id,
                "status": job.get_status(),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
                "result": job.result,
                "exc_info": job.exc_info
            }
            
        except Exception as e:
            logger.error(f"Error fetching job {job_id}: {e}")
            return {"job_id": job_id, "status": "unknown", "error": str(e)}
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.
        
        Returns:
            Queue stats dictionary
        """
        return {
            "queue_name": self.queue_name,
            "queued_jobs": len(self.queue),
            "started_jobs": self.queue.started_job_registry.count,
            "finished_jobs": self.queue.finished_job_registry.count,
            "failed_jobs": self.queue.failed_job_registry.count,
            "deferred_jobs": self.queue.deferred_job_registry.count,
            "scheduled_jobs": self.queue.scheduled_job_registry.count
        }
    
    def clear_queue(self):
        """Clear all jobs from the queue."""
        self.queue.empty()
        logger.info(f"Cleared queue: {self.queue_name}")
    
    def create_worker(
        self,
        num_workers: int = 1
    ) -> List[Worker]:
        """
        Create worker instances.
        
        Args:
            num_workers: Number of workers to create
            
        Returns:
            List of worker instances
        """
        workers = []
        
        for i in range(num_workers):
            worker = Worker(
                [self.queue],
                connection=self.redis_conn,
                name=f"ingestion-worker-{i}"
            )
            workers.append(worker)
        
        logger.info(f"Created {num_workers} workers for queue {self.queue_name}")
        return workers
