# Needs: python-package:minio

import json
import asyncio
import pytest

import importlib.util
from pathlib import Path


import sys
import types


class _DummyS3Error(Exception):
    def __init__(self, code="Error"):
        super().__init__(code)
        self.code = code


minio_module = types.ModuleType("minio")
minio_error_module = types.ModuleType("minio.error")
minio_module.Minio = object
minio_error_module.S3Error = _DummyS3Error
sys.modules.setdefault("minio", minio_module)
sys.modules.setdefault("minio.error", minio_error_module)


def _load_storage_module():
    spec = importlib.util.spec_from_file_location(
        "learning_engine_storage",
        Path(__file__).resolve().parents[2] / "learning_engine" / "storage.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


storage_module = _load_storage_module()


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def close(self):
        return None

    def release_conn(self):
        return None


class FakeObject:
    def __init__(self, object_name: str, size: int = 1):
        self.object_name = object_name
        self.size = size


class FakeMinio:
    def __init__(self, *args, **kwargs):
        self._buckets = set()
        self.objects = {}

    def bucket_exists(self, bucket):
        return bucket in self._buckets

    def make_bucket(self, bucket):
        self._buckets.add(bucket)

    def fput_object(self, bucket, object_name, file_path):
        self.objects[(bucket, object_name)] = b"archive"

    def put_object(self, bucket, object_name, data, length, content_type=None):
        self.objects[(bucket, object_name)] = data.read() if hasattr(data, "read") else data

    def get_object(self, bucket, object_name):
        payload = self.objects.get((bucket, object_name))
        if payload is None:
            raise storage_module.S3Error("NoSuchKey")
        return FakeResponse(payload)

    def list_objects(self, bucket, prefix="", recursive=False):
        for (bucket_name, object_name), payload in self.objects.items():
            if bucket_name == bucket and object_name.startswith(prefix):
                yield FakeObject(object_name=object_name, size=len(payload))

    def remove_object(self, bucket, object_name):
        self.objects.pop((bucket, object_name), None)


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setattr(storage_module, "Minio", FakeMinio)
    monkeypatch.setattr(storage_module.shutil, "make_archive", lambda *args, **kwargs: "/tmp/fake.tar.gz")
    monkeypatch.setattr(storage_module.os, "remove", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage_module.AdapterStorage, "_compute_sha256", staticmethod(lambda *args, **kwargs: "abc123"))
    return storage_module.AdapterStorage(
        endpoint="minio:9000",
        access_key="minio",
        secret_key="minio",
        bucket_name="lora-adapters",
        model_name="llama-3.3-8b-instruct",
        project_name="afroware-rag",
    )


def test_upload_adapter_uses_versioned_layout_and_metadata(storage):
    object_name = storage.upload_adapter(
        local_path="/tmp/adapter",
        version="v1.2",
        metadata={
            "dataset_id": "dataset-42",
            "validation_metrics": {"loss": 0.11, "accuracy": 0.93},
            "author": "alice",
        },
    )

    assert object_name == "llama-3.3-8b-instruct/afroware-rag/v1.2/adapter.tar.gz"

    metadata_raw = storage.client.objects[(
        "lora-adapters",
        "llama-3.3-8b-instruct/afroware-rag/v1.2/metadata.json",
    )]
    metadata = json.loads(metadata_raw.decode("utf-8"))
    assert metadata["model_name"] == "llama-3.3-8b-instruct"
    assert metadata["project"] == "afroware-rag"
    assert metadata["version"] == "v1.2"
    assert metadata["dataset_id"] == "dataset-42"
    assert metadata["validation_metrics"]["accuracy"] == pytest.approx(0.93)
    assert metadata["author"] == "alice"
    assert "timestamp" in metadata


def test_list_and_get_adapter_metadata_for_model_project(storage):
    storage.upload_adapter(local_path="/tmp/adapter", version="v1.0", metadata={"author": "bob"})
    storage.upload_adapter(local_path="/tmp/adapter", version="v1.1", metadata={"author": "carol"})

    adapters = asyncio.run(storage.list_adapters(model_name="llama-3.3-8b-instruct", project_name="afroware-rag"))
    versions = [adapter["version"] for adapter in adapters]

    assert versions == ["v1.0", "v1.1"]
    latest = storage.get_latest_version()
    assert latest == "v1.1"


def test_upload_adapter_includes_hash_eval_and_training_data_version(storage):
    storage.upload_adapter(
        local_path="/tmp/adapter",
        version="v2.0",
        metadata={
            "eval_scores": {"safety": 0.98, "latency": 0.91},
            "training_data_version": "golden-set-2026-03",
        },
    )

    metadata_raw = storage.client.objects[(
        "lora-adapters",
        "llama-3.3-8b-instruct/afroware-rag/v2.0/metadata.json",
    )]
    metadata = json.loads(metadata_raw.decode("utf-8"))

    assert metadata["adapter_sha256"] == "abc123"
    assert metadata["eval_scores"]["safety"] == pytest.approx(0.98)
    assert metadata["training_data_version"] == "golden-set-2026-03"


def test_set_and_get_rollback_pointer(storage):
    payload = storage.set_rollback_pointer(
        pointer_name="stable",
        version="v1.1",
        reason="regression-on-v1.2",
    )

    assert payload["pointer"] == "stable"
    assert payload["version"] == "v1.1"
    assert payload["reason"] == "regression-on-v1.2"

    fetched = storage.get_rollback_pointer("stable")
    assert fetched is not None
    assert fetched["version"] == "v1.1"


def test_get_rollback_pointer_returns_none_when_missing(storage):
    assert storage.get_rollback_pointer("missing") is None
