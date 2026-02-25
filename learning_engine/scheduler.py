"""
Training Scheduler

Schedules automatic fine-tuning jobs based on cron expressions.
"""

import asyncio
import logging
from typing import Optional, Any
from datetime import datetime
from croniter import croniter

logger = logging.getLogger(__name__)


class TrainingScheduler:
    """
    Schedules automatic training jobs.
    
    Uses cron expressions to trigger training at specified intervals.
    """
    
    def __init__(self, trainer: Any, config: Any):
        """
        Initialize training scheduler.
        
        Args:
            trainer: LoRA trainer instance
            config: Configuration object
        """
        self.trainer = trainer
        self.config = config
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        
        logger.info(f"Training scheduler initialized with schedule: {config.train_schedule_cron}")
    
    async def start(self):
        """Start the scheduler"""
        if self.is_running:
            logger.warning("Scheduler already running")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._run_scheduler())
        logger.info("✓ Scheduler started")
    
    async def stop(self):
        """Stop the scheduler"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("✓ Scheduler stopped")
    
    async def _run_scheduler(self):
        """Main scheduler loop"""
        try:
            cron = croniter(self.config.train_schedule_cron, datetime.now())
            
            while self.is_running:
                # Calculate next run time
                next_run = cron.get_next(datetime)
                wait_seconds = (next_run - datetime.now()).total_seconds()
                
                logger.info(f"Next training scheduled at: {next_run} (in {wait_seconds:.0f}s)")
                
                # Wait until next run
                await asyncio.sleep(wait_seconds)
                
                if not self.is_running:
                    break
                
                # Trigger training
                logger.info("=" * 60)
                logger.info("Scheduled Training Job Starting")
                logger.info("=" * 60)
                
                try:
                    result = self.trainer.train_from_feedback(
                        days=7,
                        ewc_lambda=self.config.ewc_lambda,
                        force=False,
                        job_id=f"scheduled_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    )
                    
                    logger.info(f"Training result: {result['status']}")
                    
                except Exception as e:
                    logger.error(f"Scheduled training failed: {e}", exc_info=True)
                
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            self.is_running = False
