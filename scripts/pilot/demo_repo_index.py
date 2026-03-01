#!/usr/bin/env python3
"""Pilot demo: index repository files into RAG and verify retrieval (AFR-96)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_API_KEY = os.getenv("PILOT_API_KEY", "sk-test-key-123")
DEFAULT_WORKSPACE_ID = os.getenv("PILOT_WORKSPACE_ID", "default")
DEFAULT_FILES = [
    "README.md",
    "QUICKSTART.md",
    "MCP_QUICKSTART.md",
    "SECURITY_QUICKSTART.md",
    "DISASTER_RECOVERY_RUNBOOK.md",
    "MCP_AFR32_MANUAL_TEST.md",
]


def _parse_json(payload: str) -> Any:
    payload = (payload or "").strip()
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}


def request_json(
    method: str,
    url: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
) -> Tuple[int, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url=url, data=data, method=method.upper())
    request.add_header("Accept", "application/json")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if headers:
        for key, value in headers.items():
            if value:
                request.add_header(key, value)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.getcode(), _parse_json(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, _parse_json(body)
    except urllib.error.URLError as exc:
        return 0, {"error": f"connection_error: {exc}"}


def build_documents(
    repo_root: Path,
    file_list: List[str],
    workspace_id: str,
    max_chars_per_file: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    documents: List[Dict[str, Any]] = []
    used_files: List[str] = []

    for relative_path in file_list:
        candidate = (repo_root / relative_path).resolve()
        if not candidate.is_file():
            continue

        raw_text = candidate.read_text(encoding="utf-8", errors="replace").strip()
        if not raw_text:
            continue

        text = raw_text
        if len(text) > max_chars_per_file:
            text = (
                text[:max_chars_per_file]
                + "\n\n[TRUNCATED FOR PILOT DEMO: source file exceeded max chars]"
            )

        used_files.append(str(candidate.relative_to(repo_root)))
        documents.append(
            {
                "text": text,
                "metadata": {
                    "workspace_id": workspace_id,
                    "source": str(candidate.relative_to(repo_root)),
                    "source_type": "repo_markdown",
                    "indexed_by": "scripts/pilot/demo_repo_index.py",
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        )

    return documents, used_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Index curated repository files into /v1/rag/ingest/batch and verify with search."
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API server base URL")
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID, help="Workspace ID")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key for auth")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument(
        "--files",
        default=",".join(DEFAULT_FILES),
        help="Comma-separated file list relative to repo root",
    )
    parser.add_argument("--max-files", type=int, default=6, help="Maximum files to index")
    parser.add_argument(
        "--max-chars-per-file",
        type=int,
        default=50000,
        help="Maximum characters sent per file",
    )
    parser.add_argument(
        "--verify-query",
        default="MCP ACL role",
        help="Query used to verify retrieval after indexing",
    )
    parser.add_argument("--timeout", type=float, default=45.0, help="HTTP timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Prepare payload only")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        print(f"[FAIL] repo root does not exist: {repo_root}")
        return 2

    raw_files = [item.strip() for item in args.files.split(",") if item.strip()]
    selected_files = raw_files[: max(args.max_files, 0)] if args.max_files > 0 else raw_files

    documents, used_files = build_documents(
        repo_root=repo_root,
        file_list=selected_files,
        workspace_id=args.workspace_id,
        max_chars_per_file=max(args.max_chars_per_file, 1000),
    )

    print("=== Pilot Repo Index Demo ===")
    print(f"API URL: {args.api_url.rstrip('/')}")
    print(f"Workspace: {args.workspace_id}")
    print(f"Selected files: {selected_files}")
    print(f"Files indexed: {used_files}")
    print(f"Documents prepared: {len(documents)}")
    print("")

    if not documents:
        print("[FAIL] No readable files found to index.")
        return 1

    if args.dry_run:
        print("[PASS] Dry-run completed. No HTTP requests sent.")
        return 0

    api_url = args.api_url.rstrip("/")
    headers = {
        "X-Workspace-Id": args.workspace_id,
        "Authorization": f"Bearer {args.api_key}" if args.api_key else "",
        "X-API-Key": args.api_key if args.api_key else "",
    }

    status, body = request_json(
        "POST",
        f"{api_url}/v1/rag/ingest/batch",
        payload={"documents": documents},
        headers=headers,
        timeout=float(args.timeout),
    )
    if status != 200:
        print(f"[FAIL] Batch ingestion failed (status={status})")
        print(f"Response: {body}")
        return 1

    documents_processed = body.get("documents_processed")
    total_chunks = body.get("total_chunks")
    print(
        "[PASS] Batch ingestion completed "
        f"(documents_processed={documents_processed}, total_chunks={total_chunks})"
    )

    status, body = request_json(
        "POST",
        f"{api_url}/v1/rag/search",
        payload={
            "query": args.verify_query,
            "limit": 3,
            "filters": {"workspace_id": args.workspace_id},
        },
        headers=headers,
        timeout=float(args.timeout),
    )
    if status != 200:
        print(f"[FAIL] Verification search failed (status={status})")
        print(f"Response: {body}")
        return 1

    results = body.get("results", []) if isinstance(body, dict) else []
    print(f"[PASS] Verification search returned {len(results)} result(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
