#!/usr/bin/env python3
"""Workspace context and validation helpers for API request handling."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Set

from fastapi import HTTPException, Request

try:
    import yaml
except Exception:  # pragma: no cover - yaml is expected in production images
    yaml = None

logger = logging.getLogger(__name__)

WORKSPACE_HEADER_NAME = "x-workspace-id"
WORKSPACE_QUERY_PARAM = "workspace_id"
DEFAULT_WORKSPACE_CONFIG_PATH = "configs/memory-budget.yaml"
_NON_WORKSPACE_SECTIONS = {"logging", "performance", "project_overrides", "settings", "servers"}
_WORKSPACE_CONFIG_HINTS = {"workspace_id", "max_total_tokens", "tier_allocation", "scoring_weights"}


def resolve_workspace_id(request: Request) -> Optional[str]:
    """Resolve workspace ID from headers first, then query params."""
    header_workspace = (request.headers.get(WORKSPACE_HEADER_NAME) or "").strip()
    if header_workspace:
        return header_workspace

    query_workspace = (request.query_params.get(WORKSPACE_QUERY_PARAM) or "").strip()
    return query_workspace or None


def _parse_workspace_ids_from_env(raw_workspace_ids: str) -> Set[str]:
    return {
        workspace_id.strip()
        for workspace_id in raw_workspace_ids.split(",")
        if workspace_id and workspace_id.strip()
    }


def _extract_workspace_ids_from_mapping(config_data: Dict[str, Any]) -> Set[str]:
    workspace_ids: Set[str] = set()

    for key, value in config_data.items():
        if key in _NON_WORKSPACE_SECTIONS or not isinstance(value, dict):
            continue

        explicit_workspace = value.get("workspace_id")
        if isinstance(explicit_workspace, str) and explicit_workspace.strip():
            workspace_ids.add(explicit_workspace.strip())

        if any(hint in value for hint in _WORKSPACE_CONFIG_HINTS):
            workspace_ids.add(str(key).strip())

    return workspace_ids


@lru_cache(maxsize=1)
def get_valid_workspace_ids() -> Set[str]:
    """
    Load valid workspace IDs.

    Priority:
      1) WORKSPACE_IDS env (comma-separated)
      2) WORKSPACE_CONFIG_PATH YAML file (default: configs/memory-budget.yaml)
      3) DEFAULT_WORKSPACE_ID env or "default"
    """
    workspace_ids_env = os.getenv("WORKSPACE_IDS", "")
    if workspace_ids_env.strip():
        parsed_ids = _parse_workspace_ids_from_env(workspace_ids_env)
        if parsed_ids:
            logger.info("Loaded %s workspace IDs from WORKSPACE_IDS", len(parsed_ids))
            return parsed_ids

    config_path = Path(os.getenv("WORKSPACE_CONFIG_PATH", DEFAULT_WORKSPACE_CONFIG_PATH))
    if yaml is not None and config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as config_file:
                config_data = yaml.safe_load(config_file) or {}
            if isinstance(config_data, dict):
                parsed_ids = _extract_workspace_ids_from_mapping(config_data)
                if parsed_ids:
                    logger.info(
                        "Loaded %s workspace IDs from %s",
                        len(parsed_ids),
                        config_path,
                    )
                    return parsed_ids
        except Exception as exc:  # pragma: no cover - defensive runtime logging
            logger.warning("Unable to parse workspace config %s: %s", config_path, exc)

    default_workspace_id = os.getenv("DEFAULT_WORKSPACE_ID", "default").strip() or "default"
    logger.warning(
        "Falling back to default workspace allowlist: %s",
        default_workspace_id,
    )
    return {default_workspace_id}


def ensure_workspace_filter(
    filters: Optional[Dict[str, Any]],
    workspace_id: str,
) -> Dict[str, Any]:
    """
    Merge a mandatory workspace filter.

    Rejects payloads that attempt to override workspace scope.
    """
    merged_filters: Dict[str, Any] = dict(filters or {})
    existing_workspace = merged_filters.get("workspace_id")

    if existing_workspace is not None:
        if isinstance(existing_workspace, dict) and "any" in existing_workspace:
            allowed_values = {
                str(value).strip()
                for value in existing_workspace.get("any", [])
                if str(value).strip()
            }
            if workspace_id not in allowed_values:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "workspace_id filter does not match request workspace context. "
                        f"Expected '{workspace_id}'."
                    ),
                )
        elif str(existing_workspace).strip() != workspace_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "workspace_id filter does not match request workspace context. "
                    f"Expected '{workspace_id}'."
                ),
            )

    merged_filters["workspace_id"] = workspace_id
    return merged_filters


def ensure_workspace_metadata(
    metadata: Optional[Dict[str, Any]],
    workspace_id: str,
) -> Dict[str, Any]:
    """Merge a mandatory workspace_id metadata attribute."""
    merged_metadata: Dict[str, Any] = dict(metadata or {})
    existing_workspace = merged_metadata.get("workspace_id")

    if existing_workspace is not None and str(existing_workspace).strip() != workspace_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "metadata.workspace_id does not match request workspace context. "
                f"Expected '{workspace_id}'."
            ),
        )

    merged_metadata["workspace_id"] = workspace_id
    return merged_metadata
