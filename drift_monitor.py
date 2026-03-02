#!/usr/bin/env python3
"""
Drift Monitor Service

Implements drift detection with:
- KL Divergence calculation on embedding distributions (7-day sliding windows)
- PSI (Population Stability Index) for intent distribution stability
- YAML-configurable thresholds
- Slack alerting
- Automatic fine-tuning trigger on drift detection
"""

import os
import logging
import asyncio
import re
import yaml
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from drift_policy import (
    load_thresholds,
    load_alert_event_policies,
    load_severity_policies,
)
from contextlib import asynccontextmanager

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
import httpx
from scipy.stats import entropy
from scipy.special import kl_div
from sentence_transformers import SentenceTransformer
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from drift_intent_metrics import (
    calculate_population_stability_index,
    get_intent_distribution,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Prometheus metrics
drift_checks_total = Counter(
    'drift_checks_total',
    'Total number of drift checks performed',
    ['status']
)
drift_detected_total = Counter(
    'drift_detected_total',
    'Total number of drift detections',
    ['severity']
)
kl_divergence_gauge = Gauge(
    'drift_kl_divergence',
    'Current KL Divergence value'
)
psi_gauge = Gauge(
    'drift_psi',
    'Current PSI (Population Stability Index) value'
)
baseline_accuracy_gauge = Gauge(
    'drift_baseline_accuracy',
    'Baseline accuracy from previous window'
)
current_accuracy_gauge = Gauge(
    'drift_current_accuracy',
    'Current accuracy from current window'
)
combined_drift_score_gauge = Gauge(
    'drift_combined_score',
    'Combined drift score'
)
finetuning_triggers_total = Counter(
    'finetuning_triggers_total',
    'Total number of fine-tuning triggers',
    ['trigger_type']
)
drift_check_duration = Histogram(
    'drift_check_duration_seconds',
    'Duration of drift check operations'
)


class DriftMonitorConfig(BaseModel):
    """Drift monitor configuration"""
    # Service
    service_host: str = Field(default="0.0.0.0")
    service_port: int = Field(default=8004)
    
    # Thresholds
    kl_threshold: float = Field(default=0.1)
    psi_threshold: float = Field(default=0.2)
    accuracy_min: float = Field(default=0.75)
    
    # Monitoring
    sliding_window_days: int = Field(default=7)
    check_interval_hours: int = Field(default=6)
    min_samples: int = Field(default=100)
    
    # Embeddings
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    embedding_batch_size: int = Field(default=32)
    embedding_dimension: int = Field(default=384)
    
    # Intents
    intent_categories: List[str] = Field(default=[
        "code", "reasoning", "general", "debug", "documentation"
    ])
    min_samples_per_intent: int = Field(default=10)
    
    # Alerting
    alerts_enabled: bool = Field(default=True)
    slack_enabled: bool = Field(default=True)
    slack_webhook_url: Optional[str] = Field(default=None)
    slack_channel: str = Field(default="#drift-alerts")
    drift_detected_alert_enabled: bool = Field(default=True)
    drift_detected_alert_severity: str = Field(default="warning")
    accuracy_drop_alert_enabled: bool = Field(default=True)
    accuracy_drop_alert_severity: str = Field(default="critical")
    accuracy_drop_min: float = Field(default=0.10)
    critical_kl_multiplier: float = Field(default=2.0)
    critical_psi_multiplier: float = Field(default=2.0)
    critical_accuracy_drop: float = Field(default=0.15)
    warning_kl_multiplier: float = Field(default=1.5)
    warning_psi_multiplier: float = Field(default=1.5)
    warning_accuracy_drop: float = Field(default=0.10)
    eval_metric_name: str = Field(default="quality_eval_score")
    eval_score_drop_min: float = Field(default=0.05)
    warning_eval_score_drop: float = Field(default=0.08)
    critical_eval_score_drop: float = Field(default=0.12)
    
    # Fine-tuning
    auto_trigger_finetuning: bool = Field(default=True)
    learning_engine_url: str = Field(default="http://learning-engine:8003")
    min_drift_score: float = Field(default=0.3)
    cooldown_hours: int = Field(default=168)
    fresh_data_window_days: int = Field(default=7)
    min_fresh_labeled_samples: int = Field(default=100)
    
    # Database
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="ai_platform")
    postgres_user: str = Field(default="ai_user")
    postgres_password: str = Field(default="ai_password")
    
    # Eval-first drift monitoring
    min_eval_samples: int = Field(default=3)
    retraining_recommend_min_drop: float = Field(default=0.08)
    
    # Incident management
    open_incident_on_drift: bool = Field(default=True)


def load_config(config_path: str = "configs/drift-monitor.yaml") -> DriftMonitorConfig:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r') as f:
            yaml_config = yaml.safe_load(f)
        
        thresholds = load_thresholds(yaml_config)
        alert_event_policies = load_alert_event_policies(yaml_config)
        severity_policies = load_severity_policies(yaml_config)
        eval_policy = yaml_config.get("drift_policy", {}).get("eval", {})
        incident_policy = yaml_config.get("incidents", {})

        # Flatten nested config
        config_dict = {
            "service_host": yaml_config.get("service", {}).get("host", "0.0.0.0"),
            "service_port": yaml_config.get("service", {}).get("port", 8004),
            "kl_threshold": thresholds.kl_threshold,
            "psi_threshold": thresholds.psi_threshold,
            "accuracy_min": thresholds.accuracy_min,
            "sliding_window_days": yaml_config.get("monitoring", {}).get("sliding_window_days", 7),
            "check_interval_hours": yaml_config.get("monitoring", {}).get("check_interval_hours", 6),
            "min_samples": yaml_config.get("monitoring", {}).get("min_samples", 100),
            "embedding_model": yaml_config.get("embeddings", {}).get("model", "sentence-transformers/all-MiniLM-L6-v2"),
            "embedding_batch_size": yaml_config.get("embeddings", {}).get("batch_size", 32),
            "embedding_dimension": yaml_config.get("embeddings", {}).get("dimension", 384),
            "intent_categories": yaml_config.get("intents", {}).get("categories", []),
            "min_samples_per_intent": yaml_config.get("intents", {}).get("min_samples_per_intent", 10),
            "alerts_enabled": yaml_config.get("alerts", {}).get("enabled", True),
            "slack_enabled": yaml_config.get("alerts", {}).get("slack", {}).get("enabled", True),
            "slack_webhook_url": os.getenv("SLACK_WEBHOOK_URL"),
            "slack_channel": yaml_config.get("alerts", {}).get("slack", {}).get("channel", "#drift-alerts"),
            "drift_detected_alert_enabled": alert_event_policies["drift_detected"].enabled,
            "drift_detected_alert_severity": alert_event_policies["drift_detected"].severity,
            "accuracy_drop_alert_enabled": alert_event_policies["accuracy_drop"].enabled,
            "accuracy_drop_alert_severity": alert_event_policies["accuracy_drop"].severity,
            "accuracy_drop_min": alert_event_policies["accuracy_drop"].min_drop,
            "critical_kl_multiplier": severity_policies["critical"].kl_multiplier,
            "critical_psi_multiplier": severity_policies["critical"].psi_multiplier,
            "critical_accuracy_drop": severity_policies["critical"].accuracy_delta,
            "warning_kl_multiplier": severity_policies["warning"].kl_multiplier,
            "warning_psi_multiplier": severity_policies["warning"].psi_multiplier,
            "warning_accuracy_drop": severity_policies["warning"].accuracy_delta,
            "eval_metric_name": eval_policy.get("metric_name", "quality_eval_score"),
            "eval_score_drop_min": eval_policy.get("drop_min", 0.05),
            "warning_eval_score_drop": eval_policy.get("warning_drop", 0.08),
            "critical_eval_score_drop": eval_policy.get("critical_drop", 0.12),
            "auto_trigger_finetuning": yaml_config.get("fine_tuning", {}).get("auto_trigger", True),
            "learning_engine_url": yaml_config.get("fine_tuning", {}).get("learning_engine_url", "http://learning-engine:8003"),
            "min_drift_score": yaml_config.get("fine_tuning", {}).get("min_drift_score", 0.3),
            "cooldown_hours": yaml_config.get("fine_tuning", {}).get("cooldown_hours", 168),
            "fresh_data_window_days": yaml_config.get("fine_tuning", {}).get("fresh_data_window_days", 7),
            "min_fresh_labeled_samples": yaml_config.get("fine_tuning", {}).get("min_fresh_labeled_samples", 100),
            "postgres_host": yaml_config.get("database", {}).get("host", "postgres"),
            "postgres_port": yaml_config.get("database", {}).get("port", 5432),
            "postgres_db": yaml_config.get("database", {}).get("name", "ai_platform"),
            "postgres_user": yaml_config.get("database", {}).get("user", "ai_user"),
            "postgres_password": yaml_config.get("database", {}).get("password", "ai_password"),
            "min_eval_samples": yaml_config.get("monitoring", {}).get("min_eval_samples", 3),
            "retraining_recommend_min_drop": yaml_config.get("fine_tuning", {}).get("recommend_min_eval_drop", 0.08),
            "open_incident_on_drift": incident_policy.get("open_on_eval_drift", True),
        }

        return DriftMonitorConfig(**config_dict)
    except Exception as e:
        logger.warning(f"Failed to load config from {config_path}: {e}, using defaults")
        return DriftMonitorConfig()


class DriftMonitor:
    """
    Drift monitoring service with KL Divergence and PSI calculations.
    """
    
    def __init__(self, config: DriftMonitorConfig):
        """Initialize drift monitor"""
        self.config = config
        self.embedding_model = None
        self.is_monitoring = False
        self.last_finetuning_trigger = None
        
        # Database connection
        self.db_conn = None
        
        logger.info("Drift Monitor initialized")
    
    def connect_db(self):
        """Connect to PostgreSQL database"""
        if not self.db_conn or self.db_conn.closed:
            self.db_conn = psycopg2.connect(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                dbname=self.config.postgres_db,
                user=self.config.postgres_user,
                password=self.config.postgres_password
            )
        return self.db_conn
    
    def load_embedding_model(self):
        """Load sentence transformer model for embeddings"""
        if self.embedding_model is None:
            logger.info(f"Loading embedding model: {self.config.embedding_model}")
            self.embedding_model = SentenceTransformer(self.config.embedding_model)
            logger.info("✓ Embedding model loaded")
    
    def get_feedback_data(
        self,
        days: int = 7,
        offset_days: int = 0,
        project: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get feedback data from database for a specific time window.

        Args:
            days: Number of days in the window
            offset_days: Offset from current time (0 = current, 7 = previous week)
            project: Optional project scope filter
            workspace: Optional workspace scope filter (from metadata.workspace)
        
        Returns:
            List of feedback records
        """
        conn = self.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        end_date = datetime.now() - timedelta(days=offset_days)
        start_date = end_date - timedelta(days=days)

        query = """
        SELECT
            query, response, model, rating, intent, project,
            timestamp, metadata
        FROM feedback
        WHERE timestamp >= %s AND timestamp < %s
        ORDER BY timestamp DESC
        """

        params: List[Any] = [start_date, end_date]
        filters: List[str] = []
        if project:
            filters.append("project = %s")
            params.append(project)
        if workspace:
            filters.append("COALESCE(metadata->>'workspace', '') = %s")
            params.append(workspace)

        if filters:
            scoped_filter = " AND " + " AND ".join(filters)
            query = query.replace("ORDER BY", f"{scoped_filter}\n        ORDER BY")

        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        cursor.close()

        return [dict(row) for row in results]

    def list_monitoring_scopes(self, days: int) -> List[Tuple[str, str]]:
        """List scopes (workspace/project) that have recent feedback."""
        conn = self.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        start_date = datetime.now() - timedelta(days=days * 2)

        cursor.execute(
            """
            SELECT DISTINCT scope_type, scope_value
            FROM (
                SELECT 'project' AS scope_type, project AS scope_value
                FROM feedback
                WHERE timestamp >= %s AND project IS NOT NULL AND project <> ''

                UNION

                SELECT 'workspace' AS scope_type, metadata->>'workspace' AS scope_value
                FROM feedback
                WHERE timestamp >= %s
                  AND COALESCE(metadata->>'workspace', '') <> ''
            ) scoped
            ORDER BY scope_type, scope_value
            """,
            (start_date, start_date)
        )

        rows = cursor.fetchall()
        cursor.close()
        return [(row['scope_type'], row['scope_value']) for row in rows]

    
    def compute_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Compute embeddings for a list of texts.
        
        Args:
            texts: List of text strings
        
        Returns:
            Numpy array of embeddings (n_texts, embedding_dim)
        """
        self.load_embedding_model()
        
        embeddings = self.embedding_model.encode(
            texts,
            batch_size=self.config.embedding_batch_size,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        
        return embeddings
    
    def calculate_kl_divergence(
        self,
        baseline_embeddings: np.ndarray,
        current_embeddings: np.ndarray,
        num_bins: int = 50
    ) -> float:
        """
        Calculate KL Divergence between two embedding distributions.
        
        Uses histogram-based approach to compare distributions in embedding space.
        
        Args:
            baseline_embeddings: Baseline embeddings (reference period)
            current_embeddings: Current embeddings (monitoring period)
            num_bins: Number of bins for histogram
        
        Returns:
            KL Divergence value (lower is better, 0 = identical)
        """
        # Flatten embeddings to 1D for distribution comparison
        baseline_flat = baseline_embeddings.flatten()
        current_flat = current_embeddings.flatten()
        
        # Compute histograms with same bins
        min_val = min(baseline_flat.min(), current_flat.min())
        max_val = max(baseline_flat.max(), current_flat.max())
        bins = np.linspace(min_val, max_val, num_bins + 1)
        
        baseline_hist, _ = np.histogram(baseline_flat, bins=bins, density=True)
        current_hist, _ = np.histogram(current_flat, bins=bins, density=True)
        
        # Add small epsilon to avoid log(0)
        epsilon = 1e-10
        baseline_hist = baseline_hist + epsilon
        current_hist = current_hist + epsilon
        
        # Normalize to probability distributions
        baseline_hist = baseline_hist / baseline_hist.sum()
        current_hist = current_hist / current_hist.sum()
        
        # Calculate KL Divergence
        kl_div_value = entropy(current_hist, baseline_hist)
        
        return float(kl_div_value)
    
    def calculate_psi(
        self,
        reference_distribution: Dict[str, int],
        current_distribution: Dict[str, int]
    ) -> float:
        """
        Calculate Population Stability Index (PSI) for intent distributions.
        
        PSI measures the shift in distribution between two periods.
        PSI < 0.1: No significant change
        PSI 0.1-0.2: Moderate change
        PSI > 0.2: Significant change (drift detected)
        
        Args:
            reference_distribution: Reference-window intent counts
            current_distribution: Current intent counts
        
        Returns:
            PSI value
        """
        return calculate_population_stability_index(
            reference_distribution=reference_distribution,
            current_distribution=current_distribution,
            categories=self.config.intent_categories,
        )
    
    def get_intent_distribution(self, feedback_data: List[Dict]) -> Dict[str, int]:
        """
        Get intent distribution from feedback data.
        
        Args:
            feedback_data: List of feedback records
        
        Returns:
            Dictionary mapping intent to count
        """
        return get_intent_distribution(
            feedback_data,
            categories=self.config.intent_categories,
        )
    
    def calculate_accuracy_metrics(self, feedback_data: List[Dict]) -> Dict[str, float]:
        """
        Calculate accuracy metrics from feedback data.
        
        Args:
            feedback_data: List of feedback records
        
        Returns:
            Dictionary with accuracy metrics
        """
        if not feedback_data:
            return {"accuracy": 0.0, "positive_count": 0, "total_count": 0}
        
        positive_count = sum(1 for r in feedback_data if r.get('rating', 0) == 1)
        total_count = len(feedback_data)
        accuracy = positive_count / total_count if total_count > 0 else 0.0
        
        return {
            "accuracy": accuracy,
            "positive_count": positive_count,
            "total_count": total_count
        }
    
    async def send_slack_alert(
        self,
        severity: str,
        message: str,
        metrics: Dict[str, Any]
    ):
        """
        Send alert to Slack.
        
        Args:
            severity: Alert severity (info, warning, critical)
            message: Alert message
            metrics: Drift metrics
        """
        if not self.config.alerts_enabled or not self.config.slack_enabled:
            return
        
        if not self.config.slack_webhook_url:
            logger.warning("Slack webhook URL not configured")
            return
        
        # Color coding
        colors = {
            "info": "#36a64f",      # Green
            "warning": "#ff9900",   # Orange
            "critical": "#ff0000"   # Red
        }
        
        # Format metrics
        metrics_text = "\n".join([
            f"• {k}: {v:.4f}" if isinstance(v, float) else f"• {k}: {v}"
            for k, v in metrics.items()
        ])
        
        payload = {
            "channel": self.config.slack_channel,
            "username": "Drift Monitor",
            "icon_emoji": ":chart_with_downwards_trend:",
            "attachments": [
                {
                    "color": colors.get(severity, "#808080"),
                    "title": f"[{severity.upper()}] Model Drift Detected",
                    "text": message,
                    "fields": [
                        {
                            "title": "Metrics",
                            "value": metrics_text,
                            "short": False
                        },
                        {
                            "title": "Timestamp",
                            "value": datetime.now().isoformat(),
                            "short": True
                        },
                        {
                            "title": "Severity",
                            "value": severity.upper(),
                            "short": True
                        }
                    ],
                    "footer": "Drift Monitor Service"
                }
            ]
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config.slack_webhook_url,
                    json=payload,
                    timeout=10.0
                )
                if response.status_code == 200:
                    logger.info(f"Slack alert sent: {severity}")
                else:
                    logger.error(f"Failed to send Slack alert: {response.status_code}")
        except Exception as e:
            logger.error(f"Error sending Slack alert: {e}")
    
    async def trigger_finetuning(self, drift_metrics: Dict[str, Any]) -> bool:
        """
        Trigger automatic fine-tuning via Learning Engine API.
        
        Args:
            drift_metrics: Drift detection metrics
        
        Returns:
            True if successfully triggered, False otherwise
        """
        if not self.config.auto_trigger_finetuning:
            logger.info("Auto-triggering fine-tuning is disabled")
            return False
        
        # Check cooldown period
        if self.last_finetuning_trigger:
            hours_since_last = (datetime.now() - self.last_finetuning_trigger).total_seconds() / 3600
            if hours_since_last < self.config.cooldown_hours:
                logger.info(f"Fine-tuning cooldown active ({hours_since_last:.1f}h / {self.config.cooldown_hours}h)")
                return False

        fresh_sample_count = self.get_fresh_labeled_sample_count(self.config.fresh_data_window_days)
        if fresh_sample_count < self.config.min_fresh_labeled_samples:
            logger.info(
                "Skipping auto fine-tuning trigger due to insufficient fresh labeled data "
                f"({fresh_sample_count} < {self.config.min_fresh_labeled_samples})"
            )
            return False

        audit_context = {
            "trigger_type": "automatic_drift",
            "triggered_at": datetime.now().isoformat(),
            "drift_metrics": drift_metrics,
            "thresholds": {
                "kl_threshold": self.config.kl_threshold,
                "psi_threshold": self.config.psi_threshold,
                "accuracy_min": self.config.accuracy_min,
                "min_drift_score": self.config.min_drift_score
            },
            "fresh_data_gate": {
                "window_days": self.config.fresh_data_window_days,
                "sample_count": fresh_sample_count,
                "required_min_samples": self.config.min_fresh_labeled_samples
            }
        }

        try:
            url = f"{self.config.learning_engine_url}/train"
            payload = {
                "days": self.config.fresh_data_window_days,
                "force": False,
                "trigger_source": "drift_monitor",
                "audit_context": audit_context
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=30.0)
                
                if response.status_code == 200:
                    result = response.json()
                    self.last_finetuning_trigger = datetime.now()
                    
                    # Store trigger record
                    self.store_finetuning_trigger(drift_metrics, audit_context, result)
                    
                    # Update Prometheus metrics
                    finetuning_triggers_total.labels(trigger_type='automatic').inc()
                    
                    logger.info(f"Fine-tuning triggered: {result.get('job_id')}")
                    
                    # Send success alert
                    await self.send_slack_alert(
                        "info",
                        f"Automatic fine-tuning triggered due to drift detection.\nJob ID: {result.get('job_id')}",
                        drift_metrics
                    )
                    
                    return True
                else:
                    logger.error(f"Failed to trigger fine-tuning: {response.status_code}")
                    return False
        
        except Exception as e:
            logger.error(f"Error triggering fine-tuning: {e}")
            return False
    
    def store_drift_metrics(
        self,
        kl_divergence: float,
        psi: float,
        baseline_accuracy: float,
        current_accuracy: float,
        drift_detected: bool,
        severity: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_value: Optional[str] = None,
    ):
        """
        Store drift metrics in database.

        Args:
            kl_divergence: KL Divergence value
            psi: PSI value
            baseline_accuracy: Baseline accuracy
            current_accuracy: Current accuracy
            drift_detected: Whether drift was detected
            severity: Alert severity level
        """
        conn = self.connect_db()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO drift_metrics (
                    kl_divergence, psi, baseline_accuracy, current_accuracy,
                    drift_detected, severity, scope_type, scope_value, timestamp
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    kl_divergence, psi, baseline_accuracy, current_accuracy,
                    drift_detected, severity, scope_type, scope_value, datetime.now()
                )
            )
            conn.commit()
            scope_text = f"{scope_type}:{scope_value}" if scope_type and scope_value else "global"
            logger.info(f"Drift metrics stored for {scope_text}: KL={kl_divergence:.4f}, PSI={psi:.4f}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to store drift metrics: {e}")
        finally:
            cursor.close()
    
    def store_finetuning_trigger(self, drift_metrics: Dict, audit_context: Dict, trigger_result: Dict):

        """
        Store fine-tuning trigger record.
        
        Args:
            drift_metrics: Drift metrics that triggered fine-tuning
            audit_context: Trigger audit payload
            trigger_result: Response from learning engine
        """
        conn = self.connect_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                INSERT INTO finetuning_triggers (
                    job_id, drift_metrics, trigger_timestamp
                ) VALUES (%s, %s, %s)
                """,
                (
                    trigger_result.get('job_id'),
                    json.dumps({
                        "drift_metrics": drift_metrics,
                        "audit_context": audit_context,
                        "learning_engine_response": trigger_result
                    }),
                    datetime.now()
                )
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to store fine-tuning trigger: {e}")
        finally:
            cursor.close()

    def get_fresh_labeled_sample_count(self, days: int) -> int:
        """Count fresh labeled feedback samples available for training."""
        conn = self.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cursor.execute(
                """
                SELECT COUNT(*) AS sample_count
                FROM feedback
                WHERE timestamp >= NOW() - (%s || ' days')::INTERVAL
                  AND rating IN (-1, 1)
                """,
                (days,)
            )
            result = cursor.fetchone() or {"sample_count": 0}
            return int(result["sample_count"])
        except Exception as e:
            logger.error(f"Failed to count fresh labeled data: {e}")
            return 0
        finally:
            cursor.close()

    def get_eval_scores(
        self,
        days: int = 7,
        offset_days: int = 0,
        scope_type: Optional[str] = None,
        scope_value: Optional[str] = None,
    ) -> List[float]:
        """Get eval scores for a time window from lora_performance."""
        conn = self.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        end_date = datetime.now() - timedelta(days=offset_days)
        start_date = end_date - timedelta(days=days)

        query = """
            SELECT metric_value
            FROM lora_performance
            WHERE metric_name = %s
              AND timestamp >= %s
              AND timestamp < %s
        """
        params: List[Any] = [self.config.eval_metric_name, start_date, end_date]

        if scope_type == "project" and scope_value:
            query += " AND COALESCE(metadata->>'project', '') = %s"
            params.append(scope_value)
        elif scope_type == "workspace" and scope_value:
            query += " AND COALESCE(metadata->>'workspace', '') = %s"
            params.append(scope_value)

        query += " ORDER BY timestamp DESC"

        try:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            scores: List[float] = []
            for row in rows:
                value = row.get("metric_value")
                if value is None:
                    continue
                try:
                    scores.append(float(value))
                except (TypeError, ValueError):
                    continue
            return scores
        except Exception as e:
            logger.error(f"Failed to fetch eval scores: {e}")
            return []
        finally:
            cursor.close()

    def calculate_eval_score_metrics(
        self,
        baseline_scores: List[float],
        current_scores: List[float],
    ) -> Dict[str, float]:
        """Calculate eval-score drift metrics between baseline and current windows."""
        if not baseline_scores or not current_scores:
            return {
                "baseline_eval_score": 0.0,
                "current_eval_score": 0.0,
                "eval_score_delta": 0.0,
                "eval_score_drop": 0.0,
            }

        baseline_eval_score = float(np.mean(baseline_scores))
        current_eval_score = float(np.mean(current_scores))
        eval_score_delta = current_eval_score - baseline_eval_score
        eval_score_drop = max(0.0, baseline_eval_score - current_eval_score)

        return {
            "baseline_eval_score": baseline_eval_score,
            "current_eval_score": current_eval_score,
            "eval_score_delta": eval_score_delta,
            "eval_score_drop": eval_score_drop,
        }

    def recommend_retraining(self, eval_score_drop: float, secondary_signal_count: int) -> bool:
        """Recommend retraining from eval-drop primary signal plus secondary evidence."""
        return (
            eval_score_drop >= self.config.retraining_recommend_min_drop
            or (
                eval_score_drop >= self.config.eval_score_drop_min
                and secondary_signal_count > 0
            )
        )

    def open_drift_incident(
        self,
        scope_type: str,
        scope_value: str,
        severity: str,
        metrics: Dict[str, Any],
    ) -> Optional[str]:
        """Open a drift incident record and return its id."""
        if not self.config.open_incident_on_drift:
            return None

        scope_fragment = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"{scope_type}-{scope_value}").strip("-").lower()
        if not scope_fragment:
            scope_fragment = "global"
        incident_id = f"drift-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{scope_fragment}"

        summary = (
            f"Eval quality drift detected for {scope_type}:{scope_value} "
            f"(drop={metrics.get('eval_score_drop', 0.0):.4f})"
        )
        recommendation = metrics.get(
            "recommendation",
            "review_eval_suite_and_prepare_retraining",
        )

        conn = self.connect_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO drift_incidents (
                    incident_id, status, severity, scope_type, scope_value,
                    summary, recommendation, payload, opened_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    incident_id,
                    "open",
                    severity,
                    scope_type,
                    scope_value,
                    summary,
                    recommendation,
                    json.dumps(metrics),
                    datetime.now(),
                    datetime.now(),
                ),
            )
            conn.commit()
            return incident_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to open drift incident: {e}")
            return None
        finally:
            cursor.close()

    async def run_drift_check(self) -> Dict[str, Any]:
        """
        Run drift detection check.

        Returns:
            Drift detection results
        """
        logger.info("=" * 60)
        logger.info("Running Drift Detection Check")
        logger.info("=" * 60)

        start_time = asyncio.get_event_loop().time()

        try:
            scopes = self.list_monitoring_scopes(self.config.sliding_window_days)
            if not scopes:
                logger.warning("No project/workspace scopes found, falling back to global scope")
                scopes = [("global", "global")]

            per_scope_results = []
            drift_found_any = False
            severity_rank = {"info": 1, "warning": 2, "critical": 3}
            highest_severity: Optional[str] = None
            representative_metrics: Dict[str, Any] = {}

            for scope_type, scope_value in scopes:
                if scope_type == "project":
                    scope_kwargs = {"project": scope_value}
                elif scope_type == "workspace":
                    scope_kwargs = {"workspace": scope_value}
                else:
                    scope_kwargs = {}

                baseline_eval_scores = self.get_eval_scores(
                    days=self.config.sliding_window_days,
                    offset_days=self.config.sliding_window_days,
                    scope_type=scope_type,
                    scope_value=scope_value,
                )
                current_eval_scores = self.get_eval_scores(
                    days=self.config.sliding_window_days,
                    offset_days=0,
                    scope_type=scope_type,
                    scope_value=scope_value,
                )

                baseline_data = self.get_feedback_data(
                    days=self.config.sliding_window_days,
                    offset_days=self.config.sliding_window_days,
                    **scope_kwargs,
                )
                current_data = self.get_feedback_data(
                    days=self.config.sliding_window_days,
                    offset_days=0,
                    **scope_kwargs,
                )

                logger.info(
                    "Scope %s:%s baseline_feedback=%s current_feedback=%s baseline_eval=%s current_eval=%s",
                    scope_type,
                    scope_value,
                    len(baseline_data),
                    len(current_data),
                    len(baseline_eval_scores),
                    len(current_eval_scores),
                )

                if (
                    len(baseline_eval_scores) < self.config.min_eval_samples
                    or len(current_eval_scores) < self.config.min_eval_samples
                ):
                    per_scope_results.append(
                        {
                            "scope_type": scope_type,
                            "scope_value": scope_value,
                            "status": "skipped",
                            "reason": "insufficient_eval_samples",
                            "baseline_eval_count": len(baseline_eval_scores),
                            "current_eval_count": len(current_eval_scores),
                            "min_eval_samples": self.config.min_eval_samples,
                            "baseline_feedback_count": len(baseline_data),
                            "current_feedback_count": len(current_data),
                        }
                    )
                    continue

                eval_metrics = self.calculate_eval_score_metrics(
                    baseline_scores=baseline_eval_scores,
                    current_scores=current_eval_scores,
                )
                baseline_eval_score = eval_metrics["baseline_eval_score"]
                current_eval_score = eval_metrics["current_eval_score"]
                eval_score_drop = eval_metrics["eval_score_drop"]

                kl_divergence = 0.0
                psi = 0.0
                kl_drift = False
                psi_drift = False

                secondary_samples_ready = (
                    len(baseline_data) >= self.config.min_samples
                    and len(current_data) >= self.config.min_samples
                )
                if secondary_samples_ready:
                    baseline_texts = [f"{r['query']}\n{r['response']}" for r in baseline_data]
                    current_texts = [f"{r['query']}\n{r['response']}" for r in current_data]

                    baseline_embeddings = self.compute_embeddings(baseline_texts)
                    current_embeddings = self.compute_embeddings(current_texts)
                    kl_divergence = self.calculate_kl_divergence(
                        baseline_embeddings,
                        current_embeddings,
                    )

                    baseline_intent_dist = self.get_intent_distribution(baseline_data)
                    current_intent_dist = self.get_intent_distribution(current_data)
                    psi = self.calculate_psi(baseline_intent_dist, current_intent_dist)

                    kl_drift = kl_divergence > self.config.kl_threshold
                    psi_drift = psi > self.config.psi_threshold

                eval_drop_detected = eval_score_drop >= self.config.eval_score_drop_min
                drift_detected = eval_drop_detected
                drift_found_any = drift_found_any or drift_detected

                secondary_signal_count = int(kl_drift) + int(psi_drift)
                kl_score = kl_divergence / self.config.kl_threshold if self.config.kl_threshold else 0.0
                psi_score = psi / self.config.psi_threshold if self.config.psi_threshold else 0.0
                eval_drop_score = (
                    eval_score_drop / self.config.eval_score_drop_min
                    if self.config.eval_score_drop_min
                    else 0.0
                )
                combined_drift_score = (2 * eval_drop_score + kl_score + psi_score) / 4

                severity = None
                if drift_detected:
                    if (
                        eval_score_drop >= self.config.critical_eval_score_drop
                        or secondary_signal_count >= 2
                    ):
                        severity = "critical"
                    elif eval_score_drop >= self.config.warning_eval_score_drop or secondary_signal_count >= 1:
                        severity = "warning"
                    else:
                        severity = "info"

                retraining_recommended = self.recommend_retraining(eval_score_drop, secondary_signal_count)
                recommendation = (
                    "trigger_retraining_pipeline"
                    if retraining_recommended
                    else "monitor_next_eval_window"
                )

                metrics = {
                    "kl_divergence": kl_divergence,
                    "psi": psi,
                    # Legacy keys kept for dashboard compatibility; values now carry eval scores.
                    "baseline_accuracy": baseline_eval_score,
                    "current_accuracy": current_eval_score,
                    "accuracy_delta": eval_score_drop,
                    "baseline_eval_score": baseline_eval_score,
                    "current_eval_score": current_eval_score,
                    "eval_score_delta": eval_metrics["eval_score_delta"],
                    "eval_score_drop": eval_score_drop,
                    "eval_metric_name": self.config.eval_metric_name,
                    "eval_drop_detected": eval_drop_detected,
                    "secondary_signals": {
                        "kl_drift": kl_drift,
                        "psi_drift": psi_drift,
                    },
                    "secondary_signal_count": secondary_signal_count,
                    "combined_drift_score": combined_drift_score,
                    "drift_detected": drift_detected,
                    "severity": severity,
                    "scope_type": scope_type,
                    "scope_value": scope_value,
                    "baseline_eval_samples": len(baseline_eval_scores),
                    "current_eval_samples": len(current_eval_scores),
                    "retraining_recommended": retraining_recommended,
                    "recommendation": recommendation,
                }

                incident_id: Optional[str] = None
                if drift_detected and severity:
                    incident_id = self.open_drift_incident(
                        scope_type=scope_type,
                        scope_value=scope_value,
                        severity=severity,
                        metrics=metrics,
                    )
                metrics["incident_id"] = incident_id
                metrics["incident_opened"] = incident_id is not None

                self.store_drift_metrics(
                    kl_divergence,
                    psi,
                    baseline_eval_score,
                    current_eval_score,
                    drift_detected,
                    severity,
                    scope_type,
                    scope_value,
                )

                kl_divergence_gauge.set(kl_divergence)
                psi_gauge.set(psi)
                baseline_accuracy_gauge.set(baseline_eval_score)
                current_accuracy_gauge.set(current_eval_score)
                combined_drift_score_gauge.set(combined_drift_score)

                if drift_detected and severity:
                    if not highest_severity or severity_rank[severity] > severity_rank[highest_severity]:
                        highest_severity = severity
                        representative_metrics = metrics
                    drift_detected_total.labels(severity=severity).inc()

                if drift_detected and self.config.drift_detected_alert_enabled:
                    drift_severity = severity or self.config.drift_detected_alert_severity
                    message = (
                        f"Event: eval_drift_detected\n"
                        f"Quality drift detected for {scope_type}:{scope_value}.\n"
                        f"Eval Metric: {self.config.eval_metric_name}\n"
                        f"Baseline Eval Score: {baseline_eval_score:.4f}\n"
                        f"Current Eval Score: {current_eval_score:.4f}\n"
                        f"Eval Score Drop: {eval_score_drop:.4f} "
                        f"(threshold: {self.config.eval_score_drop_min:.4f})\n"
                        f"KL Divergence: {kl_divergence:.4f} (threshold: {self.config.kl_threshold})\n"
                        f"PSI: {psi:.4f} (threshold: {self.config.psi_threshold})\n"
                        f"Secondary Signals: {secondary_signal_count}\n"
                        f"Incident Opened: {'yes' if incident_id else 'no'}\n"
                        f"Combined Drift Score: {combined_drift_score:.4f}"
                    )
                    await self.send_slack_alert(drift_severity, message, metrics)

                eval_drop_event = eval_score_drop >= self.config.accuracy_drop_min
                if eval_drop_event and self.config.accuracy_drop_alert_enabled:
                    accuracy_severity = self.config.accuracy_drop_alert_severity
                    accuracy_message = (
                        f"Event: eval_score_drop\n"
                        f"Eval score drop detected for {scope_type}:{scope_value} with {accuracy_severity} severity.\n"
                        f"Baseline Eval Score: {baseline_eval_score:.4f}\n"
                        f"Current Eval Score: {current_eval_score:.4f}\n"
                        f"Eval Score Drop: {eval_score_drop:.4f} "
                        f"(minimum drop: {self.config.accuracy_drop_min:.4f})"
                    )
                    await self.send_slack_alert(accuracy_severity, accuracy_message, metrics)

                if (
                    drift_detected
                    and retraining_recommended
                    and combined_drift_score >= self.config.min_drift_score
                ):
                    await self.trigger_finetuning(metrics)

                per_scope_results.append(
                    {
                        "scope_type": scope_type,
                        "scope_value": scope_value,
                        "status": "success",
                        "metrics": metrics,
                        "baseline_samples": len(baseline_data),
                        "current_samples": len(current_data),
                        "secondary_samples_ready": secondary_samples_ready,
                    }
                )

            successful_scopes = sum(1 for result in per_scope_results if result.get("status") == "success")
            if successful_scopes == 0:
                drift_checks_total.labels(status='skipped').inc()
                return {
                    "status": "skipped",
                    "reason": "insufficient_eval_samples",
                    "scope_results": per_scope_results,
                    "checked_scopes": len(scopes),
                    "timestamp": datetime.now().isoformat(),
                }

            drift_checks_total.labels(status='success').inc()

            
            # Record duration
            duration = asyncio.get_event_loop().time() - start_time
            drift_check_duration.observe(duration)

            return {
                "status": "success",
                "drift_detected": drift_found_any,
                "severity": highest_severity,
                "metrics": representative_metrics,
                "scope_results": per_scope_results,
                "checked_scopes": len(scopes),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Drift check failed: {e}", exc_info=True)
            drift_checks_total.labels(status='error').inc()
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def start_monitoring(self):
        """Start continuous drift monitoring"""
        self.is_monitoring = True
        logger.info(f"Starting drift monitoring (interval: {self.config.check_interval_hours}h)")
        
        while self.is_monitoring:
            try:
                await self.run_drift_check()
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            # Wait for next check interval
            await asyncio.sleep(self.config.check_interval_hours * 3600)
    
    def stop_monitoring(self):
        """Stop drift monitoring"""
        self.is_monitoring = False
        logger.info("Drift monitoring stopped")
    
    def close(self):
        """Close database connections"""
        if self.db_conn and not self.db_conn.closed:
            self.db_conn.close()


# Global state
config = load_config()
drift_monitor: Optional[DriftMonitor] = None
monitoring_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for the service"""
    global drift_monitor, monitoring_task
    
    logger.info("Starting Drift Monitor Service...")
    logger.info(f"Configuration: KL threshold={config.kl_threshold}, PSI threshold={config.psi_threshold}")
    
    try:
        # Initialize drift monitor
        drift_monitor = DriftMonitor(config)
        logger.info("✓ Drift Monitor initialized")
        
        # Start monitoring in background
        monitoring_task = asyncio.create_task(drift_monitor.start_monitoring())
        logger.info("✓ Drift monitoring started")
        
        logger.info("Drift Monitor Service ready!")
        
        yield
        
    finally:
        # Cleanup
        logger.info("Shutting down Drift Monitor Service...")
        if drift_monitor:
            drift_monitor.stop_monitoring()
            if monitoring_task:
                monitoring_task.cancel()
                try:
                    await monitoring_task
                except asyncio.CancelledError:
                    pass
            drift_monitor.close()
        logger.info("Drift Monitor Service stopped")


# Create FastAPI app
app = FastAPI(
    title="Drift Monitor Service",
    description="Model drift detection with KL Divergence, PSI, and automatic fine-tuning",
    version="1.0.0",
    lifespan=lifespan
)


# Request/Response models
class DriftCheckRequest(BaseModel):
    """Manual drift check request"""
    window_days: Optional[int] = Field(default=None, description="Override sliding window days")


class DriftCheckResponse(BaseModel):
    """Drift check response"""
    status: str
    drift_detected: bool
    severity: Optional[str]
    metrics: Dict[str, Any]
    scope_results: List[Dict[str, Any]] = Field(default_factory=list)
    checked_scopes: int = 0
    timestamp: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    is_monitoring: bool
    config: Dict[str, Any]


# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        is_monitoring=drift_monitor.is_monitoring if drift_monitor else False,
        config={
            "kl_threshold": config.kl_threshold,
            "psi_threshold": config.psi_threshold,
            "accuracy_min": config.accuracy_min,
            "sliding_window_days": config.sliding_window_days,
            "check_interval_hours": config.check_interval_hours
        }
    )


@app.post("/drift/check", response_model=DriftCheckResponse)
async def manual_drift_check(request: DriftCheckRequest = None):
    """Manually trigger a drift check"""
    if not drift_monitor:
        raise HTTPException(status_code=503, detail="Drift monitor not initialized")
    
    try:
        # Override window days if specified
        if request and request.window_days:
            original_window = drift_monitor.config.sliding_window_days
            drift_monitor.config.sliding_window_days = request.window_days
            result = await drift_monitor.run_drift_check()
            drift_monitor.config.sliding_window_days = original_window
        else:
            result = await drift_monitor.run_drift_check()
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error"))
        
        return DriftCheckResponse(
            status=result["status"],
            drift_detected=result.get("drift_detected", False),
            severity=result.get("severity"),
            metrics=result.get("metrics", {}),
            scope_results=result.get("scope_results", []),
            checked_scopes=result.get("checked_scopes", 0),
            timestamp=result.get("timestamp", datetime.now().isoformat())
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual drift check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drift/metrics")
async def get_drift_metrics(days: int = 30, scope_type: Optional[str] = None, scope_value: Optional[str] = None):
    """Get historical drift metrics"""
    if not drift_monitor:
        raise HTTPException(status_code=503, detail="Drift monitor not initialized")

    try:
        conn = drift_monitor.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        start_date = datetime.now() - timedelta(days=days)
        
        query = """
            SELECT 
                id, kl_divergence, psi, baseline_accuracy, current_accuracy,
                drift_detected, severity, scope_type, scope_value, timestamp
            FROM drift_metrics
            WHERE timestamp >= %s
        """
        params: List[Any] = [start_date]
        if scope_type and scope_value:
            query += " AND scope_type = %s AND scope_value = %s"
            params.extend([scope_type, scope_value])
        query += " ORDER BY timestamp DESC"

        cursor.execute(query, tuple(params))
        
        results = cursor.fetchall()
        cursor.close()

        return {
            "metrics": [dict(row) for row in results],
            "total": len(results),
            "days": days
        }

    except Exception as e:
        logger.error(f"Failed to get drift metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drift/summary")
async def get_drift_summary():
    """Get drift detection summary"""
    if not drift_monitor:
        raise HTTPException(status_code=503, detail="Drift monitor not initialized")
    
    try:
        conn = drift_monitor.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get summary statistics
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_checks,
                COUNT(*) FILTER (WHERE drift_detected = true) as drift_count,
                COUNT(*) FILTER (WHERE severity = 'critical') as critical_count,
                COUNT(*) FILTER (WHERE severity = 'warning') as warning_count,
                AVG(kl_divergence) as avg_kl,
                AVG(psi) as avg_psi,
                MAX(timestamp) as last_check
            FROM drift_metrics
            WHERE timestamp >= NOW() - INTERVAL '30 days'
            """
        )
        
        summary = cursor.fetchone()
        
        # Get fine-tuning triggers
        cursor.execute(
            """
            SELECT COUNT(*) as trigger_count
            FROM finetuning_triggers
            WHERE trigger_timestamp >= NOW() - INTERVAL '30 days'
            """
        )
        
        trigger_info = cursor.fetchone()

        cursor.execute(
            """
            SELECT scope_type, scope_value,
                   COUNT(*) as total_checks,
                   COUNT(*) FILTER (WHERE drift_detected = true) as drift_count,
                   AVG(kl_divergence) as avg_kl,
                   AVG(psi) as avg_psi,
                   MAX(timestamp) as last_check
            FROM drift_metrics
            WHERE timestamp >= NOW() - INTERVAL '30 days'
              AND scope_type IS NOT NULL
              AND scope_value IS NOT NULL
            GROUP BY scope_type, scope_value
            ORDER BY drift_count DESC, scope_type, scope_value
            """
        )
        scoped_summary = [dict(row) for row in cursor.fetchall()]

        incident_info = {"incident_count": 0}
        try:
            cursor.execute(
                """
                SELECT COUNT(*) as incident_count
                FROM drift_incidents
                WHERE opened_at >= NOW() - INTERVAL '30 days'
                """
            )
            incident_info = cursor.fetchone() or {"incident_count": 0}
        except Exception as incident_error:
            conn.rollback()
            logger.warning(f"Unable to query drift incidents summary: {incident_error}")
        cursor.close()

        return {
            "summary": dict(summary),
            "scoped_summary": scoped_summary,
            "finetuning_triggers": trigger_info['trigger_count'],
            "open_incidents_last_30_days": incident_info["incident_count"],
            "last_finetuning_trigger": drift_monitor.last_finetuning_trigger.isoformat() 
                if drift_monitor.last_finetuning_trigger else None,
            "is_monitoring": drift_monitor.is_monitoring
        }
    
    except Exception as e:
        logger.error(f"Failed to get drift summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drift/incidents")
async def get_drift_incidents(
    days: int = 30,
    status: Optional[str] = None,
    scope_type: Optional[str] = None,
    scope_value: Optional[str] = None,
):
    """List open and historical drift incidents."""
    if not drift_monitor:
        raise HTTPException(status_code=503, detail="Drift monitor not initialized")

    try:
        conn = drift_monitor.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        start_date = datetime.now() - timedelta(days=days)
        query = """
            SELECT
                incident_id, status, severity, scope_type, scope_value,
                summary, recommendation, payload, opened_at, updated_at
            FROM drift_incidents
            WHERE opened_at >= %s
        """
        params: List[Any] = [start_date]

        if status:
            query += " AND status = %s"
            params.append(status)
        if scope_type and scope_value:
            query += " AND scope_type = %s AND scope_value = %s"
            params.extend([scope_type, scope_value])

        query += " ORDER BY opened_at DESC"

        cursor.execute(query, tuple(params))
        incidents = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        return {
            "incidents": incidents,
            "total": len(incidents),
            "days": days,
        }
    except Exception as e:
        logger.error(f"Failed to list drift incidents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/drift/trigger-finetuning")
async def manual_trigger_finetuning():
    """Manually trigger fine-tuning"""
    if not drift_monitor:
        raise HTTPException(status_code=503, detail="Drift monitor not initialized")
    
    try:
        # Run drift check first
        result = await drift_monitor.run_drift_check()
        
        if result.get("status") != "success":
            raise HTTPException(status_code=400, detail="Drift check failed")
        
        # Trigger fine-tuning regardless of drift score
        metrics = result.get("metrics", {})
        if not metrics:
            scope_results = result.get("scope_results", [])
            for scope_result in scope_results:
                if scope_result.get("status") == "success" and scope_result.get("metrics"):
                    metrics = scope_result["metrics"]
                    break
        success = await drift_monitor.trigger_finetuning(metrics)
        
        if success:
            finetuning_triggers_total.labels(trigger_type='manual').inc()
            return {
                "status": "success",
                "message": "Fine-tuning triggered successfully",
                "drift_metrics": metrics
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to trigger fine-tuning")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual fine-tuning trigger failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=config.service_host,
        port=config.service_port,
        log_level="info"
    )
