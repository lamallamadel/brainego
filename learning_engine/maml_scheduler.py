"""
MAML Monthly CronJob Scheduler

Schedules monthly meta-training runs for MAML meta-learning.
Default: First day of each month at 2 AM.
"""

import logging
import asyncio
from typing import Optional, Callable
from datetime import datetime
from croniter import croniter

logger = logging.getLogger(__name__)


class MAMLScheduler:
    """
    Schedules periodic MAML meta-training.
    
    Default schedule: Monthly (1st day of month at 2 AM)
    Cron format: "0 2 1 * *"
    """
    
    def __init__(
        self,
        cron_schedule: str = "0 2 1 * *",  # Monthly: 2 AM on 1st of month
        callback: Optional[Callable] = None
    ):
        """
        Initialize MAML scheduler.
        
        Args:
            cron_schedule: Cron schedule string
            callback: Async callback function for meta-training
        """
        self.cron_schedule = cron_schedule
        self.callback = callback
        self.is_running = False
        self._task = None
        
        # Validate cron schedule
        try:
            croniter(cron_schedule)
            logger.info(f"MAML scheduler initialized with schedule: {cron_schedule}")
        except Exception as e:
            logger.error(f"Invalid cron schedule: {e}")
            raise
    
    async def start(self):
        """Start the scheduler"""
        if self.is_running:
            logger.warning("Scheduler already running")
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._run_schedule())
        logger.info("✓ MAML scheduler started")
    
    async def stop(self):
        """Stop the scheduler"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("✓ MAML scheduler stopped")
    
    async def _run_schedule(self):
        """Run the scheduled tasks"""
        while self.is_running:
            try:
                # Calculate next run time
                now = datetime.now()
                cron = croniter(self.cron_schedule, now)
                next_run = cron.get_next(datetime)
                
                wait_seconds = (next_run - now).total_seconds()
                
                logger.info(
                    f"Next MAML meta-training scheduled for: {next_run.isoformat()} "
                    f"(in {wait_seconds/3600:.1f} hours)"
                )
                
                # Wait until next run
                await asyncio.sleep(wait_seconds)
                
                # Execute callback
                if self.callback and self.is_running:
                    logger.info("=" * 60)
                    logger.info("MAML Meta-Training: Scheduled Execution")
                    logger.info("=" * 60)
                    
                    try:
                        await self.callback()
                        logger.info("✓ Scheduled meta-training completed")
                    except Exception as e:
                        logger.error(f"Scheduled meta-training failed: {e}", exc_info=True)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    def get_next_run_time(self) -> Optional[datetime]:
        """Get the next scheduled run time"""
        try:
            cron = croniter(self.cron_schedule, datetime.now())
            return cron.get_next(datetime)
        except Exception as e:
            logger.error(f"Failed to get next run time: {e}")
            return None
    
    def get_schedule_info(self) -> dict:
        """Get scheduler information"""
        next_run = self.get_next_run_time()
        
        return {
            "is_running": self.is_running,
            "cron_schedule": self.cron_schedule,
            "next_run": next_run.isoformat() if next_run else None,
            "description": self._get_schedule_description()
        }
    
    def _get_schedule_description(self) -> str:
        """Get human-readable schedule description"""
        if self.cron_schedule == "0 2 1 * *":
            return "Monthly (1st day at 2 AM)"
        elif self.cron_schedule == "0 2 * * 1":
            return "Weekly (Monday at 2 AM)"
        elif self.cron_schedule == "0 2 * * *":
            return "Daily (2 AM)"
        else:
            return f"Custom: {self.cron_schedule}"
    
    async def trigger_now(self):
        """Manually trigger meta-training immediately"""
        if self.callback:
            logger.info("Manual meta-training trigger")
            try:
                await self.callback()
                logger.info("✓ Manual meta-training completed")
            except Exception as e:
                logger.error(f"Manual meta-training failed: {e}", exc_info=True)
        else:
            logger.warning("No callback configured")
