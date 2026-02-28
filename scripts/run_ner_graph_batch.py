#!/usr/bin/env python3
"""Batch pipeline for NER + graph building on a small corpus.

# Needs: service:neo4j
# Needs: python-package:spacy
# Needs: python-package:sentence-transformers

This script reads a local corpus file, extracts entities and relations using
``GraphService.process_document`` and writes a JSON report.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from graph_service import GraphService

logger = logging.getLogger("ner_graph_batch")


def _load_corpus(path: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    required_keys = {"document_id", "text"}

    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            if not isinstance(doc, dict):
                raise ValueError(f"Line {i} must be a JSON object")
            missing = required_keys - set(doc.keys())
            if missing:
                raise ValueError(f"Line {i} is missing keys: {sorted(missing)}")
            docs.append(doc)

    if not docs:
        raise ValueError("Corpus JSONL file is empty")

    return docs


def run_batch(corpus_path: Path, output_path: Path) -> dict[str, Any]:
    docs = _load_corpus(corpus_path)

    service = GraphService(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="neo4j_password",
    )

    processed: list[dict[str, Any]] = []
    totals = {
        "documents": 0,
        "entities_extracted": 0,
        "entities_added": 0,
        "relations_extracted": 0,
        "relations_added": 0,
    }

    try:
        for doc in docs:
            result = service.process_document(
                text=doc["text"],
                document_id=doc["document_id"],
                metadata=doc.get("metadata", {}),
            )
            processed.append(result)

            totals["documents"] += 1
            totals["entities_extracted"] += result["entities_extracted"]
            totals["entities_added"] += result["entities_added"]
            totals["relations_extracted"] += result["relations_extracted"]
            totals["relations_added"] += result["relations_added"]
    finally:
        service.close()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_path": str(corpus_path),
        "totals": totals,
        "documents": processed,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NER + graph builder batch job")
    parser.add_argument(
        "--corpus",
        default="data/graph_seed_corpus.jsonl",
        type=Path,
        help="Path to corpus JSONL file",
    )
    parser.add_argument(
        "--output",
        default="artifacts/ner_graph_batch_report.json",
        type=Path,
        help="Path to output report JSON",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    report = run_batch(args.corpus, args.output)
    logger.info("Processed %s documents", report["totals"]["documents"])
    logger.info("Entities extracted: %s", report["totals"]["entities_extracted"])
    logger.info("Relations extracted: %s", report["totals"]["relations_extracted"])
    logger.info("Report written to %s", args.output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
