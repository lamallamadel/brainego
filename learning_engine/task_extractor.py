"""
Per-Project Task Extractor

Extracts and organizes feedback data into project-specific tasks for MAML meta-learning.
Each project becomes a separate task, enabling the model to learn task-agnostic representations.
"""

import logging
import psycopg2
import json
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class TaskExtractor:
    """
    Extracts per-project tasks from feedback database.
    
    Tasks are organized by:
    - Project identifier (from feedback metadata)
    - Intent/task type
    - Time period
    
    This enables MAML to learn from diverse tasks and adapt quickly to new projects.
    """
    
    def __init__(
        self,
        postgres_host: str,
        postgres_port: int,
        postgres_db: str,
        postgres_user: str,
        postgres_password: str
    ):
        """
        Initialize task extractor.
        
        Args:
            postgres_host: PostgreSQL host
            postgres_port: PostgreSQL port
            postgres_db: Database name
            postgres_user: Database user
            postgres_password: Database password
        """
        self.db_config = {
            "host": postgres_host,
            "port": postgres_port,
            "database": postgres_db,
            "user": postgres_user,
            "password": postgres_password
        }
        
        logger.info(f"Task extractor initialized: {postgres_host}:{postgres_port}/{postgres_db}")
    
    def extract_project_tasks(
        self,
        days: int = 30,
        min_samples_per_project: int = 20,
        positive_only: bool = False
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract tasks grouped by project.
        
        Args:
            days: Number of days to look back
            min_samples_per_project: Minimum samples required per project
            positive_only: If True, only include positive feedback
        
        Returns:
            Dictionary mapping project_id -> list of samples
        """
        logger.info(f"Extracting project tasks from last {days} days...")
        
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        # Query feedback grouped by project
        query = """
        SELECT 
            project,
            query,
            response,
            rating,
            intent,
            metadata,
            timestamp
        FROM feedback
        WHERE timestamp >= NOW() - INTERVAL '%s days'
        AND project IS NOT NULL
        """
        
        if positive_only:
            query += " AND rating = 1"
        
        query += " ORDER BY project, timestamp DESC"
        
        cursor.execute(query, (days,))
        rows = cursor.fetchall()
        
        # Group by project
        project_tasks = defaultdict(list)
        
        for row in rows:
            project = row[0]
            query_text = row[1]
            response_text = row[2]
            rating = row[3]
            intent = row[4]
            metadata = row[5] if isinstance(row[5], dict) else json.loads(row[5] or '{}')
            timestamp = row[6]
            
            # Create sample
            sample = {
                'input': query_text,
                'output': response_text,
                'rating': rating,
                'intent': intent,
                'metadata': metadata,
                'timestamp': timestamp.isoformat() if timestamp else None,
                'weight': 2.0 if rating == 1 else 0.5
            }
            
            project_tasks[project].append(sample)
        
        cursor.close()
        conn.close()
        
        # Filter projects with insufficient samples
        filtered_tasks = {
            project: samples
            for project, samples in project_tasks.items()
            if len(samples) >= min_samples_per_project
        }
        
        logger.info(f"✓ Extracted {len(filtered_tasks)} project tasks")
        for project, samples in filtered_tasks.items():
            positive = sum(1 for s in samples if s['rating'] == 1)
            logger.info(f"  {project}: {len(samples)} samples ({positive} positive)")
        
        return filtered_tasks

    def build_project_task_splits(
        self,
        project_tasks: Dict[str, List[Dict[str, Any]]],
        support_ratio: float = 0.8,
        min_support_samples: int = 1,
        min_query_samples: int = 1
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build support/query splits for each project task.

        Args:
            project_tasks: Mapping of project -> interaction samples
            support_ratio: Target ratio of samples in support set
            min_support_samples: Lower bound for support set size
            min_query_samples: Lower bound for query set size

        Returns:
            Mapping of project -> task descriptor with support/query splits
        """
        project_task_splits: Dict[str, Dict[str, Any]] = {}

        for project, interactions in project_tasks.items():
            if len(interactions) < (min_support_samples + min_query_samples):
                logger.debug(
                    "Skipping project '%s': not enough samples to build split (%d)",
                    project,
                    len(interactions),
                )
                continue

            shuffled = interactions.copy()
            import random
            random.shuffle(shuffled)

            split_idx = int(len(shuffled) * support_ratio)
            split_idx = max(min_support_samples, split_idx)
            split_idx = min(len(shuffled) - min_query_samples, split_idx)

            support_set = shuffled[:split_idx]
            query_set = shuffled[split_idx:]

            project_task_splits[project] = {
                "task_id": f"project_{project}",
                "project": project,
                "interactions": shuffled,
                "support_set": support_set,
                "query_set": query_set,
                "support_size": len(support_set),
                "query_size": len(query_set),
            }

        logger.info("✓ Built support/query splits for %d project tasks", len(project_task_splits))
        return project_task_splits

    def extract_project_task_splits(
        self,
        days: int = 30,
        min_samples_per_project: int = 20,
        positive_only: bool = False,
        support_ratio: float = 0.8,
        min_support_samples: int = 1,
        min_query_samples: int = 1,
    ) -> Dict[str, Dict[str, Any]]:
        """Extract per-project interaction tasks and materialize support/query sets."""
        project_tasks = self.extract_project_tasks(
            days=days,
            min_samples_per_project=min_samples_per_project,
            positive_only=positive_only,
        )

        return self.build_project_task_splits(
            project_tasks=project_tasks,
            support_ratio=support_ratio,
            min_support_samples=min_support_samples,
            min_query_samples=min_query_samples,
        )
    
    def extract_intent_tasks(
        self,
        days: int = 30,
        min_samples_per_intent: int = 20
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract tasks grouped by intent/task type.
        
        Args:
            days: Number of days to look back
            min_samples_per_intent: Minimum samples required per intent
        
        Returns:
            Dictionary mapping intent -> list of samples
        """
        logger.info(f"Extracting intent tasks from last {days} days...")
        
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        query = """
        SELECT 
            intent,
            query,
            response,
            rating,
            project,
            metadata,
            timestamp
        FROM feedback
        WHERE timestamp >= NOW() - INTERVAL '%s days'
        AND intent IS NOT NULL
        ORDER BY intent, timestamp DESC
        """
        
        cursor.execute(query, (days,))
        rows = cursor.fetchall()
        
        # Group by intent
        intent_tasks = defaultdict(list)
        
        for row in rows:
            intent = row[0]
            query_text = row[1]
            response_text = row[2]
            rating = row[3]
            project = row[4]
            metadata = row[5] if isinstance(row[5], dict) else json.loads(row[5] or '{}')
            timestamp = row[6]
            
            sample = {
                'input': query_text,
                'output': response_text,
                'rating': rating,
                'project': project,
                'metadata': metadata,
                'timestamp': timestamp.isoformat() if timestamp else None,
                'weight': 2.0 if rating == 1 else 0.5
            }
            
            intent_tasks[intent].append(sample)
        
        cursor.close()
        conn.close()
        
        # Filter intents with insufficient samples
        filtered_tasks = {
            intent: samples
            for intent, samples in intent_tasks.items()
            if len(samples) >= min_samples_per_intent
        }
        
        logger.info(f"✓ Extracted {len(filtered_tasks)} intent tasks")
        for intent, samples in filtered_tasks.items():
            positive = sum(1 for s in samples if s['rating'] == 1)
            logger.info(f"  {intent}: {len(samples)} samples ({positive} positive)")
        
        return filtered_tasks
    
    def extract_temporal_tasks(
        self,
        days: int = 90,
        task_window_days: int = 7,
        min_samples_per_window: int = 15
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract tasks by temporal windows (weekly buckets).
        
        Args:
            days: Total number of days to look back
            task_window_days: Size of each temporal window
            min_samples_per_window: Minimum samples required per window
        
        Returns:
            Dictionary mapping time_window -> list of samples
        """
        logger.info(f"Extracting temporal tasks: {days} days, {task_window_days}-day windows")
        
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        query = """
        SELECT 
            query,
            response,
            rating,
            intent,
            project,
            metadata,
            timestamp
        FROM feedback
        WHERE timestamp >= NOW() - INTERVAL '%s days'
        ORDER BY timestamp DESC
        """
        
        cursor.execute(query, (days,))
        rows = cursor.fetchall()
        
        # Group by time windows
        temporal_tasks = defaultdict(list)
        
        for row in rows:
            query_text = row[0]
            response_text = row[1]
            rating = row[2]
            intent = row[3]
            project = row[4]
            metadata = row[5] if isinstance(row[5], dict) else json.loads(row[5] or '{}')
            timestamp = row[6]
            
            # Calculate window bucket
            if timestamp:
                days_ago = (datetime.now() - timestamp.replace(tzinfo=None)).days
                window_id = days_ago // task_window_days
                window_name = f"window_{window_id:02d}"
                
                sample = {
                    'input': query_text,
                    'output': response_text,
                    'rating': rating,
                    'intent': intent,
                    'project': project,
                    'metadata': metadata,
                    'timestamp': timestamp.isoformat(),
                    'weight': 2.0 if rating == 1 else 0.5
                }
                
                temporal_tasks[window_name].append(sample)
        
        cursor.close()
        conn.close()
        
        # Filter windows with insufficient samples
        filtered_tasks = {
            window: samples
            for window, samples in temporal_tasks.items()
            if len(samples) >= min_samples_per_window
        }
        
        logger.info(f"✓ Extracted {len(filtered_tasks)} temporal tasks")
        for window, samples in sorted(filtered_tasks.items()):
            positive = sum(1 for s in samples if s['rating'] == 1)
            logger.info(f"  {window}: {len(samples)} samples ({positive} positive)")
        
        return filtered_tasks
    
    def extract_all_tasks(
        self,
        days: int = 30,
        min_samples: int = 20,
        strategy: str = "project"
    ) -> List[List[Dict[str, str]]]:
        """
        Extract all tasks using specified strategy.
        
        Args:
            days: Number of days to look back
            min_samples: Minimum samples per task
            strategy: Extraction strategy ("project", "intent", "temporal", "mixed")
        
        Returns:
            List of task datasets
        """
        logger.info(f"Extracting all tasks: strategy={strategy}, days={days}")
        
        if strategy == "project":
            task_dict = self.extract_project_task_splits(
                days=days,
                min_samples_per_project=min_samples,
            )
        elif strategy == "intent":
            task_dict = self.extract_intent_tasks(days, min_samples)
        elif strategy == "temporal":
            task_dict = self.extract_temporal_tasks(days, min_samples_per_window=min_samples)
        elif strategy == "mixed":
            # Combine multiple strategies
            project_tasks = self.extract_project_task_splits(
                days=days,
                min_samples_per_project=min_samples,
            )
            intent_tasks = self.extract_intent_tasks(days, min_samples)
            
            # Merge with unique keys
            task_dict = {}
            for k, v in project_tasks.items():
                task_dict[f"project_{k}"] = v
            for k, v in intent_tasks.items():
                task_dict[f"intent_{k}"] = v
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        
        # Convert to list of task datasets
        task_list = list(task_dict.values())
        
        logger.info(f"✓ Extracted {len(task_list)} total tasks")
        
        return task_list
    
    def get_project_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get statistics about projects in the database.
        
        Args:
            days: Number of days to look back
        
        Returns:
            Statistics dictionary
        """
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        query = """
        SELECT 
            project,
            COUNT(*) as total_samples,
            COUNT(*) FILTER (WHERE rating = 1) as positive_samples,
            COUNT(DISTINCT intent) as unique_intents,
            MIN(timestamp) as earliest,
            MAX(timestamp) as latest
        FROM feedback
        WHERE timestamp >= NOW() - INTERVAL '%s days'
        AND project IS NOT NULL
        GROUP BY project
        ORDER BY total_samples DESC
        """
        
        cursor.execute(query, (days,))
        rows = cursor.fetchall()
        
        statistics = {
            "total_projects": len(rows),
            "projects": []
        }
        
        for row in rows:
            project_stats = {
                "project": row[0],
                "total_samples": row[1],
                "positive_samples": row[2],
                "unique_intents": row[3],
                "accuracy": row[2] / row[1] if row[1] > 0 else 0.0,
                "earliest": row[4].isoformat() if row[4] else None,
                "latest": row[5].isoformat() if row[5] else None
            }
            statistics["projects"].append(project_stats)
        
        cursor.close()
        conn.close()
        
        return statistics
    
    def get_failed_plans(
        self,
        days: int = 30,
        rating_threshold: int = -1
    ) -> List[Dict[str, str]]:
        """
        Extract failed plans (negative feedback) for replay buffer.
        
        Args:
            days: Number of days to look back
            rating_threshold: Rating threshold for failures (default: -1)
        
        Returns:
            List of failed plan samples
        """
        logger.info(f"Extracting failed plans from last {days} days...")
        
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        query = """
        SELECT 
            query,
            response,
            rating,
            intent,
            project,
            metadata,
            timestamp
        FROM feedback
        WHERE timestamp >= NOW() - INTERVAL '%s days'
        AND rating <= %s
        ORDER BY timestamp DESC
        """
        
        cursor.execute(query, (days, rating_threshold))
        rows = cursor.fetchall()
        
        failed_plans = []
        
        for row in rows:
            sample = {
                'input': row[0],
                'output': row[1],
                'rating': row[2],
                'intent': row[3],
                'project': row[4],
                'metadata': row[5] if isinstance(row[5], dict) else json.loads(row[5] or '{}'),
                'timestamp': row[6].isoformat() if row[6] else None,
                'weight': 3.0  # 3x weight for failed plans
            }
            failed_plans.append(sample)
        
        cursor.close()
        conn.close()
        
        logger.info(f"✓ Extracted {len(failed_plans)} failed plans")
        
        return failed_plans
