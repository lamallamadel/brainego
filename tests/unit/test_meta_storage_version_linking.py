# Needs: python-package:pytest>=9.0.2

from pathlib import Path


META_STORAGE_SOURCE = Path(__file__).resolve().parents[2] / "learning_engine" / "meta_storage.py"


def test_upload_meta_weights_accepts_training_config_and_adapter_links() -> None:
    content = META_STORAGE_SOURCE.read_text(encoding="utf-8")

    assert "training_config: Optional[Dict[str, Any]] = None" in content
    assert "linked_adapter_versions: Optional[List[str]] = None" in content
    assert 'metadata_doc["training_config"] = training_config or metadata_doc.get("training_config", {})' in content
    assert 'metadata_doc["linked_adapter_versions"] = sorted(' in content
    assert 'metadata_doc["weights_object_version_id"] = getattr(upload_result, "version_id", None)' in content


def test_meta_storage_exposes_linking_helpers() -> None:
    content = META_STORAGE_SOURCE.read_text(encoding="utf-8")

    assert "def link_adapter_to_meta_weights(" in content
    assert "def get_adapter_dependencies(self, adapter_version: str) -> List[str]:" in content
    assert "linked.add(adapter_version)" in content
    assert "if adapter_version in version_data.get(\"linked_adapter_versions\", []):" in content


def test_meta_storage_uses_json_helpers_for_metadata_roundtrip() -> None:
    content = META_STORAGE_SOURCE.read_text(encoding="utf-8")

    assert "def _put_json(self, object_name: str, payload: Dict[str, Any]):" in content
    assert "def _get_json(self, object_name: str) -> Dict[str, Any]:" in content
    assert "data=BytesIO(payload_bytes)" in content
    assert "return self._get_json(metadata_name)" in content
