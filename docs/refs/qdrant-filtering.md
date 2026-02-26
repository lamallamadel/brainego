# Qdrant Filtering Reference (Offline Note)

This file is a vendored project note to avoid network lookups during CI.

Official documentation:
- https://qdrant.tech/documentation/concepts/filtering/

## Minimal Python Example (`qdrant_client.models`)

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

query_filter = Filter(
    must=[
        FieldCondition(
            key="metadata.source",
            match=MatchValue(value="user_upload")
        )
    ]
)
```

Common clauses:
- `must=[...]`
- `should=[...]`
- `must_not=[...]`

For numeric/date constraints, use `Range(...)` in `FieldCondition`.
