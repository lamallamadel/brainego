#!/usr/bin/env python3
"""Offline/CI evaluation runner for answers, tools, and citations.

Usage:
  python scripts/eval_runner.py \
    --suite tests/contract/fixtures/eval_runner_suite.ndjson \
    --outputs /tmp/eval_outputs.ndjson \
    --output artifacts/eval_report.json

The script exits with code 1 when configured CI gate thresholds are not met.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


class RunnerError(RuntimeError):
    """Raised when suite/output payloads are invalid."""


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    prompt: str = ""
    expected_answer: str = ""
    answer_keywords: List[str] = field(default_factory=list)
    expected_tools: List[str] = field(default_factory=list)
    expected_citations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelOutput:
    answer: str = ""
    tools: List[str] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScoreThresholds:
    min_answer_score: float
    min_tool_score: float
    min_citation_score: float
    min_overall_score: float
    min_pass_rate: float
    min_mean_overall_score: float


@dataclass(frozen=True)
class ScoreWeights:
    answer: float
    tools: float
    citations: float

    def normalized(self) -> "ScoreWeights":
        total = self.answer + self.tools + self.citations
        if total <= 0:
            raise RunnerError("The sum of answer/tool/citation weights must be > 0")
        return ScoreWeights(
            answer=self.answer / total,
            tools=self.tools / total,
            citations=self.citations / total,
        )


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    passed: bool
    answer_score: float
    tool_score: float
    citation_score: float
    overall_score: float
    details: Dict[str, Any]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_label(value: str) -> str:
    return _normalize_text(value)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", _normalize_text(text))


def _load_json_or_ndjson(path: Path) -> Any:
    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        raise RunnerError(f"File is empty: {path}")
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        lines = [line for line in raw_text.splitlines() if line.strip()]
        try:
            return [json.loads(line) for line in lines]
        except json.JSONDecodeError as exc:
            raise RunnerError(f"Could not parse JSON/NDJSON from {path}") from exc


def _coerce_str(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if any(sep in stripped for sep in [",", ";", "\n"]):
            return [segment.strip() for segment in re.split(r"[,\n;]+", stripped) if segment.strip()]
        return [stripped]
    return [value]


def _extract_tool_label(item: Any) -> str:
    if isinstance(item, Mapping):
        if "function" in item and isinstance(item["function"], Mapping):
            candidate = item["function"].get("name")
            if candidate:
                return str(candidate)
        for key in ("name", "tool", "tool_name"):
            candidate = item.get(key)
            if candidate:
                return str(candidate)
        return ""
    return str(item)


def _extract_citation_label(item: Any) -> str:
    if isinstance(item, Mapping):
        for key in ("id", "source", "source_id", "url", "uri", "title"):
            candidate = item.get(key)
            if candidate:
                return str(candidate)
        return ""
    return str(item)


def _normalize_collection(items: Sequence[str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for raw_item in items:
        stripped = str(raw_item).strip()
        if not stripped:
            continue
        key = _normalize_label(stripped)
        if key and key not in normalized:
            normalized[key] = stripped
    return normalized


def _coerce_output_value(raw: Any, *, kind: str) -> List[str]:
    extractor = _extract_tool_label if kind == "tool" else _extract_citation_label
    normalized_items: List[str] = []
    for item in _coerce_list(raw):
        candidate = extractor(item).strip()
        if candidate:
            normalized_items.append(candidate)
    return normalized_items


def load_suite(path: Path) -> List[EvalCase]:
    raw = _load_json_or_ndjson(path)
    items: Iterable[Dict[str, Any]]
    if isinstance(raw, dict) and "cases" in raw:
        items = raw["cases"]
    elif isinstance(raw, list):
        items = raw
    else:
        raise RunnerError("Suite must be a list or an object containing a 'cases' key")

    cases: List[EvalCase] = []
    for item in items:
        if not isinstance(item, dict):
            raise RunnerError("Each suite case must be an object")

        case_id = _coerce_str(item.get("id") or item.get("case_id"), default="").strip()
        if not case_id:
            raise RunnerError("Each suite case must provide 'id' (or 'case_id')")

        answer_keywords = _coerce_list(
            item.get("answer_keywords")
            or item.get("must_include_keywords")
            or item.get("must_include")
            or []
        )
        expected_tools = _coerce_output_value(
            item.get("expected_tools") or item.get("required_tools") or [],
            kind="tool",
        )
        expected_citations = _coerce_output_value(
            item.get("expected_citations") or item.get("required_citations") or [],
            kind="citation",
        )

        cases.append(
            EvalCase(
                case_id=case_id,
                prompt=_coerce_str(item.get("prompt"), default=""),
                expected_answer=_coerce_str(
                    item.get("expected_answer")
                    or item.get("reference_answer")
                    or item.get("ground_truth_answer"),
                    default="",
                ),
                answer_keywords=[str(value) for value in answer_keywords if str(value).strip()],
                expected_tools=expected_tools,
                expected_citations=expected_citations,
            )
        )
    return cases


def _extract_answer(raw_item: Dict[str, Any]) -> str:
    for key in ("answer", "response", "output", "content"):
        if key in raw_item and raw_item[key] is not None:
            return str(raw_item[key])

    message = raw_item.get("message")
    if isinstance(message, dict) and message.get("content") is not None:
        return str(message["content"])

    choices = raw_item.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            choice_message = first.get("message")
            if isinstance(choice_message, dict) and choice_message.get("content") is not None:
                return str(choice_message["content"])
            if first.get("text") is not None:
                return str(first["text"])
    return ""


def _iter_output_items(payload: Any) -> Iterable[Tuple[str, Any]]:
    if isinstance(payload, dict):
        if "outputs" in payload:
            yield from _iter_output_items(payload["outputs"])
            return
        if "results" in payload and isinstance(payload["results"], list):
            yield from _iter_output_items(payload["results"])
            return

        if all(isinstance(value, dict) for value in payload.values()):
            for key, value in payload.items():
                yield str(key), value
            return

        output_like_keys = {
            "answer",
            "response",
            "output",
            "content",
            "message",
            "choices",
            "tools",
            "tool_calls",
            "tools_used",
            "tools_called",
            "citations",
            "sources",
            "references",
            "source_ids",
        }
        if "id" not in payload and "case_id" not in payload and not (set(payload) & output_like_keys):
            for key, value in payload.items():
                yield str(key), value
            return

        case_id = payload.get("id") or payload.get("case_id")
        if case_id:
            yield str(case_id), payload
            return

        raise RunnerError("Unsupported outputs payload shape")

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                raise RunnerError("Each output item must be an object")
            case_id = item.get("id") or item.get("case_id")
            if not case_id:
                raise RunnerError("Each output item must provide 'id' (or 'case_id')")
            yield str(case_id), item
        return

    raise RunnerError("Outputs payload must be an object or list")


def load_outputs(path: Path) -> Dict[str, ModelOutput]:
    raw = _load_json_or_ndjson(path)
    outputs: Dict[str, ModelOutput] = {}
    for case_id, item in _iter_output_items(raw):
        if isinstance(item, str):
            answer = item
            tools: List[str] = []
            citations: List[str] = []
        elif isinstance(item, dict):
            answer = _extract_answer(item)
            tools = _coerce_output_value(
                item.get("tools")
                or item.get("tool_calls")
                or item.get("tools_used")
                or item.get("tools_called"),
                kind="tool",
            )
            citations = _coerce_output_value(
                item.get("citations")
                or item.get("sources")
                or item.get("references")
                or item.get("source_ids"),
                kind="citation",
            )
        else:
            raise RunnerError("Each output value must be either an object or a string")

        outputs[case_id] = ModelOutput(answer=answer, tools=tools, citations=citations)
    return outputs


def _set_f1(expected: Sequence[str], observed: Sequence[str]) -> Tuple[float, float, float, Dict[str, Any]]:
    expected_map = _normalize_collection(expected)
    observed_map = _normalize_collection(observed)

    expected_set = set(expected_map)
    observed_set = set(observed_map)

    matched = expected_set & observed_set
    missing = expected_set - observed_set
    unexpected = observed_set - expected_set

    if not expected_set and not observed_set:
        precision = 1.0
        recall = 1.0
        score = 1.0
    elif not expected_set and observed_set:
        precision = 0.0
        recall = 1.0
        score = 0.0
    else:
        precision = len(matched) / len(observed_set) if observed_set else 0.0
        recall = len(matched) / len(expected_set) if expected_set else 0.0
        score = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    details = {
        "expected": sorted(expected_map.values(), key=lambda value: value.lower()),
        "observed": sorted(observed_map.values(), key=lambda value: value.lower()),
        "matched": sorted((expected_map[key] for key in matched), key=lambda value: value.lower()),
        "missing": sorted((expected_map[key] for key in missing), key=lambda value: value.lower()),
        "unexpected": sorted((observed_map[key] for key in unexpected), key=lambda value: value.lower()),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(score, 4),
    }
    return score, precision, recall, details


def score_answer(expected_answer: str, observed_answer: str, answer_keywords: Sequence[str]) -> Tuple[float, Dict[str, Any]]:
    expected_normalized = _normalize_text(expected_answer) if expected_answer else ""
    observed_normalized = _normalize_text(observed_answer) if observed_answer else ""

    has_reference = bool(expected_normalized)
    has_keywords = bool(answer_keywords)

    if has_reference:
        sequence_similarity = SequenceMatcher(None, expected_normalized, observed_normalized).ratio()
        token_score, _, _, token_details = _set_f1(_tokenize(expected_answer), _tokenize(observed_answer))
        token_f1 = token_details["f1"]
    else:
        sequence_similarity = 1.0
        token_f1 = 1.0

    normalized_keywords = [value for value in (_normalize_text(keyword) for keyword in answer_keywords) if value]
    matched_keywords = [keyword for keyword, norm in zip(answer_keywords, normalized_keywords) if norm in observed_normalized]
    keyword_recall = len(matched_keywords) / len(normalized_keywords) if normalized_keywords else 1.0

    if has_reference and has_keywords:
        score = (0.5 * sequence_similarity) + (0.3 * token_f1) + (0.2 * keyword_recall)
    elif has_reference:
        score = (0.6 * sequence_similarity) + (0.4 * token_f1)
    elif has_keywords:
        score = keyword_recall
    else:
        score = 1.0

    details = {
        "sequence_similarity": round(sequence_similarity, 4),
        "token_f1": round(token_f1, 4),
        "keyword_recall": round(keyword_recall, 4),
        "matched_keywords": matched_keywords,
        "total_keywords": len(normalized_keywords),
        "reference_answer_provided": has_reference,
    }
    return round(score, 4), details


def evaluate_case(
    case: EvalCase,
    output: ModelOutput,
    weights: ScoreWeights,
    thresholds: ScoreThresholds,
) -> CaseEvaluation:
    answer_score, answer_details = score_answer(case.expected_answer, output.answer, case.answer_keywords)
    tool_score, _, _, tool_details = _set_f1(case.expected_tools, output.tools)
    citation_score, _, _, citation_details = _set_f1(case.expected_citations, output.citations)

    normalized_weights = weights.normalized()
    overall_score = (
        (normalized_weights.answer * answer_score)
        + (normalized_weights.tools * tool_score)
        + (normalized_weights.citations * citation_score)
    )
    overall_score = round(overall_score, 4)

    passed = (
        answer_score >= thresholds.min_answer_score
        and tool_score >= thresholds.min_tool_score
        and citation_score >= thresholds.min_citation_score
        and overall_score >= thresholds.min_overall_score
    )

    return CaseEvaluation(
        case_id=case.case_id,
        passed=passed,
        answer_score=answer_score,
        tool_score=round(tool_score, 4),
        citation_score=round(citation_score, 4),
        overall_score=overall_score,
        details={
            "answer": answer_details,
            "tools": tool_details,
            "citations": citation_details,
            "expected": {
                "prompt": case.prompt,
                "answer": case.expected_answer,
                "answer_keywords": case.answer_keywords,
                "tools": case.expected_tools,
                "citations": case.expected_citations,
            },
            "observed": {
                "answer": output.answer,
                "tools": output.tools,
                "citations": output.citations,
            },
        },
    )


def build_report(
    cases: Sequence[EvalCase],
    outputs: Mapping[str, ModelOutput],
    *,
    thresholds: ScoreThresholds,
    weights: ScoreWeights,
    suite_path: Path,
    outputs_path: Path,
) -> Dict[str, Any]:
    evaluations: List[CaseEvaluation] = []
    for case in cases:
        output = outputs.get(case.case_id, ModelOutput())
        evaluations.append(evaluate_case(case, output, weights=weights, thresholds=thresholds))

    total_cases = len(evaluations)
    passed_cases = sum(1 for item in evaluations if item.passed)
    failed_cases = total_cases - passed_cases
    pass_rate = (passed_cases / total_cases) if total_cases else 0.0

    mean_answer = sum(item.answer_score for item in evaluations) / total_cases if total_cases else 0.0
    mean_tools = sum(item.tool_score for item in evaluations) / total_cases if total_cases else 0.0
    mean_citations = sum(item.citation_score for item in evaluations) / total_cases if total_cases else 0.0
    mean_overall = sum(item.overall_score for item in evaluations) / total_cases if total_cases else 0.0

    suite_case_ids = {case.case_id for case in cases}
    orphan_outputs = sorted(case_id for case_id in outputs if case_id not in suite_case_ids)

    gate_passed = (
        pass_rate >= thresholds.min_pass_rate
        and mean_overall >= thresholds.min_mean_overall_score
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite_path": str(suite_path),
        "outputs_path": str(outputs_path),
        "weights": asdict(weights.normalized()),
        "thresholds": asdict(thresholds),
        "summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "pass_rate": round(pass_rate, 4),
            "mean_answer_score": round(mean_answer, 4),
            "mean_tool_score": round(mean_tools, 4),
            "mean_citation_score": round(mean_citations, 4),
            "mean_overall_score": round(mean_overall, 4),
            "orphan_outputs": orphan_outputs,
        },
        "gate": {
            "passed": gate_passed,
            "reasons": {
                "pass_rate_ok": pass_rate >= thresholds.min_pass_rate,
                "mean_overall_ok": mean_overall >= thresholds.min_mean_overall_score,
            },
        },
        "results": [asdict(item) for item in evaluations],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline/CI eval runner for answers, tools, and citations")
    parser.add_argument("--suite", required=True, type=Path, help="Path to eval suite JSON/NDJSON")
    parser.add_argument("--outputs", required=True, type=Path, help="Path to model outputs JSON/NDJSON")
    parser.add_argument("--output", type=Path, default=Path("artifacts/eval_report.json"), help="Path for JSON report")
    parser.add_argument("--answer-weight", type=float, default=0.6)
    parser.add_argument("--tool-weight", type=float, default=0.2)
    parser.add_argument("--citation-weight", type=float, default=0.2)
    parser.add_argument("--min-answer-score", type=float, default=0.5)
    parser.add_argument("--min-tool-score", type=float, default=0.5)
    parser.add_argument("--min-citation-score", type=float, default=0.5)
    parser.add_argument("--min-overall-score", type=float, default=0.7)
    parser.add_argument("--min-pass-rate", type=float, default=0.8)
    parser.add_argument("--min-mean-overall-score", type=float, default=0.7)
    args = parser.parse_args()

    thresholds = ScoreThresholds(
        min_answer_score=args.min_answer_score,
        min_tool_score=args.min_tool_score,
        min_citation_score=args.min_citation_score,
        min_overall_score=args.min_overall_score,
        min_pass_rate=args.min_pass_rate,
        min_mean_overall_score=args.min_mean_overall_score,
    )
    weights = ScoreWeights(
        answer=args.answer_weight,
        tools=args.tool_weight,
        citations=args.citation_weight,
    )

    cases = load_suite(args.suite)
    outputs = load_outputs(args.outputs)

    report = build_report(
        cases,
        outputs,
        thresholds=thresholds,
        weights=weights,
        suite_path=args.suite,
        outputs_path=args.outputs,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "gate": report["gate"]}, indent=2))

    return 0 if report["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
