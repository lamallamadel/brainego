#!/usr/bin/env python3
"""
Workspace registry service for multi-tenant isolation.

Stores workspace lifecycle state (active/disabled) in PostgreSQL so request
paths can enforce strict workspace boundaries consistently.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WORKSPACE_STATUS_ACTIVE = "active"
WORKSPACE_STATUS_DISABLED = "disabled"
_SUPPORTED_WORKSPACE_STATUSES = {WORKSPACE_STATUS_ACTIVE, WORKSPACE_STATUS_DISABLED}


class WorkspaceService:
    """Service responsible for workspace lifecycle persistence."""

    def __init__(
        self,
        db_host: str = "localhost",
        db_port: int = 5432,
        db_name: str = "ai_platform",
        db_user: str = "ai_user",
        db_password: str = "ai_password",
        pool_min_conn: int = 1,
        pool_max_conn: int = 5,
        default_workspace_id: str = "default",
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

            normalized_default = self._normalize_workspace_id(default_workspace_id)
            self.create_workspace(
                workspace_id=normalized_default,
                display_name="Default Workspace",
                metadata={"bootstrap": True},
            )
            logger.info(
                "Workspace Service initialized with PostgreSQL pool (%s-%s connections)",
                pool_min_conn,
                pool_max_conn,
            )
        except Exception as exc:
            logger.error("Failed to initialize Workspace Service: %s", exc)
            raise

    def _get_connection(self):
        return self.pool.getconn()

    def _return_connection(self, conn):
        self.pool.putconn(conn)

    @staticmethod
    def _normalize_workspace_id(workspace_id: Any) -> str:
        normalized = str(workspace_id).strip() if workspace_id is not None else ""
        if not normalized:
            raise ValueError("workspace_id must be a non-empty string")
        return normalized

    @staticmethod
    def _coerce_json(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    @staticmethod
    def _normalize_status(status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized not in _SUPPORTED_WORKSPACE_STATUSES:
            raise ValueError(
                f"Unsupported workspace status='{status}'. "
                f"Supported values: {sorted(_SUPPORTED_WORKSPACE_STATUSES)}"
            )
        return normalized

    def _ensure_schema(self) -> None:
        """Ensure workspace table and indexes exist."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS workspaces (
                        id SERIAL PRIMARY KEY,
                        workspace_id VARCHAR(255) UNIQUE NOT NULL,
                        display_name VARCHAR(255),
                        status VARCHAR(16) NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'disabled')),
                        metadata JSONB DEFAULT '{}'::JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        disabled_at TIMESTAMP WITH TIME ZONE
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_workspaces_workspace_id ON workspaces(workspace_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_workspaces_status ON workspaces(status)"
                )
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)

    def create_workspace(
        self,
        workspace_id: str,
        display_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create or reactivate a workspace."""
        normalized_workspace_id = self._normalize_workspace_id(workspace_id)
        metadata_payload = self._coerce_json(metadata)
        normalized_display_name = (
            str(display_name).strip() if isinstance(display_name, str) else None
        )
        if normalized_display_name == "":
            normalized_display_name = None

        conn = self._get_connection()
        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO workspaces (
                        workspace_id, display_name, status, metadata, disabled_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, NULL)
                    ON CONFLICT (workspace_id)
                    DO UPDATE SET
                        display_name = COALESCE(EXCLUDED.display_name, workspaces.display_name),
                        status = 'active',
                        metadata = COALESCE(workspaces.metadata, '{}'::jsonb)
                                   || COALESCE(EXCLUDED.metadata, '{}'::jsonb),
                        updated_at = CURRENT_TIMESTAMP,
                        disabled_at = NULL
                    RETURNING
                        workspace_id,
                        display_name,
                        status,
                        metadata,
                        created_at,
                        updated_at,
                        disabled_at
                    """,
                    (
                        normalized_workspace_id,
                        normalized_display_name,
                        WORKSPACE_STATUS_ACTIVE,
                        json.dumps(metadata_payload),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return self._normalize_row(dict(row or {}))
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)

    def disable_workspace(
        self,
        workspace_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Disable an existing workspace."""
        normalized_workspace_id = self._normalize_workspace_id(workspace_id)
        metadata_patch: Dict[str, Any] = {}
        if reason and str(reason).strip():
            metadata_patch["disabled_reason"] = str(reason).strip()

        conn = self._get_connection()
        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE workspaces
                    SET
                        status = %s,
                        disabled_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP,
                        metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE workspace_id = %s
                    RETURNING
                        workspace_id,
                        display_name,
                        status,
                        metadata,
                        created_at,
                        updated_at,
                        disabled_at
                    """,
                    (
                        WORKSPACE_STATUS_DISABLED,
                        json.dumps(metadata_patch),
                        normalized_workspace_id,
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise ValueError(f"workspace '{normalized_workspace_id}' does not exist")
                conn.commit()
                return self._normalize_row(dict(row))
        except Exception:
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)

    def get_workspace(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a workspace by ID."""
        normalized_workspace_id = self._normalize_workspace_id(workspace_id)
        conn = self._get_connection()
        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        workspace_id,
                        display_name,
                        status,
                        metadata,
                        created_at,
                        updated_at,
                        disabled_at
                    FROM workspaces
                    WHERE workspace_id = %s
                    """,
                    (normalized_workspace_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return self._normalize_row(dict(row))
        finally:
            self._return_connection(conn)

    def list_workspaces(
        self,
        include_disabled: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List workspaces with optional pagination."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")

        conn = self._get_connection()
        try:
            from psycopg2.extras import RealDictCursor

            where_sql = ""
            params: List[Any] = []
            if not include_disabled:
                where_sql = "WHERE status = %s"
                params.append(WORKSPACE_STATUS_ACTIVE)

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"SELECT COUNT(*) AS total FROM workspaces {where_sql}",
                    params,
                )
                total = int((cur.fetchone() or {}).get("total", 0))
                cur.execute(
                    f"""
                    SELECT
                        workspace_id,
                        display_name,
                        status,
                        metadata,
                        created_at,
                        updated_at,
                        disabled_at
                    FROM workspaces
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, limit, offset],
                )
                rows = cur.fetchall()
                workspaces = [self._normalize_row(dict(row)) for row in rows]
                return {
                    "status": "success",
                    "total": total,
                    "count": len(workspaces),
                    "workspaces": workspaces,
                }
        finally:
            self._return_connection(conn)

    def assert_workspace_active(self, workspace_id: str, context: str) -> str:
        """
        Ensure workspace exists and is active.

        Returns normalized workspace_id when valid.
        """
        normalized_workspace_id = self._normalize_workspace_id(workspace_id)
        workspace = self.get_workspace(normalized_workspace_id)
        if workspace is None:
            raise ValueError(f"{context}: workspace '{normalized_workspace_id}' does not exist")

        status = self._normalize_status(workspace.get("status", ""))
        if status != WORKSPACE_STATUS_ACTIVE:
            raise ValueError(
                f"{context}: workspace '{normalized_workspace_id}' is disabled"
            )
        return normalized_workspace_id

    @staticmethod
    def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        for field in ("created_at", "updated_at", "disabled_at"):
            value = normalized.get(field)
            if value is not None and hasattr(value, "isoformat"):
                normalized[field] = value.isoformat()
        if not isinstance(normalized.get("metadata"), dict):
            normalized["metadata"] = {}
        return normalized

    def close(self) -> None:
        if hasattr(self, "pool"):
            self.pool.closeall()
            logger.info("Workspace Service connection pool closed")
