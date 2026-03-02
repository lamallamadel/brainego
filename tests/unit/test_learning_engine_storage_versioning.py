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
    monkeypatch.setattr(storage_module.AdapterStorage, "_sha256_file", staticmethod(lambda *_args, **_kwargs: "deadbeef"))
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


def test_upload_updates_registry_with_version_metadata(storage):
    storage.upload_adapter(
        local_path="/tmp/adapter",
        version="v2.0",
        metadata={
            "dataset_id": "dataset-77",
            "training_data_version": "train-2026-02",
            "eval_scores": {"bleu": 0.71},
        },
    )

    registry_raw = storage.client.objects[(
        "lora-adapters",
        "llama-3.3-8b-instruct/afroware-rag/registry.json",
    )]
    registry = json.loads(registry_raw.decode("utf-8"))

    assert registry["active_version"] == "v2.0"
    assert registry["known_good_version"] == "v2.0"
    assert registry["versions"]["v2.0"]["training_data_version"] == "train-2026-02"
    assert registry["versions"]["v2.0"]["eval_scores"]["bleu"] == pytest.approx(0.71)
    assert registry["versions"]["v2.0"]["adapter_sha256"]


def test_rollback_pointers_are_persisted_in_registry(storage):
    storage.upload_adapter(local_path="/tmp/adapter", version="v1.0", metadata={"dataset_id": "d1"})
    storage.upload_adapter(local_path="/tmp/adapter", version="v1.1", metadata={"dataset_id": "d2"})

    registry = storage.update_rollback_pointers(
        active_version="v1.1",
        previous_version="v1.0",
        known_good_version="v1.0",
        reason="rollback_test",
    )

    assert registry["active_version"] == "v1.1"
    assert registry["previous_version"] == "v1.0"
    assert registry["known_good_version"] == "v1.0"
    assert registry["rollback_history"][-1]["reason"] == "rollback_test"

    persisted_registry = storage.get_registry()
    assert persisted_registry["active_version"] == "v1.1"
    assert persisted_registry["rollback_history"][-1]["reason"] == "rollback_test"
