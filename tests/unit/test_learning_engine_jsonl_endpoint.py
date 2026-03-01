# Needs: python-package:fastapi>=0.133.1

import pytest

fastapi = pytest.importorskip("fastapi")
TestClient = pytest.importorskip("fastapi.testclient").TestClient

service = pytest.importorskip("learning_engine_service")


class DummyTrainer:
    def train_from_jsonl(self, dataset_path, learning_rate=None, epochs=None, batch_size=None, job_id=None):
        return {
            "status": "success",
            "dataset_path": dataset_path,
            "learning_rate": learning_rate,
            "epochs": epochs,
            "batch_size": batch_size,
            "job_id": job_id,
        }


def test_train_jsonl_endpoint_accepts_hyperparameter_overrides(monkeypatch):
    monkeypatch.setattr(service, "trainer", DummyTrainer())

    client = TestClient(service.app)
    response = client.post(
        "/train/jsonl",
        json={
            "dataset_path": "data/graph_seed_corpus.jsonl",
            "learning_rate": 0.0001,
            "epochs": 2,
            "batch_size": 8,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "started"
    assert payload["job_id"].startswith("train_jsonl_")
    assert "JSONL training job started" in payload["message"]


def test_train_jsonl_requires_trainer_initialized(monkeypatch):
    monkeypatch.setattr(service, "trainer", None)

    client = TestClient(service.app)
    response = client.post(
        "/train/jsonl",
        json={"dataset_path": "data/graph_seed_corpus.jsonl"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Trainer not initialized"
