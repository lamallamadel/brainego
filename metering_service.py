#!/usr/bin/env python3
"""
Workspace-scoped metering event persistence.

Tracks usage counters (RAG retrievals, MCP tool calls, etc.) with mandatory
workspace_id to guarantee tenant-isolated metering.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MeteringService:
    """Service responsible for storing and aggregating metering events."""

    def __init__(
        self,
        db_host: str = "localhost",
        db_port: int = 5432,
        db_name: str = "ai_platform",
        db_user: str = "ai_user",
        db_password: str = "ai_password",
        pool_min_conn: int = 1,
        pool_max_conn: int = 5,
    ):
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password

        try:
            from psycopg2.pool import ThreadedConnectionPool

            self.pool = ThreadedConnectionPool(
                pool_min_conn,
                pool_max_conn,
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
            )
            self._ensure_schema()
            logger.info(
                "Metering Service initialized with PostgreSQL pool (%s-%s connections)",
                pool_min_conn,
                pool_max_conn,
            )
        except Exception as exc:
            logger.error("Failed to initialize Metering Service: %s", exc)
            raise

    def _get_connection(self):
        return self.pool.getconn()

    def _return_connection(self, conn):
        self.pool.putconn(conn)

    @staticmethod
    def _normalize_workspace_id(workspace_id: Any) -> str:
        normalized = str(workspace_id).strip() if workspace_id is not None else ""
        if not normalized:
            raise ValueError("workspace_id is required for metering events")
        return normalized

    @staticmethod
    def _normalize_meter_key(meter_key: Any) -> str:
        normalized = str(meter_key).strip() if meter_key is not None else ""
        if not normalized:
            raise ValueError("meter_key is required for metering events")
        return normalized

    @staticmethod
    def _coerce_json(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def _ensure_schema(self) -> None:
        """Ensure metering schema exists."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workspace_metering_events (
                        id SERIAL PRIMARY KEY,
                        event_id VARCHAR(255) UNIQUE NOT NULL,
                        workspace_id VARCHAR(255) NOT NULL,
                        meter_key VARCHAR(128) NOT NULL,
                        quantity DOUBLE PRECISION NOT NULL DEFAULT 1,
                        request_id VARCHAR(255),
                        metadata JSONB DEFAULT '{}'::JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_metering_workspace_id "
                    "ON workspace_metering_events(workspace_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_metering_meter_key "
                    "ON workspace_metering_events(meter_key)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_metering_created_at "
                    "ON workspace_metering_events(created_at)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_metering_workspace_meter_key "
                    "ON workspace_metering_events(workspace_id, meter_key)"
                )
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)

    def add_event(
        self,
        *,
        workspace_id: str,
        meter_key: str,
        quantity: float = 1.0,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Persist one metering event."""
        normalized_workspace_id = self._normalize_workspace_id(workspace_id)
        normalized_meter_key = self._normalize_meter_key(meter_key)
        quantity_value = float(quantity)
        if quantity_value < 0:
            raise ValueError("quantity must be >= 0")

        resolved_event_id = event_id or str(uuid.uuid4())
        resolved_created_at = created_at or datetime.utcnow()
        metadata_payload = self._coerce_json(metadata)

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workspace_metering_events (
                        event_id,
                        workspace_id,
                        meter_key,
                        quantity,
                        request_id,
                        metadata,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                    RETURNING event_id, created_at
                    """,
                    (
                        resolved_event_id,
                        normalized_workspace_id,
                        normalized_meter_key,
                        quantity_value,
                        request_id,
                        json.dumps(metadata_payload),
                        resolved_created_at,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return {
                    "status": "success",
                    "event_id": row[0],
                    "workspace_id": normalized_workspace_id,
                    "meter_key": normalized_meter_key,
                    "quantity": quantity_value,
                    "created_at": row[1].isoformat() if row and row[1] else resolved_created_at.isoformat(),
                }
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)

    @staticmethod
    def _build_summary_filters(
        workspace_id: Optional[str] = None,
        meter_key: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[str, List[Any]]:
        where_clauses: List[str] = []
        params: List[Any] = []

        if workspace_id:
            where_clauses.append("workspace_id = %s")
            params.append(workspace_id)
        if meter_key:
            where_clauses.append("meter_key = %s")
            params.append(meter_key)
        if start_date:
            where_clauses.append("created_at >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("created_at <= %s")
            params.append(end_date)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        return where_sql, params

    def summarize_usage(
        self,
        *,
        workspace_id: Optional[str] = None,
        meter_key: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Aggregate metering events grouped by workspace and key."""
        normalized_workspace_id = (
            self._normalize_workspace_id(workspace_id) if workspace_id is not None else None
        )
        normalized_meter_key = (
            self._normalize_meter_key(meter_key) if meter_key is not None else None
        )
        where_sql, params = self._build_summary_filters(
            workspace_id=normalized_workspace_id,
            meter_key=normalized_meter_key,
            start_date=start_date,
            end_date=end_date,
        )

        conn = self._get_connection()
        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
                        workspace_id,
                        meter_key,
                        COUNT(*) AS events,
                        COALESCE(SUM(quantity), 0) AS total_quantity
                    FROM workspace_metering_events
                    {where_sql}
                    GROUP BY workspace_id, meter_key
                    ORDER BY workspace_id ASC, meter_key ASC
                    """,
                    params,
                )
                rows = cur.fetchall()
                records = [
                    {
                        "workspace_id": str(row["workspace_id"]),
                        "meter_key": str(row["meter_key"]),
                        "events": int(row["events"] or 0),
                        "total_quantity": float(row["total_quantity"] or 0),
                    }
                    for row in rows
                ]
                return {
                    "status": "success",
                    "workspace_id": normalized_workspace_id,
                    "meter_key": normalized_meter_key,
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "count": len(records),
                    "records": records,
                }
        finally:
            self._return_connection(conn)

    def close(self) -> None:
        if hasattr(self, "pool"):
            self.pool.closeall()
            logger.info("Metering Service connection pool closed")
