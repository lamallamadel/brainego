"""
Adaptation Metrics Tracking

Tracks MAML adaptation metrics with target: <10 steps to 80% accuracy.
Stores metrics in PostgreSQL and provides analytics.
"""

import logging
import psycopg2
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class AdaptationMetricsTracker:
    """
    Tracks and analyzes MAML adaptation performance.
    
    Key metrics:
    - Steps to target accuracy (target: <10 steps to 80%)
    - Final accuracy achieved
    - Adaptation loss curve
    - Task-specific performance
    """
    
    def __init__(
        self,
        postgres_host: str,
        postgres_port: int,
        postgres_db: str,
        postgres_user: str,
        postgres_password: str
    ):
        """Initialize metrics tracker"""
        self.db_config = {
            "host": postgres_host,
            "port": postgres_port,
            "database": postgres_db,
            "user": postgres_user,
            "password": postgres_password
        }
        
        self._ensure_tables()
        
        logger.info(f"Adaptation metrics tracker initialized")
    
    def _ensure_tables(self):
        """Ensure metrics tables exist"""
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        # Create adaptation_metrics table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS maml_adaptation_metrics (
            id SERIAL PRIMARY KEY,
            task_id VARCHAR(255) NOT NULL,
            task_type VARCHAR(100),
            project VARCHAR(255),
            meta_version VARCHAR(50),
            steps_to_target INTEGER,
            target_reached BOOLEAN NOT NULL,
            target_accuracy FLOAT NOT NULL,
            final_accuracy FLOAT NOT NULL,
            final_loss FLOAT NOT NULL,
            adaptation_steps JSONB,
            losses JSONB,
            accuracies JSONB,
            num_support_samples INTEGER,
            num_query_samples INTEGER,
            metadata JSONB DEFAULT '{}'::JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create meta_training_metrics table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS maml_meta_training_metrics (
            id SERIAL PRIMARY KEY,
            version VARCHAR(50) NOT NULL,
            num_tasks INTEGER NOT NULL,
            num_outer_steps INTEGER NOT NULL,
            num_inner_steps INTEGER NOT NULL,
            final_meta_loss FLOAT NOT NULL,
            mean_task_accuracy FLOAT NOT NULL,
            meta_losses JSONB,
            task_accuracies JSONB,
            training_duration_seconds FLOAT,
            metadata JSONB DEFAULT '{}'::JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create indexes
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_adaptation_task_id 
        ON maml_adaptation_metrics(task_id)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_adaptation_project 
        ON maml_adaptation_metrics(project)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_adaptation_target_reached 
        ON maml_adaptation_metrics(target_reached)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_adaptation_created_at 
        ON maml_adaptation_metrics(created_at)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_meta_training_version 
        ON maml_meta_training_metrics(version)
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("✓ Metrics tables ensured")
    
    def record_adaptation(
        self,
        task_id: str,
        metrics: Dict[str, Any],
        task_metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record adaptation metrics for a task.
        
        Args:
            task_id: Task identifier
            metrics: Adaptation metrics dictionary
            task_metadata: Additional task metadata
        """
        logger.info(f"Recording adaptation metrics for task: {task_id}")
        
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        metadata = task_metadata or {}
        
        cursor.execute("""
        INSERT INTO maml_adaptation_metrics (
            task_id,
            task_type,
            project,
            meta_version,
            steps_to_target,
            target_reached,
            target_accuracy,
            final_accuracy,
            final_loss,
            adaptation_steps,
            losses,
            accuracies,
            num_support_samples,
            num_query_samples,
            metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            task_id,
            metadata.get('task_type'),
            metadata.get('project'),
            metadata.get('meta_version'),
            metrics.get('steps_to_target'),
            metrics.get('target_reached', False),
            metrics.get('target_accuracy', 0.80),
            metrics.get('final_accuracy', 0.0),
            metrics.get('final_loss', float('inf')),
            json.dumps(metrics.get('steps', [])),
            json.dumps(metrics.get('losses', [])),
            json.dumps(metrics.get('accuracies', [])),
            metadata.get('num_support_samples'),
            metadata.get('num_query_samples'),
            json.dumps(metadata)
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"✓ Adaptation metrics recorded")
    
    def record_meta_training(
        self,
        version: str,
        metrics: Dict[str, Any],
        training_metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record meta-training metrics.
        
        Args:
            version: Meta-weights version
            metrics: Meta-training metrics
            training_metadata: Additional metadata
        """
        logger.info(f"Recording meta-training metrics for version: {version}")
        
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        metadata = training_metadata or {}
        
        cursor.execute("""
        INSERT INTO maml_meta_training_metrics (
            version,
            num_tasks,
            num_outer_steps,
            num_inner_steps,
            final_meta_loss,
            mean_task_accuracy,
            meta_losses,
            task_accuracies,
            training_duration_seconds,
            metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            version,
            metadata.get('num_tasks', 0),
            metadata.get('num_outer_steps', 0),
            metadata.get('num_inner_steps', 0),
            metrics.get('final_meta_loss', 0.0),
            metrics.get('mean_task_accuracy', 0.0),
            json.dumps(metrics.get('meta_losses', [])),
            json.dumps(metrics.get('task_accuracies', [])),
            metadata.get('training_duration_seconds'),
            json.dumps(metadata)
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"✓ Meta-training metrics recorded")
    
    def get_adaptation_statistics(
        self,
        days: int = 30,
        project: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get adaptation statistics.
        
        Args:
            days: Number of days to look back
            project: Filter by project
        
        Returns:
            Statistics dictionary
        """
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        query = """
        SELECT 
            COUNT(*) as total_adaptations,
            COUNT(*) FILTER (WHERE target_reached) as successful_adaptations,
            AVG(steps_to_target) FILTER (WHERE target_reached) as avg_steps_to_target,
            MIN(steps_to_target) FILTER (WHERE target_reached) as min_steps_to_target,
            MAX(steps_to_target) FILTER (WHERE target_reached) as max_steps_to_target,
            AVG(final_accuracy) as avg_final_accuracy,
            MAX(final_accuracy) as max_final_accuracy,
            MIN(final_accuracy) as min_final_accuracy
        FROM maml_adaptation_metrics
        WHERE created_at >= NOW() - INTERVAL '%s days'
        """
        
        params = [days]
        
        if project:
            query += " AND project = %s"
            params.append(project)
        
        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        
        stats = {
            "total_adaptations": row[0] or 0,
            "successful_adaptations": row[1] or 0,
            "success_rate": (row[1] / row[0]) if row[0] else 0.0,
            "avg_steps_to_target": float(row[2]) if row[2] else None,
            "min_steps_to_target": row[3],
            "max_steps_to_target": row[4],
            "avg_final_accuracy": float(row[5]) if row[5] else 0.0,
            "max_final_accuracy": float(row[6]) if row[6] else 0.0,
            "min_final_accuracy": float(row[7]) if row[7] else 0.0,
            "target_met": (row[2] or 11) < 10 if row[2] else False  # <10 steps target
        }
        
        cursor.close()
        conn.close()
        
        return stats
    
    def get_project_adaptation_performance(
        self,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get adaptation performance by project.
        
        Args:
            days: Number of days to look back
        
        Returns:
            List of project performance statistics
        """
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        query = """
        SELECT 
            project,
            COUNT(*) as total_adaptations,
            COUNT(*) FILTER (WHERE target_reached) as successful_adaptations,
            AVG(steps_to_target) FILTER (WHERE target_reached) as avg_steps_to_target,
            AVG(final_accuracy) as avg_final_accuracy
        FROM maml_adaptation_metrics
        WHERE created_at >= NOW() - INTERVAL '%s days'
        AND project IS NOT NULL
        GROUP BY project
        ORDER BY avg_final_accuracy DESC
        """
        
        cursor.execute(query, (days,))
        rows = cursor.fetchall()
        
        projects = []
        for row in rows:
            projects.append({
                "project": row[0],
                "total_adaptations": row[1],
                "successful_adaptations": row[2],
                "success_rate": row[2] / row[1] if row[1] else 0.0,
                "avg_steps_to_target": float(row[3]) if row[3] else None,
                "avg_final_accuracy": float(row[4]) if row[4] else 0.0
            })
        
        cursor.close()
        conn.close()
        
        return projects
    
    def get_recent_adaptations(
        self,
        limit: int = 10,
        project: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent adaptation records.
        
        Args:
            limit: Maximum number of records
            project: Filter by project
        
        Returns:
            List of adaptation records
        """
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        query = """
        SELECT 
            task_id,
            project,
            steps_to_target,
            target_reached,
            final_accuracy,
            final_loss,
            created_at
        FROM maml_adaptation_metrics
        WHERE 1=1
        """
        
        params = []
        
        if project:
            query += " AND project = %s"
            params.append(project)
        
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        adaptations = []
        for row in rows:
            adaptations.append({
                "task_id": row[0],
                "project": row[1],
                "steps_to_target": row[2],
                "target_reached": row[3],
                "final_accuracy": float(row[4]),
                "final_loss": float(row[5]),
                "created_at": row[6].isoformat() if row[6] else None
            })
        
        cursor.close()
        conn.close()
        
        return adaptations
    
    def check_target_performance(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Check if MAML is meeting the target performance (<10 steps to 80% accuracy).
        
        Args:
            days: Number of days to look back
        
        Returns:
            Performance check results
        """
        stats = self.get_adaptation_statistics(days=days)
        
        target_met = (
            stats['avg_steps_to_target'] is not None and
            stats['avg_steps_to_target'] < 10 and
            stats['avg_final_accuracy'] >= 0.80
        )
        
        return {
            "target_met": target_met,
            "avg_steps_to_target": stats['avg_steps_to_target'],
            "target_steps": 10,
            "avg_final_accuracy": stats['avg_final_accuracy'],
            "target_accuracy": 0.80,
            "success_rate": stats['success_rate'],
            "total_adaptations": stats['total_adaptations'],
            "days_evaluated": days,
            "status": "✓ Target met" if target_met else "✗ Target not met"
        }
