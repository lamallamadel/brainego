"""Unit tests for fine-tuning dataset filtering and export format."""

import json
import sys
import types
from pathlib import Path

# Stub optional DB dependency so this unit test stays offline.
if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")
    psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
    psycopg2_pool_stub = types.ModuleType("psycopg2.pool")
    psycopg2_extras_stub.RealDictCursor = object
    psycopg2_extras_stub.execute_batch = lambda *args, **kwargs: None
    psycopg2_pool_stub.ThreadedConnectionPool = object
    psycopg2_stub.extras = psycopg2_extras_stub
    psycopg2_stub.pool = psycopg2_pool_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub
    sys.modules["psycopg2.pool"] = psycopg2_pool_stub

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import feedback_service


def _build_service():
    """Create service instance without opening database connections."""
    return feedback_service.FeedbackService.__new__(feedback_service.FeedbackService)


def test_filter_training_examples_deduplicates_and_drops_short_rows():
    service = _build_service()

    dataset = [
        {"query": "", "response": "Valid response long enough", "rating": 1, "weight": 2.0},
        {"query": "short", "response": "Too short response", "rating": -1, "weight": 0.5},
        {
            "query": "How do I build a weekly dataset?",
            "response": "Collect recent interactions and export JSONL records.",
            "rating": 1,
            "weight": 2.0,
        },
        {
            "query": "How do I build a weekly dataset?",
            "response": "Collect recent interactions and export JSONL records.",
            "rating": 1,
            "weight": 2.0,
        },
    ]

    filtered = service._filter_training_examples(dataset)

    assert len(filtered) == 1
    assert filtered[0]["query"] == "How do I build a weekly dataset?"


def test_export_finetuning_dataset_writes_instruction_input_output(tmp_path):
    service = _build_service()

    def _fake_dataset(_start, _end):
        return [
            {
                "query": "Explain transformers in simple terms",
                "response": "Transformers process token sequences with self-attention.",
                "model": "llama-3.3-8b-instruct",
                "rating": 1,
                "weight": 2.0,
                "timestamp": "2025-01-01T00:00:00+00:00",
                "intent": "general",
                "project": "brainego",
                "reason": "Response was too vague",
                "category": "missing_citation",
                "expected_answer": "Transformers use self-attention layers to model token dependencies.",
            }
        ]

    service.get_weekly_finetuning_dataset = _fake_dataset

    output_path = tmp_path / "finetuning.jsonl"
    result = service.export_finetuning_dataset(str(output_path))

    rows = [json.loads(line) for line in Path(output_path).read_text().splitlines()]

    assert result["total_samples"] == 1
    assert result["filtered_out_samples"] == 0
    assert set(rows[0].keys()) == {"instruction", "input", "output", "weight", "metadata"}
    assert rows[0]["input"] == "Explain transformers in simple terms"
    assert rows[0]["output"] == "Transformers use self-attention layers to model token dependencies."
    assert rows[0]["metadata"]["project"] == "brainego"
    assert rows[0]["metadata"]["category"] == "missing_citation"
    assert rows[0]["metadata"]["expected_answer"] == (
        "Transformers use self-attention layers to model token dependencies."
    )


def test_export_finetuning_dataset_uploads_to_minio_when_enabled(tmp_path, monkeypatch):
    service = _build_service()

    def _fake_dataset(_start, _end):
        return [
            {
                "query": "How to tune a model weekly?",
                "response": "Export quality-filtered examples and train with weights.",
                "model": "llama-3.3-8b-instruct",
                "rating": 1,
                "weight": 2.0,
                "timestamp": "2025-01-01T00:00:00+00:00",
                "intent": "general",
                "project": "brainego",
            }
        ]

    captured = {}

    def _fake_upload(
        self,
        file_path,
        bucket_name,
        object_key,
        endpoint,
        access_key,
        secret_key,
        secure,
        metadata,
    ):
        captured["file_path"] = file_path
        captured["bucket_name"] = bucket_name
        captured["object_key"] = object_key
        captured["endpoint"] = endpoint
        captured["access_key"] = access_key
        captured["secret_key"] = secret_key
        captured["secure"] = secure
        captured["metadata"] = metadata
        return {
            "minio_bucket": bucket_name,
            "minio_object_key": object_key,
            "minio_uri": f"s3://{bucket_name}/{object_key}",
        }

    service.get_weekly_finetuning_dataset = _fake_dataset
    monkeypatch.setattr(
        feedback_service.FeedbackService,
        "_upload_dataset_to_minio",
        _fake_upload,
    )

    output_path = tmp_path / "finetuning_minio.jsonl"
    result = service.export_finetuning_dataset(
        str(output_path),
        upload_to_minio=True,
        minio_bucket="finetuning-datasets",
        minio_prefix="weekly",
        minio_endpoint="minio:9000",
        minio_access_key="test-access",
        minio_secret_key="test-secret",
        minio_secure=False,
    )

    assert result["total_samples"] == 1
    assert result["minio_bucket"] == "finetuning-datasets"
    assert result["minio_uri"].startswith("s3://finetuning-datasets/weekly/")
    assert captured["bucket_name"] == "finetuning-datasets"
    assert captured["endpoint"] == "minio:9000"
    assert captured["secure"] is False
    assert captured["metadata"]["deduplicate"] is True
