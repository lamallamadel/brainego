#!/usr/bin/env python3
"""Ferrari benchmark harness (ENG-1).

Single-command runner that evaluates grounded-first behavior and emits:
- reports/ferrari/<git_sha>/report.json
- reports/ferrari/<git_sha>/report.md
- reports/ferrari/<git_sha>/diff.md (when baseline is provided)
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple



PATH_AT_COMMIT_RE = re.compile(r"^.+@[a-f0-9]{40}$")


@dataclass(frozen=True)
class Gates:
    grounded_accuracy_answerable: float = 0.80
    false_citation_rate_max: float = 0.02
    missing_context_actionable_rate: float = 0.95
    p95_rag_total_ms_max: float = 800.0
    leakage_max: int = 0


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True)
            .strip()
        )
    except Exception:
        return "unknown-sha"


def _extract_questions(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        cases = payload.get("cases", [])
        return [c for c in cases if isinstance(c, dict)]
    if isinstance(payload, list):
        return [c for c in payload if isinstance(c, dict)]
    return []


def _extract_missing_context_payload(response_text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(response_text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _is_actionable_missing_context(payload: Dict[str, Any]) -> bool:
    questions = payload.get("targeted_questions")
    suggestion = payload.get("ingestion_suggestion")
    valid_questions = isinstance(questions, list) and 1 <= len([q for q in questions if str(q).strip()]) <= 3
    return bool(valid_questions and isinstance(suggestion, str) and suggestion.strip())


def _citation_strings_from_response(item: Dict[str, Any]) -> List[str]:
    sources = item.get("sources")
    if not isinstance(sources, list):
        return []
    entries: List[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        path = str(source.get("path", "")).strip()
        commit = str(source.get("commit", "")).strip()
        if path and commit:
            entries.append(f"{path}@{commit}")
    return entries


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def _evaluate_cases(cases: List[Dict[str, Any]], outputs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    answerable_total = 0
    answerable_supported = 0
    answerable_with_citations = 0
    false_citation_count = 0
    missing_total = 0
    missing_actionable = 0
    rag_latencies: List[float] = []
    leakage_events: List[Dict[str, Any]] = []
    examples: List[Dict[str, Any]] = []

    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id:
            continue
        out = outputs.get(case_id, {})
        answerable = bool(case.get("answerable", False))
        citations = _citation_strings_from_response(out)
        bad_citations = [c for c in citations if not PATH_AT_COMMIT_RE.match(c)]
        if bad_citations:
            false_citation_count += 1
            examples.append({"id": case_id, "failure": "invalid_citation_format", "citations": bad_citations})

        retrieval_stats = out.get("retrieval_stats", {}) if isinstance(out.get("retrieval_stats"), dict) else {}
        latency = retrieval_stats.get("total_time_ms")
        if isinstance(latency, (int, float)):
            rag_latencies.append(float(latency))

        expected_workspace = str(case.get("workspace_id", "")).strip()
        for source in out.get("sources", []) if isinstance(out.get("sources"), list) else []:
            ws = str((source or {}).get("workspace_id", "")).strip()
            if expected_workspace and ws and ws != expected_workspace:
                leakage_events.append({"id": case_id, "expected": expected_workspace, "got": ws, "source": source})

        if answerable:
            answerable_total += 1
            if out.get("supported_answer", True):
                answerable_supported += 1
            if citations:
                answerable_with_citations += 1
        else:
            missing_total += 1
            payload = _extract_missing_context_payload(str(out.get("response", "")))
            if _is_actionable_missing_context(payload):
                missing_actionable += 1
            else:
                examples.append({"id": case_id, "failure": "missing_context_not_actionable", "response": out.get("response")})

    grounded_accuracy = (answerable_supported / answerable_total) if answerable_total else 0.0
    false_citation_rate = (false_citation_count / len(cases)) if cases else 0.0
    missing_actionable_rate = (missing_actionable / missing_total) if missing_total else 0.0
    citations_coverage = (answerable_with_citations / answerable_total) if answerable_total else 0.0
    leakage = len(leakage_events)
    p95 = _p95(rag_latencies)

    return {
        "metrics": {
            "grounded_accuracy_answerable": round(grounded_accuracy, 4),
            "false_citation_rate": round(false_citation_rate, 4),
            "missing_context_actionable_rate": round(missing_actionable_rate, 4),
            "answerable_citation_coverage": round(citations_coverage, 4),
            "p95_rag_total_ms": round(p95, 2),
            "leakage": leakage,
        },
        "counts": {
            "total": len(cases),
            "answerable_total": answerable_total,
            "answerable_supported": answerable_supported,
            "answerable_with_citations": answerable_with_citations,
            "missing_total": missing_total,
            "missing_actionable": missing_actionable,
            "false_citation_count": false_citation_count,
            "leakage_events": leakage,
        },
        "top_failures": (examples + leakage_events)[:20],
    }


def _run_live(base_url: str, cases: List[Dict[str, Any]], timeout_s: float) -> Dict[str, Dict[str, Any]]:
    outputs: Dict[str, Dict[str, Any]] = {}
    # Needs: python-package:httpx
    import httpx

    with httpx.Client(timeout=timeout_s) as client:
        for case in cases:
            case_id = str(case.get("id", "")).strip()
            if not case_id:
                continue
            workspace_id = str(case.get("workspace_id", "default")).strip() or "default"
            body = {
                "query": case.get("question", ""),
                "workspace_id": workspace_id,
                "include_context": False,
            }
            headers = {"X-Workspace-Id": workspace_id}
            started = time.perf_counter()
            response = client.post(f"{base_url.rstrip('/')}/v1/rag/query", json=body, headers=headers)
            elapsed_ms = (time.perf_counter() - started) * 1000
            response.raise_for_status()
            payload = response.json()
            retrieval_stats = payload.get("retrieval_stats", {}) if isinstance(payload, dict) else {}
            if isinstance(retrieval_stats, dict) and "total_time_ms" not in retrieval_stats:
                retrieval_stats["total_time_ms"] = round(elapsed_ms, 2)
            payload["retrieval_stats"] = retrieval_stats
            payload["supported_answer"] = bool(case.get("answerable", False)) and bool(payload.get("sources"))
            outputs[case_id] = payload
    return outputs


def _load_outputs(path: Path) -> Dict[str, Dict[str, Any]]:
    raw = _load_json(path)
    if isinstance(raw, dict) and "outputs" in raw and isinstance(raw["outputs"], list):
        items = raw["outputs"]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    out: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            out[str(item["id"])] = item
    return out


def _gate_failures(metrics: Dict[str, Any], gates: Gates) -> List[str]:
    failures: List[str] = []
    if metrics["grounded_accuracy_answerable"] < gates.grounded_accuracy_answerable:
        failures.append("grounded_accuracy_answerable")
    if metrics["false_citation_rate"] > gates.false_citation_rate_max:
        failures.append("false_citation_rate")
    if metrics["missing_context_actionable_rate"] < gates.missing_context_actionable_rate:
        failures.append("missing_context_actionable_rate")
    if metrics["p95_rag_total_ms"] > gates.p95_rag_total_ms_max:
        failures.append("p95_rag_total_ms")
    if metrics["leakage"] > gates.leakage_max:
        failures.append("leakage")
    return failures


def _render_markdown(report: Dict[str, Any]) -> str:
    m = report["metrics"]
    lines = [
        "# Ferrari Benchmark Report",
        "",
        f"- Commit: `{report['git_sha']}`",
        f"- Generated at: `{report['generated_at']}`",
        "",
        "## Metrics",
        "",
        f"- grounded_accuracy_answerable: **{m['grounded_accuracy_answerable']:.2%}**",
        f"- false_citation_rate: **{m['false_citation_rate']:.2%}**",
        f"- missing_context_actionable_rate: **{m['missing_context_actionable_rate']:.2%}**",
        f"- p95_rag_total_ms: **{m['p95_rag_total_ms']} ms**",
        f"- leakage: **{m['leakage']}**",
        "",
        "## Top failures",
        "",
    ]
    failures = report.get("top_failures", [])
    if not failures:
        lines.append("- none")
    else:
        for item in failures[:10]:
            lines.append(f"- `{item.get('id', 'unknown')}`: {item.get('failure', 'leakage_or_other')}")
    return "\n".join(lines) + "\n"


def _render_diff(current: Dict[str, Any], baseline: Dict[str, Any], tolerance_accuracy_drop: float) -> Tuple[str, bool]:
    cm = current["metrics"]
    bm = baseline.get("metrics", {})
    lines = ["# Ferrari Benchmark Diff", ""]
    regressions: List[str] = []

    for key in [
        "grounded_accuracy_answerable",
        "false_citation_rate",
        "missing_context_actionable_rate",
        "p95_rag_total_ms",
        "leakage",
    ]:
        cur = float(cm.get(key, 0.0))
        base = float(bm.get(key, 0.0))
        delta = cur - base
        lines.append(f"- {key}: current={cur:.4f} baseline={base:.4f} delta={delta:+.4f}")

    if float(cm.get("leakage", 0)) > 0:
        regressions.append("absolute_gate: leakage > 0")
    if float(cm.get("grounded_accuracy_answerable", 0)) < float(bm.get("grounded_accuracy_answerable", 0)) - tolerance_accuracy_drop:
        regressions.append("relative_regression: grounded_accuracy_answerable")

    if regressions:
        lines.extend(["", "## Regressions", *[f"- {r}" for r in regressions]])
    else:
        lines.extend(["", "## Regressions", "- none"])
    return "\n".join(lines) + "\n", bool(regressions)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ferrari benchmark and produce report JSON/MD")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--golden-set", default="eval/golden_set_eng_v2.json")
    parser.add_argument("--hard-set", default="eval/hard_set_missing_context_v1.json")
    parser.add_argument("--outputs-file", default="", help="Offline mode: precomputed outputs with id-matching cases")
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--report-root", default="reports/ferrari")
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--tolerance-accuracy-drop", type=float, default=0.03)
    args = parser.parse_args()

    golden_cases = _extract_questions(_load_json(Path(args.golden_set)))
    hard_cases = _extract_questions(_load_json(Path(args.hard_set)))
    all_cases = golden_cases + hard_cases
    if not all_cases:
        raise SystemExit("No benchmark cases found.")

    if args.outputs_file:
        outputs = _load_outputs(Path(args.outputs_file))
    else:
        if not args.base_url:
            raise SystemExit("--base-url is required when --outputs-file is not provided")
        outputs = _run_live(args.base_url, all_cases, args.request_timeout)

    evaluation = _evaluate_cases(all_cases, outputs)
    git_sha = _git_sha()
    report_dir = Path(args.report_root) / git_sha
    report_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "git_sha": git_sha,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "datasets": {
            "golden_set": args.golden_set,
            "hard_set": args.hard_set,
            "total_cases": len(all_cases),
        },
        **evaluation,
    }

    gates = Gates()
    failures = _gate_failures(report["metrics"], gates)
    report["gates"] = {"passed": not failures, "failed": failures}

    report_json = report_dir / "report.json"
    report_md = report_dir / "report.md"
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report_md.write_text(_render_markdown(report), encoding="utf-8")

    baseline_failed = False
    if args.baseline_report:
        baseline = _load_json(Path(args.baseline_report))
        diff_md, baseline_failed = _render_diff(report, baseline, args.tolerance_accuracy_drop)
        (report_dir / "diff.md").write_text(diff_md, encoding="utf-8")

    print(json.dumps(report["metrics"], indent=2))
    if failures or baseline_failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

