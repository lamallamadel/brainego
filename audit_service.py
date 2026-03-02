#!/usr/bin/env python3
"""
Audit event persistence and export service.

Stores structured audit events (HTTP requests + tool calls) in PostgreSQL and
supports filtered export as JSON/CSV.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_EVENT_TYPE_ALIASES = {
    "request": "request_event",
    "request_event": "request_event",
    "tool_call": "tool_event",
    "tool_event": "tool_event",
    "mcp_tool_call": "tool_event",
}
_SUPPORTED_EVENT_TYPES = {"request_event", "tool_event"}
_EVENT_TYPE_FILTER_VALUES = {
    "request_event": ["request_event", "request"],
    "tool_event": ["tool_event", "tool_call", "mcp_tool_call"],
}


class AuditService:
    """Service responsible for storing and exporting structured audit events."""

    def __init__(
        self,
        db_host: str = "localhost",
        db_port: int = 5432,
        db_name: str = "ai_platform",
        db_user: str = "ai_user",
        db_password: str = "ai_password",
        pool_min_conn: int = 2,
        pool_max_conn: int = 10,
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
                "Audit Service initialized with PostgreSQL pool (%s-%s connections)",
                pool_min_conn,
                pool_max_conn,
            )
        except Exception as exc:
            logger.error("Failed to initialize Audit Service connection pool: %s", exc)
            raise

    def _get_connection(self):
        """Get a connection from the pool."""
        return self.pool.getconn()

    def _return_connection(self, conn):
        """Return a connection to the pool."""
        self.pool.putconn(conn)

    def _ensure_schema(self):
        """
        Ensure core audit schema exists.

        The canonical schema is also declared in init-scripts/postgres/init.sql;
        this guard keeps the service robust if initialization order changes.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_events (
                        id SERIAL PRIMARY KEY,
                        event_id VARCHAR(255) UNIQUE NOT NULL,
                        event_type VARCHAR(32) NOT NULL CHECK (
                            event_type IN ('request_event', 'tool_event', 'request', 'tool_call', 'mcp_tool_call')
                        ),
                        timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        request_id VARCHAR(255),
                        workspace_id VARCHAR(255),
                        user_id VARCHAR(255),
                        role VARCHAR(64),
                        model VARCHAR(255),
                        status VARCHAR(32),
                        tool_name VARCHAR(255),
                        tool_calls JSONB DEFAULT '[]'::JSONB,
                        endpoint TEXT,
                        method VARCHAR(16),
                        status_code INTEGER,
                        latency_ms DOUBLE PRECISION,
                        duration_ms DOUBLE PRECISION,
                        redacted_arguments JSONB DEFAULT '{}'::JSONB,
                        request_payload JSONB DEFAULT '{}'::JSONB,
                        response_payload JSONB DEFAULT '{}'::JSONB,
                        metadata JSONB DEFAULT '{}'::JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cur.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS role VARCHAR(64)")
                cur.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS model VARCHAR(255)")
                cur.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS status VARCHAR(32)")
                cur.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS tool_calls JSONB DEFAULT '[]'::JSONB")
                cur.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS latency_ms DOUBLE PRECISION")
                cur.execute(
                    "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS redacted_arguments JSONB DEFAULT '{}'::JSONB"
                )
                cur.execute("ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_event_type_check")
                cur.execute(
                    """
                    ALTER TABLE audit_events
                    ADD CONSTRAINT audit_events_event_type_check
                    CHECK (event_type IN ('request_event', 'tool_event', 'request', 'tool_call', 'mcp_tool_call'))
                    """
                )
                cur.execute(
                    """
                    UPDATE audit_events
                    SET latency_ms = duration_ms
                    WHERE latency_ms IS NULL
                      AND duration_ms IS NOT NULL
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_workspace_id ON audit_events(workspace_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_user_id ON audit_events(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_role ON audit_events(role)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_model ON audit_events(model)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_status ON audit_events(status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_tool_name ON audit_events(tool_name)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_event_type ON audit_events(event_type)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_request_id ON audit_events(request_id)")
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)

    @staticmethod
    def _normalize_event_type(event_type: Optional[str]) -> str:
        normalized = str(event_type or "").strip().lower()
        canonical = _EVENT_TYPE_ALIASES.get(normalized)
        if canonical:
            return canonical
        supported = sorted(_SUPPORTED_EVENT_TYPES)
        aliases = sorted(_EVENT_TYPE_ALIASES)
        raise ValueError(
            f"Unsupported audit event_type='{event_type}'. "
            f"Supported values: {supported}. Accepted aliases: {aliases}"
        )

    @staticmethod
    def _event_type_filter_values(event_type: Optional[str]) -> List[str]:
        canonical = AuditService._normalize_event_type(event_type)
        return list(_EVENT_TYPE_FILTER_VALUES[canonical])

    @staticmethod
    def _normalize_workspace_id(workspace_id: Optional[str]) -> str:
        normalized = str(workspace_id).strip() if workspace_id is not None else ""
        if not normalized:
            raise ValueError("workspace_id is required for audit events")
        return normalized

    @staticmethod
    def _coerce_json(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            return {}
        return value

    @staticmethod
    def _normalize_status(status: Optional[str], status_code: Optional[int]) -> Optional[str]:
        normalized = str(status).strip().lower() if status is not None else ""
        if normalized:
            return normalized
        if status_code is None:
            return None
        if status_code in {401, 403}:
            return "denied"
        if status_code < 400:
            return "success"
        return "error"

    @staticmethod
    def _extract_model(
        explicit_model: Optional[str],
        request_payload: Dict[str, Any],
        response_payload: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Optional[str]:
        candidates = [
            explicit_model,
            metadata.get("model"),
            metadata.get("model_name"),
            request_payload.get("model"),
            request_payload.get("model_name"),
            request_payload.get("preferred_model"),
            response_payload.get("model"),
            response_payload.get("model_name"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    @staticmethod
    def _extract_tool_calls(
        explicit_tool_calls: Optional[List[str]],
        tool_name: Optional[str],
        request_payload: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> List[str]:
        raw_candidates: List[str] = []

        if isinstance(explicit_tool_calls, list):
            raw_candidates.extend(str(item).strip() for item in explicit_tool_calls if str(item).strip())

        for payload in (metadata, request_payload):
            if not isinstance(payload, dict):
                continue
            for key in ("tool_calls", "tools_called"):
                value = payload.get(key)
                if isinstance(value, list):
                    raw_candidates.extend(str(item).strip() for item in value if str(item).strip())

        if isinstance(tool_name, str) and tool_name.strip():
            raw_candidates.append(tool_name.strip())

        unique_tool_calls: List[str] = []
        seen: set[str] = set()
        for candidate in raw_candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                unique_tool_calls.append(candidate)
        return unique_tool_calls

    @staticmethod
    def _extract_redacted_arguments(
        explicit_redacted_arguments: Optional[Dict[str, Any]],
        request_payload: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        if isinstance(explicit_redacted_arguments, dict):
            return explicit_redacted_arguments
        metadata_args = metadata.get("redacted_arguments") if isinstance(metadata, dict) else None
        if isinstance(metadata_args, dict):
            return metadata_args
        request_args = request_payload.get("arguments") if isinstance(request_payload, dict) else None
        if isinstance(request_args, dict):
            return request_args
        return {}

    def add_event(
        self,
        event_type: str,
        request_id: Optional[str],
        endpoint: Optional[str],
        method: Optional[str],
        status_code: Optional[int],
        workspace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        model: Optional[str] = None,
        status: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_calls: Optional[List[str]] = None,
        latency_ms: Optional[float] = None,
        duration_ms: Optional[float] = None,
        redacted_arguments: Optional[Dict[str, Any]] = None,
        request_payload: Optional[Dict[str, Any]] = None,
        response_payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Persist one audit event.

        Returns:
            Dict containing status, event_id, and timestamp.
        """
        resolved_event_type = self._normalize_event_type(event_type)
        resolved_event_id = event_id or str(uuid.uuid4())
        resolved_timestamp = timestamp or datetime.utcnow()
        resolved_workspace_id = self._normalize_workspace_id(workspace_id)
        req_payload = self._coerce_json(request_payload)
        resp_payload = self._coerce_json(response_payload)
        meta_payload = self._coerce_json(metadata)
        resolved_model = self._extract_model(model, req_payload, resp_payload, meta_payload)
        resolved_status = self._normalize_status(status, status_code)
        resolved_latency_ms = latency_ms if latency_ms is not None else duration_ms
        resolved_duration_ms = duration_ms if duration_ms is not None else latency_ms
        resolved_tool_calls = self._extract_tool_calls(
            explicit_tool_calls=tool_calls,
            tool_name=tool_name,
            request_payload=req_payload,
            metadata=meta_payload,
        )
        resolved_redacted_arguments = self._extract_redacted_arguments(
            explicit_redacted_arguments=redacted_arguments,
            request_payload=req_payload,
            metadata=meta_payload,
        )

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_events (
                        event_id, event_type, timestamp, request_id,
                        workspace_id, user_id, role, model, status, tool_name, tool_calls,
                        endpoint, method, status_code, latency_ms, duration_ms,
                        redacted_arguments, request_payload, response_payload, metadata
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                    )
                    RETURNING event_id, timestamp
                    """,
                    (
                        resolved_event_id,
                        resolved_event_type,
                        resolved_timestamp,
                        request_id,
                        resolved_workspace_id,
                        user_id,
                        role,
                        resolved_model,
                        resolved_status,
                        tool_name,
                        json.dumps(resolved_tool_calls),
                        endpoint,
                        method,
                        status_code,
                        resolved_latency_ms,
                        resolved_duration_ms,
                        json.dumps(resolved_redacted_arguments),
                        json.dumps(req_payload),
                        json.dumps(resp_payload),
                        json.dumps(meta_payload),
                    ),
                )
                inserted = cur.fetchone()
                conn.commit()
                return {
                    "status": "success",
                    "event_id": inserted[0],
                    "timestamp": inserted[1].isoformat() if inserted and inserted[1] else resolved_timestamp.isoformat(),
                }
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)

    @staticmethod
    def _build_filters(
        workspace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        model: Optional[str] = None,
        status: Optional[str] = None,
        tool_name: Optional[str] = None,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[str, List[Any]]:
        where_clauses: List[str] = []
        params: List[Any] = []

        if workspace_id:
            where_clauses.append("workspace_id = %s")
            params.append(workspace_id)
        if user_id:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        if role:
            where_clauses.append("role = %s")
            params.append(role)
        if model:
            where_clauses.append("model = %s")
            params.append(model)
        if status:
            where_clauses.append("status = %s")
            params.append(status)
        if tool_name:
            where_clauses.append("tool_name = %s")
            params.append(tool_name)
        if event_type:
            where_clauses.append("event_type = ANY(%s)")
            params.append(AuditService._event_type_filter_values(event_type))
        if start_date:
            where_clauses.append("timestamp >= %s")
            params.append(start_date)
        if end_date:
            where_clauses.append("timestamp <= %s")
            params.append(end_date)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        return where_sql, params

    @staticmethod
    def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        ts = normalized.get("timestamp")
        if isinstance(ts, datetime):
            normalized["timestamp"] = ts.isoformat()
        return normalized

    def list_events(
        self,
        workspace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        model: Optional[str] = None,
        status: Optional[str] = None,
        tool_name: Optional[str] = None,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Retrieve audit events with optional filters and pagination.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")

        where_sql, params = self._build_filters(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            model=model,
            status=status,
            tool_name=tool_name,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
        )

        conn = self._get_connection()
        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"SELECT COUNT(*) AS total_events FROM audit_events {where_sql}",
                    params,
                )
                count_row = cur.fetchone() or {"total_events": 0}
                total_events = int(count_row["total_events"])

                cur.execute(
                    f"""
                    SELECT
                        event_id,
                        event_type,
                        timestamp,
                        request_id,
                        workspace_id,
                        user_id,
                        role,
                        model,
                        status,
                        tool_name,
                        tool_calls,
                        endpoint,
                        method,
                        status_code,
                        latency_ms,
                        duration_ms,
                        redacted_arguments,
                        request_payload,
                        response_payload,
                        metadata
                    FROM audit_events
                    {where_sql}
                    ORDER BY timestamp DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, limit, offset],
                )
                rows = cur.fetchall()
                events = [self._normalize_row(dict(row)) for row in rows]
                return {
                    "status": "success",
                    "total_events": total_events,
                    "count": len(events),
                    "events": events,
                }
        finally:
            self._return_connection(conn)

    @staticmethod
    def _to_csv(events: List[Dict[str, Any]]) -> str:
        output = io.StringIO()
        fieldnames = [
            "event_id",
            "event_type",
            "timestamp",
            "request_id",
            "workspace_id",
            "user_id",
            "role",
            "model",
            "status",
            "tool_name",
            "tool_calls",
            "endpoint",
            "method",
            "status_code",
            "latency_ms",
            "duration_ms",
            "redacted_arguments",
            "request_payload",
            "response_payload",
            "metadata",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            serialized = dict(event)
            serialized["tool_calls"] = json.dumps(serialized.get("tool_calls", []), ensure_ascii=False)
            serialized["redacted_arguments"] = json.dumps(
                serialized.get("redacted_arguments", {}),
                ensure_ascii=False,
            )
            serialized["request_payload"] = json.dumps(serialized.get("request_payload", {}), ensure_ascii=False)
            serialized["response_payload"] = json.dumps(serialized.get("response_payload", {}), ensure_ascii=False)
            serialized["metadata"] = json.dumps(serialized.get("metadata", {}), ensure_ascii=False)
            writer.writerow(serialized)
        return output.getvalue()

    def export_events(
        self,
        export_format: str = "json",
        workspace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        model: Optional[str] = None,
        status: Optional[str] = None,
        tool_name: Optional[str] = None,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Export audit events in JSON or CSV format.
        """
        fmt = (export_format or "json").lower().strip()
        if fmt not in {"json", "csv"}:
            raise ValueError("export_format must be one of: json, csv")

        result = self.list_events(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            model=model,
            status=status,
            tool_name=tool_name,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        filters = {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": role,
            "model": model,
            "status": status,
            "tool_name": tool_name,
            "event_type": event_type,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "limit": limit,
            "offset": offset,
        }

        if fmt == "csv":
            csv_data = self._to_csv(result["events"])
            return {
                "status": "success",
                "format": "csv",
                "total_events": result["total_events"],
                "count": result["count"],
                "filters": filters,
                "csv_data": csv_data,
            }

        return {
            "status": "success",
            "format": "json",
            "total_events": result["total_events"],
            "count": result["count"],
            "filters": filters,
            "events": result["events"],
        }

    def close(self):
        """Close all database connections."""
        if hasattr(self, "pool"):
            self.pool.closeall()
            logger.info("Audit Service connection pool closed")
