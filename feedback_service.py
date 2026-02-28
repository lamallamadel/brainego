#!/usr/bin/env python3
"""
Feedback Collection Service for AI Platform
Handles thumbs-up/down feedback, PostgreSQL storage, accuracy tracking,
and weekly fine-tuning dataset export.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)


class FeedbackService:
    """
    Service for collecting and managing feedback on AI model responses.
    
    Features:
    - Thumbs-up/down rating collection
    - PostgreSQL storage with metadata
    - Per-model accuracy calculation by intent and project
    - Weekly fine-tuning dataset export with weighted samples
    """
    
    def __init__(
        self,
        db_host: str = "localhost",
        db_port: int = 5432,
        db_name: str = "ai_platform",
        db_user: str = "ai_user",
        db_password: str = "ai_password",
        pool_min_conn: int = 2,
        pool_max_conn: int = 10
    ):
        """
        Initialize Feedback Service with PostgreSQL connection pool.
        
        Args:
            db_host: PostgreSQL host
            db_port: PostgreSQL port
            db_name: Database name
            db_user: Database user
            db_password: Database password
            pool_min_conn: Minimum connections in pool
            pool_max_conn: Maximum connections in pool
        """
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        
        try:
            self.pool = ThreadedConnectionPool(
                pool_min_conn,
                pool_max_conn,
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password
            )
            logger.info(
                f"Feedback Service initialized with PostgreSQL pool "
                f"({pool_min_conn}-{pool_max_conn} connections)"
            )
        except Exception as e:
            logger.error(f"Failed to initialize database connection pool: {e}")
            raise
    
    def _get_connection(self):
        """Get a connection from the pool."""
        return self.pool.getconn()
    
    def _return_connection(self, conn):
        """Return a connection to the pool."""
        self.pool.putconn(conn)
    
    def add_feedback(
        self,
        query: str,
        response: str,
        model: str,
        rating: int,
        reason: Optional[str] = None,
        memory_used: int = 0,
        tools_called: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        intent: Optional[str] = None,
        project: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add feedback for a model response.
        
        Args:
            query: Original user query
            response: Model's response
            model: Model identifier
            rating: Feedback rating (1 for thumbs-up, -1 for thumbs-down)
            reason: Optional textual reason provided by the user
            memory_used: Memory usage in bytes
            tools_called: List of tools/functions called during response
            user_id: Optional user identifier
            session_id: Optional session identifier
            intent: Detected intent (e.g., "code", "reasoning", "general")
            project: Project identifier
            metadata: Additional metadata as JSON
        
        Returns:
            Dictionary with feedback_id and status
        """
        if rating not in [1, -1]:
            raise ValueError("Rating must be 1 (thumbs-up) or -1 (thumbs-down)")
        
        feedback_id = str(uuid.uuid4())
        tools = tools_called or []
        meta = metadata or {}
        
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feedback (
                        feedback_id, query, response, model, memory_used,
                        tools_called, rating, reason, user_id, session_id,
                        intent, project, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id, timestamp
                    """,
                    (
                        feedback_id, query, response, model, memory_used,
                        tools, rating, reason, user_id, session_id,
                        intent, project, json.dumps(meta)
                    )
                )
                result = cur.fetchone()
                conn.commit()
                
                logger.info(
                    f"Feedback added: {feedback_id} "
                    f"[model={model}, rating={rating}, intent={intent}]"
                )
                
                return {
                    "status": "success",
                    "feedback_id": feedback_id,
                    "id": result[0],
                    "timestamp": result[1].isoformat(),
                    "rating": rating,
                    "model": model
                }
        except Exception as e:
            conn.rollback()
            logger.error(f"Error adding feedback: {e}")
            raise
        finally:
            self._return_connection(conn)
    
    def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve feedback by ID.
        
        Args:
            feedback_id: Feedback identifier
        
        Returns:
            Feedback data or None if not found
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT 
                        feedback_id, query, response, model, memory_used,
                        tools_called, rating, reason, timestamp, user_id, session_id,
                        intent, project, metadata, created_at, updated_at
                    FROM feedback
                    WHERE feedback_id = %s
                    """,
                    (feedback_id,)
                )
                result = cur.fetchone()
                
                if result:
                    return dict(result)
                return None
        finally:
            self._return_connection(conn)
    
    def update_feedback(
        self,
        feedback_id: str,
        rating: Optional[int] = None,
        intent: Optional[str] = None,
        project: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update existing feedback.
        
        Args:
            feedback_id: Feedback identifier
            rating: New rating value
            intent: Updated intent
            project: Updated project
            metadata: Updated metadata (will be merged with existing)
        
        Returns:
            Update status
        """
        conn = self._get_connection()
        try:
            updates = []
            params = []
            
            if rating is not None:
                if rating not in [1, -1]:
                    raise ValueError("Rating must be 1 or -1")
                updates.append("rating = %s")
                params.append(rating)
            
            if intent is not None:
                updates.append("intent = %s")
                params.append(intent)
            
            if project is not None:
                updates.append("project = %s")
                params.append(project)
            
            if metadata is not None:
                updates.append("metadata = metadata || %s::jsonb")
                params.append(json.dumps(metadata))
            
            if not updates:
                raise ValueError("No updates provided")
            
            params.append(feedback_id)
            
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE feedback
                    SET {', '.join(updates)}
                    WHERE feedback_id = %s
                    RETURNING id
                    """,
                    params
                )
                result = cur.fetchone()
                conn.commit()
                
                if result:
                    logger.info(f"Feedback updated: {feedback_id}")
                    return {"status": "success", "feedback_id": feedback_id}
                else:
                    raise ValueError(f"Feedback not found: {feedback_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating feedback: {e}")
            raise
        finally:
            self._return_connection(conn)
    
    def delete_feedback(self, feedback_id: str) -> Dict[str, Any]:
        """
        Delete feedback by ID.
        
        Args:
            feedback_id: Feedback identifier
        
        Returns:
            Deletion status
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM feedback WHERE feedback_id = %s RETURNING id",
                    (feedback_id,)
                )
                result = cur.fetchone()
                conn.commit()
                
                if result:
                    logger.info(f"Feedback deleted: {feedback_id}")
                    return {
                        "status": "success",
                        "feedback_id": feedback_id,
                        "message": "Feedback deleted successfully"
                    }
                else:
                    raise ValueError(f"Feedback not found: {feedback_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting feedback: {e}")
            raise
        finally:
            self._return_connection(conn)
    
    def get_model_accuracy(
        self,
        model: Optional[str] = None,
        intent: Optional[str] = None,
        project: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get accuracy metrics per model, intent, and project.
        
        Args:
            model: Filter by specific model
            intent: Filter by specific intent
            project: Filter by specific project
        
        Returns:
            List of accuracy metrics
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                where_clauses = []
                params = []
                
                if model:
                    where_clauses.append("model = %s")
                    params.append(model)
                
                if intent:
                    where_clauses.append("intent = %s")
                    params.append(intent)
                
                if project:
                    where_clauses.append("project = %s")
                    params.append(project)
                
                where_sql = ""
                if where_clauses:
                    where_sql = "WHERE " + " AND ".join(where_clauses)
                
                cur.execute(
                    f"""
                    SELECT 
                        model, intent, project,
                        total_feedback, positive_feedback, negative_feedback,
                        accuracy_percentage, last_updated
                    FROM model_accuracy_by_intent
                    {where_sql}
                    ORDER BY model, intent, project
                    """,
                    params
                )
                results = cur.fetchall()
                return [dict(r) for r in results]
        finally:
            self._return_connection(conn)
    
    def get_weekly_finetuning_dataset(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format: str = "jsonl"
    ) -> List[Dict[str, Any]]:
        """
        Export weekly fine-tuning dataset with weighted samples.
        
        Weights:
        - Positive feedback (thumbs-up): 2.0x weight
        - Negative feedback (thumbs-down): 0.5x weight
        
        Args:
            start_date: Start of time range (default: 7 days ago)
            end_date: End of time range (default: now)
            format: Export format ("jsonl", "list")
        
        Returns:
            List of training samples with weights
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=7)
        if end_date is None:
            end_date = datetime.now()
        
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM get_weekly_finetuning_dataset(%s, %s)",
                    (start_date, end_date)
                )
                results = cur.fetchall()
                
                dataset = []
                for row in results:
                    sample = {
                        "query": row["query"],
                        "response": row["response"],
                        "model": row["model"],
                        "rating": row["rating"],
                        "weight": float(row["weight"]),
                        "timestamp": row["timestamp"].isoformat(),
                        "intent": row["intent"],
                        "project": row["project"]
                    }
                    dataset.append(sample)
                
                logger.info(
                    f"Exported {len(dataset)} samples for fine-tuning "
                    f"({start_date.date()} to {end_date.date()})"
                )
                
                return dataset
        finally:
            self._return_connection(conn)
    
    def export_finetuning_dataset(
        self,
        output_path: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        format: str = "jsonl"
    ) -> Dict[str, Any]:
        """
        Export fine-tuning dataset to file.
        
        Args:
            output_path: Path to output file
            start_date: Start of time range
            end_date: End of time range
            format: Export format ("jsonl")
        
        Returns:
            Export statistics
        """
        dataset = self.get_weekly_finetuning_dataset(start_date, end_date)
        
        if format == "jsonl":
            with open(output_path, "w") as f:
                for sample in dataset:
                    training_sample = {
                        "messages": [
                            {"role": "user", "content": sample["query"]},
                            {"role": "assistant", "content": sample["response"]}
                        ],
                        "weight": sample["weight"],
                        "metadata": {
                            "model": sample["model"],
                            "rating": sample["rating"],
                            "timestamp": sample["timestamp"],
                            "intent": sample["intent"],
                            "project": sample["project"]
                        }
                    }
                    f.write(json.dumps(training_sample) + "\n")
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        positive_count = sum(1 for s in dataset if s["rating"] == 1)
        negative_count = sum(1 for s in dataset if s["rating"] == -1)
        total_weight = sum(s["weight"] for s in dataset)
        
        logger.info(f"Dataset exported to {output_path}")
        
        return {
            "status": "success",
            "output_path": output_path,
            "total_samples": len(dataset),
            "positive_samples": positive_count,
            "negative_samples": negative_count,
            "total_weight": round(total_weight, 2),
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None
        }
    
    def get_feedback_stats(
        self,
        model: Optional[str] = None,
        intent: Optional[str] = None,
        project: Optional[str] = None,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get feedback statistics.
        
        Args:
            model: Filter by model
            intent: Filter by intent
            project: Filter by project
            days: Number of days to look back
        
        Returns:
            Statistics dictionary
        """
        start_date = datetime.now() - timedelta(days=days)
        
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                where_clauses = ["timestamp >= %s"]
                params = [start_date]
                
                if model:
                    where_clauses.append("model = %s")
                    params.append(model)
                
                if intent:
                    where_clauses.append("intent = %s")
                    params.append(intent)
                
                if project:
                    where_clauses.append("project = %s")
                    params.append(project)
                
                where_sql = " AND ".join(where_clauses)
                
                cur.execute(
                    f"""
                    SELECT 
                        COUNT(*) as total_feedback,
                        COUNT(*) FILTER (WHERE rating = 1) as positive_count,
                        COUNT(*) FILTER (WHERE rating = -1) as negative_count,
                        ROUND(
                            COUNT(*) FILTER (WHERE rating = 1)::NUMERIC / 
                            NULLIF(COUNT(*), 0) * 100, 2
                        ) as positive_percentage,
                        AVG(memory_used) as avg_memory_used,
                        COUNT(DISTINCT user_id) as unique_users,
                        COUNT(DISTINCT session_id) as unique_sessions
                    FROM feedback
                    WHERE {where_sql}
                    """,
                    params
                )
                stats = cur.fetchone()
                
                return {
                    "total_feedback": stats["total_feedback"],
                    "positive_count": stats["positive_count"],
                    "negative_count": stats["negative_count"],
                    "positive_percentage": float(stats["positive_percentage"] or 0),
                    "avg_memory_used": int(stats["avg_memory_used"] or 0),
                    "unique_users": stats["unique_users"],
                    "unique_sessions": stats["unique_sessions"],
                    "days": days,
                    "filters": {
                        "model": model,
                        "intent": intent,
                        "project": project
                    }
                }
        finally:
            self._return_connection(conn)
    
    def refresh_accuracy_view(self):
        """Manually refresh the materialized view for accuracy metrics."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY model_accuracy_by_intent")
                conn.commit()
                logger.info("Accuracy view refreshed")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error refreshing accuracy view: {e}")
            raise
        finally:
            self._return_connection(conn)
    
    def close(self):
        """Close all database connections."""
        if hasattr(self, 'pool'):
            self.pool.closeall()
            logger.info("Feedback Service connection pool closed")
