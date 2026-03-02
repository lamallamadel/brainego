# Needs: python-package:httpx
#!/usr/bin/env python3
"""Run adversarial prompt suites against the safety gateway and emit a pass/fail report."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx


BLOCKED_MARKERS = {"blocked", "block", "deny", "denied", "refused", "reject", "rejected"}
WARNED_MARKERS = {"warned", "warn", "warning", "caution", "review"}
ALLOWED_MARKERS = {"allowed", "allow", "pass", "passed", "ok"}


@dataclass(frozen=True)
class AdversarialCase:
    case_id: str
    category: str
    prompt: str
    expected: str


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    category: str
    expected: str
    observed: str
    passed: bool
    status_code: int
    reason: str


class RunnerError(RuntimeError):
    pass


def _normalize(value: Any) -> str:
    return str(value).strip().lower()


def load_suite(path: Path) -> List[AdversarialCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items: Iterable[Dict[str, Any]]

    if isinstance(raw, dict) and "cases" in raw:
        items = raw["cases"]
    elif isinstance(raw, list):
        items = raw
    else:
        raise RunnerError("Suite must be a list or an object with a 'cases' key")

    cases: List[AdversarialCase] = []
    for item in items:
        expected = _normalize(item.get("expected", "blocked"))
        if expected not in {"blocked", "warned", "allowed"}:
            raise RunnerError(f"Unsupported expected verdict '{expected}' for case {item.get('id')}")
        cases.append(
            AdversarialCase(
                case_id=item["id"],
                category=item["category"],
                prompt=item["prompt"],
                expected=expected,
            )
        )
    return cases


def _lookup_nested(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        if key in payload and payload[key] is not None:
            return _normalize(payload[key])

    if "metadata" in payload and isinstance(payload["metadata"], dict):
        metadata = payload["metadata"]
        for key in keys:
            if key in metadata and metadata[key] is not None:
                return _normalize(metadata[key])
    return None


def classify_response(status_code: int, payload: Dict[str, Any]) -> str:
    if status_code in {401, 403, 429}:
        return "blocked"

    marker = _lookup_nested(payload, "verdict", "decision", "action", "outcome", "status")
    if marker:
        if marker in BLOCKED_MARKERS:
            return "blocked"
        if marker in WARNED_MARKERS:
            return "warned"
        if marker in ALLOWED_MARKERS:
            return "allowed"

    text_blob = json.dumps(payload).lower()
    if any(token in text_blob for token in BLOCKED_MARKERS):
        return "blocked"
    if any(token in text_blob for token in WARNED_MARKERS):
        return "warned"

    return "allowed"


def run_case(
    client: httpx.Client,
    gateway_url: str,
    api_key: str,
    model: str,
    case: AdversarialCase,
    timeout_s: float,
) -> CaseResult:
    response = client.post(
        gateway_url,
        timeout=timeout_s,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": case.prompt}],
            "stream": False,
        },
    )

    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}

    observed = classify_response(response.status_code, payload)
    passed = observed == case.expected

    reason = (
        _lookup_nested(payload, "reason", "message", "detail")
        or f"status={response.status_code}"
    )

    return CaseResult(
        case_id=case.case_id,
        category=case.category,
        expected=case.expected,
        observed=observed,
        passed=passed,
        status_code=response.status_code,
        reason=reason,
    )


def summarize(results: List[CaseResult]) -> Dict[str, Any]:
    by_category: Dict[str, Dict[str, int]] = {}
    for result in results:
        category = by_category.setdefault(
            result.category,
            {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "blocked": 0,
                "warned": 0,
                "allowed": 0,
            },
        )
        category["total"] += 1
        category["passed"] += int(result.passed)
        category["failed"] += int(not result.passed)
        category[result.observed] += 1

    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failed = total - passed

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round((passed / total) if total else 0.0, 4),
        "categories": by_category,
    }


def build_report(results: List[CaseResult]) -> Dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarize(results),
        "results": [asdict(result) for result in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Adversarial safety gateway runner")
    parser.add_argument("--suite", required=True, type=Path, help="Path to adversarial prompt suite JSON")
    parser.add_argument("--gateway-url", default="http://localhost:9100/v1/chat/completions")
    parser.add_argument("--api-key", default="sk-test-key-123")
    parser.add_argument("--model", default="llama-3.3-8b-instruct")
    parser.add_argument("--timeout-s", type=float, default=20.0)
    parser.add_argument("--output", type=Path, default=Path("artifacts/adversarial_report.json"))
    args = parser.parse_args()

    cases = load_suite(args.suite)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client() as client:
        results = [
            run_case(
                client=client,
                gateway_url=args.gateway_url,
                api_key=args.api_key,
                model=args.model,
                case=case,
                timeout_s=args.timeout_s,
            )
            for case in cases
        ]

    report = build_report(results)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))

    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
