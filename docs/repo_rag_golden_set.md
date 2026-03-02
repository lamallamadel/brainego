# Repo-RAG Golden Set (AFR-111)

## Goal

Provide a compact evaluation set for the pilot repository to check:

1. **retrieval relevance** (does the system retrieve the right source files?)
2. **citation correctness** (does the answer cite the right files?)

The set is intentionally small (20 questions) to keep pilot validation fast.

## Location

- Golden set fixture: `tests/contract/fixtures/repo_rag_golden_set.ndjson`
- Contract test: `tests/unit/test_repo_rag_golden_set_contract.py`

## Source corpus scope

The golden set is aligned with the default files indexed by `scripts/pilot/demo_repo_index.py`:

- `README.md`
- `QUICKSTART.md`
- `MCP_QUICKSTART.md`
- `SECURITY_QUICKSTART.md`
- `DISASTER_RECOVERY_RUNBOOK.md`
- `MCP_AFR32_MANUAL_TEST.md`

## Case schema

Each case contains:

- `id`: stable case identifier
- `question`: user question to ask
- `expected_sources`: source file(s) expected in retrieval
- `expected_answer_keywords`: key facts expected in the answer
- `citation_required`: always `true` for this set
- `citation_format`: expected citation pattern (`[source:<path>]`)
- `citation_anchors`: exact source snippets used as citation ground truth

## Suggested execution flow

1. Index the pilot corpus:

```bash
python3 scripts/pilot/demo_repo_index.py \
  --api-url http://localhost:8000 \
  --workspace-id default \
  --api-key sk-test-key-123
```

2. For each golden case, call `/v1/rag/query` with `include_context=true` and force citations:

```json
{
  "query": "<case.question>\n\nAnswer with citations in the format [source:<path>].",
  "k": 5,
  "include_context": true
}
```

3. Evaluate:
   - **Retrieval relevance**: pass if at least one retrieved `context[].metadata.source` is in `expected_sources`.
   - **Citation correctness**: pass if answer includes citation(s) in `[source:<path>]` and cited path(s) match expected sources.
   - **Fact signal (optional)**: check `expected_answer_keywords` presence.

## Pilot acceptance suggestion

For a lightweight pilot gate:

- Retrieval relevance pass rate >= 0.85
- Citation correctness pass rate >= 0.85
- No case without citation when `citation_required=true`

Teams can tighten these thresholds after baseline stabilization.

## Maintenance

When pilot indexed files change:

1. Update `DEFAULT_FILES` in `scripts/pilot/demo_repo_index.py` if needed.
2. Update `repo_rag_golden_set.ndjson` cases and `indexed_source_set`.
3. Run:

```bash
pytest tests/unit/test_repo_rag_golden_set_contract.py -q
```
