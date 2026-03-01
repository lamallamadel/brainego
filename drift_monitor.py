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
    
    # Fine-tuning
    auto_trigger_finetuning: bool = Field(default=True)
    learning_engine_url: str = Field(default="http://learning-engine:8003")
    min_drift_score: float = Field(default=0.3)
    cooldown_hours: int = Field(default=168)
    
    # Database
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="ai_platform")
    postgres_user: str = Field(default="ai_user")
    postgres_password: str = Field(default="ai_password")


def load_config(config_path: str = "configs/drift-monitor.yaml") -> DriftMonitorConfig:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r') as f:
            yaml_config = yaml.safe_load(f)
        
        thresholds = load_thresholds(yaml_config)
        alert_event_policies = load_alert_event_policies(yaml_config)
        severity_policies = load_severity_policies(yaml_config)

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
            "auto_trigger_finetuning": yaml_config.get("fine_tuning", {}).get("auto_trigger", True),
            "learning_engine_url": yaml_config.get("fine_tuning", {}).get("learning_engine_url", "http://learning-engine:8003"),
            "min_drift_score": yaml_config.get("fine_tuning", {}).get("min_drift_score", 0.3),
            "cooldown_hours": yaml_config.get("fine_tuning", {}).get("cooldown_hours", 168),
            "postgres_host": yaml_config.get("database", {}).get("host", "postgres"),
            "postgres_port": yaml_config.get("database", {}).get("port", 5432),
            "postgres_db": yaml_config.get("database", {}).get("name", "ai_platform"),
            "postgres_user": yaml_config.get("database", {}).get("user", "ai_user"),
            "postgres_password": yaml_config.get("database", {}).get("password", "ai_password"),
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
        offset_days: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get feedback data from database for a specific time window.
        
        Args:
            days: Number of days in the window
            offset_days: Offset from current time (0 = current, 7 = previous week)
        
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
        
        cursor.execute(query, (start_date, end_date))
        results = cursor.fetchall()
        cursor.close()
        
        return [dict(row) for row in results]
    
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
        baseline_distribution: Dict[str, int],
        current_distribution: Dict[str, int]
    ) -> float:
        """
        Calculate Population Stability Index (PSI) for intent distributions.
        
        PSI measures the shift in distribution between two periods.
        PSI < 0.1: No significant change
        PSI 0.1-0.2: Moderate change
        PSI > 0.2: Significant change (drift detected)
        
        Args:
            baseline_distribution: Baseline intent counts
            current_distribution: Current intent counts
        
        Returns:
            PSI value
        """
        # Ensure all categories are present in both distributions
        all_intents = set(baseline_distribution.keys()) | set(current_distribution.keys())
        
        psi = 0.0
        epsilon = 1e-10
        
        # Calculate total counts
        baseline_total = sum(baseline_distribution.values()) or 1
        current_total = sum(current_distribution.values()) or 1
        
        for intent in all_intents:
            baseline_count = baseline_distribution.get(intent, 0)
            current_count = current_distribution.get(intent, 0)
            
            # Calculate percentages
            baseline_pct = (baseline_count / baseline_total) + epsilon
            current_pct = (current_count / current_total) + epsilon
            
            # PSI formula: (actual% - expected%) * ln(actual% / expected%)
            psi += (current_pct - baseline_pct) * np.log(current_pct / baseline_pct)
        
        return float(psi)
    
    def get_intent_distribution(self, feedback_data: List[Dict]) -> Dict[str, int]:
        """
        Get intent distribution from feedback data.
        
        Args:
            feedback_data: List of feedback records
        
        Returns:
            Dictionary mapping intent to count
        """
        distribution = {}
        for record in feedback_data:
            intent = record.get('intent', 'unknown')
            if intent:
                distribution[intent] = distribution.get(intent, 0) + 1
        
        return distribution
    
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
                    "title": f"[{severity.upper()}] Drift Monitor Alert",
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
        
        try:
            url = f"{self.config.learning_engine_url}/train"
            payload = {
                "days": self.config.sliding_window_days,
                "force": True
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=30.0)
                
                if response.status_code == 200:
                    result = response.json()
                    self.last_finetuning_trigger = datetime.now()
                    
                    # Store trigger record
                    self.store_finetuning_trigger(drift_metrics, result)
                    
                    # Update Prometheus metrics
                    finetuning_triggers_total.labels(trigger_type='automatic').inc()
                    
                    logger.info(f"Fine-tuning triggered: {result.get('job_id')}")
                    
                    # Send success alert
                    await self.send_slack_alert(
                        "info",
                        f"Event: finetuning_triggered\nAutomatic fine-tuning triggered due to drift detection.\nJob ID: {result.get('job_id')}",
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
        severity: Optional[str] = None
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
                    drift_detected, severity, timestamp
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    kl_divergence, psi, baseline_accuracy, current_accuracy,
                    drift_detected, severity, datetime.now()
                )
            )
            conn.commit()
            logger.info(f"Drift metrics stored: KL={kl_divergence:.4f}, PSI={psi:.4f}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to store drift metrics: {e}")
        finally:
            cursor.close()
    
    def store_finetuning_trigger(self, drift_metrics: Dict, trigger_result: Dict):
        """
        Store fine-tuning trigger record.
        
        Args:
            drift_metrics: Drift metrics that triggered fine-tuning
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
                    json.dumps(drift_metrics),
                    datetime.now()
                )
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to store fine-tuning trigger: {e}")
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
            # Get baseline data (previous window)
            baseline_data = self.get_feedback_data(
                days=self.config.sliding_window_days,
                offset_days=self.config.sliding_window_days
            )
            
            # Get current data (current window)
            current_data = self.get_feedback_data(
                days=self.config.sliding_window_days,
                offset_days=0
            )
            
            logger.info(f"Baseline samples: {len(baseline_data)}")
            logger.info(f"Current samples: {len(current_data)}")
            
            # Check minimum sample requirements
            if len(baseline_data) < self.config.min_samples or len(current_data) < self.config.min_samples:
                logger.warning(f"Insufficient samples for drift detection")
                drift_checks_total.labels(status='skipped').inc()
                return {
                    "status": "skipped",
                    "reason": "insufficient_samples",
                    "baseline_count": len(baseline_data),
                    "current_count": len(current_data)
                }
            
            # 1. Calculate KL Divergence on embeddings
            logger.info("Calculating KL Divergence on embeddings...")
            baseline_texts = [f"{r['query']}\n{r['response']}" for r in baseline_data]
            current_texts = [f"{r['query']}\n{r['response']}" for r in current_data]
            
            baseline_embeddings = self.compute_embeddings(baseline_texts)
            current_embeddings = self.compute_embeddings(current_texts)
            
            kl_divergence = self.calculate_kl_divergence(baseline_embeddings, current_embeddings)
            logger.info(f"  KL Divergence: {kl_divergence:.4f} (threshold: {self.config.kl_threshold})")
            
            # 2. Calculate PSI on intent distributions
            logger.info("Calculating PSI on intent distributions...")
            baseline_intent_dist = self.get_intent_distribution(baseline_data)
            current_intent_dist = self.get_intent_distribution(current_data)
            
            psi = self.calculate_psi(baseline_intent_dist, current_intent_dist)
            logger.info(f"  PSI: {psi:.4f} (threshold: {self.config.psi_threshold})")
            
            # 3. Calculate accuracy metrics
            logger.info("Calculating accuracy metrics...")
            baseline_accuracy_metrics = self.calculate_accuracy_metrics(baseline_data)
            current_accuracy_metrics = self.calculate_accuracy_metrics(current_data)
            
            baseline_accuracy = baseline_accuracy_metrics['accuracy']
            current_accuracy = current_accuracy_metrics['accuracy']
            accuracy_delta = baseline_accuracy - current_accuracy
            
            logger.info(f"  Baseline accuracy: {baseline_accuracy:.4f}")
            logger.info(f"  Current accuracy: {current_accuracy:.4f}")
            logger.info(f"  Accuracy delta: {accuracy_delta:.4f}")
            
            # 4. Detect drift
            kl_drift = kl_divergence > self.config.kl_threshold
            psi_drift = psi > self.config.psi_threshold
            accuracy_drift = current_accuracy < self.config.accuracy_min
            
            drift_detected = kl_drift or psi_drift or accuracy_drift
            
            # Calculate combined drift score
            kl_score = kl_divergence / self.config.kl_threshold
            psi_score = psi / self.config.psi_threshold
            accuracy_score = max(0, accuracy_delta / (1 - self.config.accuracy_min))
            combined_drift_score = (kl_score + psi_score + accuracy_score) / 3
            
            # Determine severity from policy multipliers
            severity = None
            if drift_detected:
                if (
                    kl_divergence > self.config.kl_threshold * self.config.critical_kl_multiplier
                    or psi > self.config.psi_threshold * self.config.critical_psi_multiplier
                    or accuracy_delta > self.config.critical_accuracy_drop
                ):
                    severity = "critical"
                elif (
                    kl_divergence > self.config.kl_threshold * self.config.warning_kl_multiplier
                    or psi > self.config.psi_threshold * self.config.warning_psi_multiplier
                    or accuracy_delta > self.config.warning_accuracy_drop
                ):
                    severity = "warning"
                else:
                    severity = "info"
            
            logger.info("=" * 60)
            logger.info(f"Drift Detection Result: {'DRIFT DETECTED' if drift_detected else 'NO DRIFT'}")
            if severity:
                logger.info(f"Severity: {severity.upper()}")
            logger.info(f"Combined Drift Score: {combined_drift_score:.4f}")
            logger.info("=" * 60)
            
            # Prepare metrics
            metrics = {
                "kl_divergence": kl_divergence,
                "psi": psi,
                "baseline_accuracy": baseline_accuracy,
                "current_accuracy": current_accuracy,
                "accuracy_delta": accuracy_delta,
                "combined_drift_score": combined_drift_score,
                "drift_detected": drift_detected,
                "severity": severity
            }
            
            # Store metrics
            self.store_drift_metrics(
                kl_divergence, psi, baseline_accuracy, current_accuracy,
                drift_detected, severity
            )
            
            # Update Prometheus metrics
            kl_divergence_gauge.set(kl_divergence)
            psi_gauge.set(psi)
            baseline_accuracy_gauge.set(baseline_accuracy)
            current_accuracy_gauge.set(current_accuracy)
            combined_drift_score_gauge.set(combined_drift_score)
            drift_checks_total.labels(status='success').inc()
            
            if drift_detected and severity:
                drift_detected_total.labels(severity=severity).inc()
            
            # Send event-based alerts
            if drift_detected and self.config.drift_detected_alert_enabled:
                drift_severity = self.config.drift_detected_alert_severity
                message = (
                    f"Event: drift_detected\n"
                    f"Model drift detected with {drift_severity} severity.\n"
                    f"KL Divergence: {kl_divergence:.4f} (threshold: {self.config.kl_threshold})\n"
                    f"PSI: {psi:.4f} (threshold: {self.config.psi_threshold})\n"
                    f"Current Accuracy: {current_accuracy:.4f} (minimum: {self.config.accuracy_min})\n"
                    f"Combined Drift Score: {combined_drift_score:.4f}"
                )
                await self.send_slack_alert(drift_severity, message, metrics)

            accuracy_drop_event = accuracy_delta >= self.config.accuracy_drop_min
            if accuracy_drop_event and self.config.accuracy_drop_alert_enabled:
                accuracy_severity = self.config.accuracy_drop_alert_severity
                accuracy_message = (
                    f"Event: accuracy_drop\n"
                    f"Accuracy drop detected with {accuracy_severity} severity.\n"
                    f"Baseline Accuracy: {baseline_accuracy:.4f}\n"
                    f"Current Accuracy: {current_accuracy:.4f}\n"
                    f"Accuracy Delta: {accuracy_delta:.4f} (minimum drop: {self.config.accuracy_drop_min:.4f})"
                )
                await self.send_slack_alert(accuracy_severity, accuracy_message, metrics)

            # Trigger fine-tuning if score exceeds threshold
            if drift_detected and combined_drift_score >= self.config.min_drift_score:
                logger.info(f"Drift score {combined_drift_score:.4f} exceeds threshold {self.config.min_drift_score}")
                await self.trigger_finetuning(metrics)
            
            # Record duration
            duration = asyncio.get_event_loop().time() - start_time
            drift_check_duration.observe(duration)
            
            return {
                "status": "success",
                "drift_detected": drift_detected,
                "severity": severity,
                "metrics": metrics,
                "baseline_samples": len(baseline_data),
                "current_samples": len(current_data),
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
            timestamp=result.get("timestamp", datetime.now().isoformat())
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual drift check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/drift/metrics")
async def get_drift_metrics(days: int = 30):
    """Get historical drift metrics"""
    if not drift_monitor:
        raise HTTPException(status_code=503, detail="Drift monitor not initialized")
    
    try:
        conn = drift_monitor.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        start_date = datetime.now() - timedelta(days=days)
        
        cursor.execute(
            """
            SELECT 
                id, kl_divergence, psi, baseline_accuracy, current_accuracy,
                drift_detected, severity, timestamp
            FROM drift_metrics
            WHERE timestamp >= %s
            ORDER BY timestamp DESC
            """,
            (start_date,)
        )
        
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
        cursor.close()
        
        return {
            "summary": dict(summary),
            "finetuning_triggers": trigger_info['trigger_count'],
            "last_finetuning_trigger": drift_monitor.last_finetuning_trigger.isoformat() 
                if drift_monitor.last_finetuning_trigger else None,
            "is_monitoring": drift_monitor.is_monitoring
        }
    
    except Exception as e:
        logger.error(f"Failed to get drift summary: {e}", exc_info=True)
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
