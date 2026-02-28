#!/usr/bin/env python3
"""
Collection Scheduler
Manages cron jobs for periodic data collection.
"""

import os
import logging
from typing import Dict, Any, List, Optional
import schedule
import time
from datetime import datetime
import yaml

from data_collectors.ingestion_queue import IngestionQueue

logger = logging.getLogger(__name__)


def _is_enabled(value: Optional[str], default: bool = True) -> bool:
    """Parse boolean-like configuration values."""
    if value is None:
        return default

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class CollectionScheduler:
    """Manages scheduled data collection jobs."""
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        queue: Optional[IngestionQueue] = None
    ):
        """
        Initialize collection scheduler.
        
        Args:
            config_path: Path to scheduler configuration file
            queue: IngestionQueue instance
        """
        self.config_path = config_path or os.getenv(
            "COLLECTION_CONFIG",
            "configs/collection-schedule.yaml"
        )
        self.queue = queue or IngestionQueue(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0"))
        )
        
        self.config = self._load_config()
        self.running = False
        
        logger.info("Initialized CollectionScheduler")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load scheduler configuration."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {self.config_path}")
                return config
            else:
                logger.warning(f"Config file not found: {self.config_path}, using defaults")
                return self._default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "schedules": [
                {
                    "name": "github_collection",
                    "source": "github",
                    "interval": "6h",
                    "config": {
                        "repo_name": os.getenv("GITHUB_DEFAULT_REPO"),
                        "hours_back": 6
                    }
                },
                {
                    "name": "notion_collection",
                    "source": "notion",
                    "interval": "4h",
                    "config": {
                        "hours_back": 4
                    }
                },
                {
                    "name": "slack_collection",
                    "source": "slack",
                    "interval": "2h",
                    "config": {
                        "channel_ids": os.getenv("SLACK_CHANNELS", "").split(","),
                        "hours_back": 2
                    }
                }
            ]
        }
    
    def setup_schedules(self):
        """Setup all scheduled jobs."""
        for job_config in self.config.get("schedules", []):
            self._schedule_job(job_config)
        
        logger.info(f"Setup {len(self.config.get('schedules', []))} scheduled jobs")
    
    def _schedule_job(self, job_config: Dict[str, Any]):
        """Schedule a single job."""
        name = job_config.get("name", "unknown")
        source = job_config.get("source")
        interval = job_config.get("interval", "1h")
        config = job_config.get("config", {})

        if not _is_enabled(job_config.get("enabled"), default=True):
            logger.info(f"Skipping disabled job: {name}")
            return

        if source == "github" and not _is_enabled(os.getenv("ENABLE_GITHUB_INGESTION"), default=True):
            logger.info("GitHub ingestion is disabled by ENABLE_GITHUB_INGESTION")
            return
        
        def job_func():
            logger.info(f"Running scheduled job: {name}")
            try:
                job_id = self.queue.enqueue_collection_job(source, config)
                logger.info(f"Enqueued job {name}: {job_id}")
            except Exception as e:
                logger.error(f"Error in scheduled job {name}: {e}")
        
        if interval.endswith('h'):
            hours = int(interval[:-1])
            schedule.every(hours).hours.do(job_func)
            logger.info(f"Scheduled {name} every {hours} hours")
        
        elif interval.endswith('m'):
            minutes = int(interval[:-1])
            schedule.every(minutes).minutes.do(job_func)
            logger.info(f"Scheduled {name} every {minutes} minutes")
        
        elif interval.endswith('d'):
            days = int(interval[:-1])
            schedule.every(days).days.do(job_func)
            logger.info(f"Scheduled {name} every {days} days")
        
        else:
            logger.warning(f"Unknown interval format: {interval}")
    
    def run(self):
        """Run the scheduler loop."""
        self.running = True
        logger.info("Starting scheduler loop")
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Scheduler stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(60)
    
    def stop(self):
        """Stop the scheduler."""
        self.running = False
        logger.info("Scheduler stopped")
    
    def trigger_immediate_collection(
        self,
        source: str,
        config: Dict[str, Any]
    ) -> str:
        """
        Trigger immediate collection job.
        
        Args:
            source: Data source
            config: Collection configuration
            
        Returns:
            Job ID
        """
        job_id = self.queue.enqueue_collection_job(source, config)
        logger.info(f"Triggered immediate collection for {source}: {job_id}")
        return job_id
    
    def get_scheduled_jobs(self) -> List[Dict[str, Any]]:
        """Get list of all scheduled jobs."""
        jobs = []
        
        for job in schedule.get_jobs():
            jobs.append({
                "job": str(job.job_func),
                "next_run": job.next_run.isoformat() if job.next_run else None,
                "interval": str(job.interval),
                "unit": job.unit
            })
        
        return jobs
