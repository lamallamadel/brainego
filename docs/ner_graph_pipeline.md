# AFR-42 NER + Graph Builder Pipeline

This deliverable adds a batch pipeline that extracts entities/relations from a small RAG corpus and persists them into Neo4j via `GraphService`.

## 1. Batch job

Run:

```bash
python scripts/run_ner_graph_batch.py \
  --corpus data/graph_seed_corpus.jsonl \
  --output artifacts/ner_graph_batch_report.json
```

What it does:
- Loads a small corpus (`data/graph_seed_corpus.jsonl`).
- For each document, calls `GraphService.process_document(...)`.
- Stores a run report with per-document and aggregate totals.

## 2. Verification queries in Neo4j

Use `docs/neo4j_verification_queries.cypher` in Neo4j Browser:

1. Validate node label counts.
2. Validate relationship type counts.
3. Validate that each `Document` links to extracted entities through `MENTIONS`.
4. Verify key semantic links (`WORKS_ON`, `SOLVED_BY`, `LEARNED_FROM`).

## 3. Expected output artifact

The batch script writes:

- `artifacts/ner_graph_batch_report.json`

This includes:
- document count,
- entities extracted/added,
- relations extracted/added,
- per-document processing status.
