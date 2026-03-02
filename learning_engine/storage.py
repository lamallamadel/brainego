"""
Adapter Storage on MinIO

Manages LoRA adapter versioning and storage on MinIO S3-compatible storage.
"""

import os
import logging
import json
import shutil
import re
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class AdapterStorage:
    """
    Manages LoRA adapter storage on MinIO.

    Adapters are versioned and stored with metadata.
    Storage layout:
      {model_name}/{project}/{version}/adapter.tar.gz
      {model_name}/{project}/{version}/metadata.json
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str = "lora-adapters",
        secure: bool = False,
        model_name: str = "default-model",
        project_name: str = "default-project",
    ):
        self.endpoint = endpoint
        self.bucket_name = bucket_name
        self.model_name = self._sanitize_path_component(model_name)
        self.project_name = self._sanitize_path_component(project_name)

        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )

        self._ensure_bucket()
        logger.info(f"Adapter storage initialized: {endpoint}/{bucket_name}")

    @staticmethod
    def _sanitize_path_component(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]", "-", value or "")
        return cleaned.strip(".-") or "unknown"

    def _version_prefix(
        self,
        version: str,
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> str:
        selected_model = self._sanitize_path_component(model_name or self.model_name)
        selected_project = self._sanitize_path_component(project_name or self.project_name)
        version_key = self._sanitize_path_component(version)
        return f"{selected_model}/{selected_project}/{version_key}"

    def _registry_name(
        self,
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> str:
        selected_model = self._sanitize_path_component(model_name or self.model_name)
        selected_project = self._sanitize_path_component(project_name or self.project_name)
        return f"{selected_model}/{selected_project}/registry.json"

    def _build_default_registry(self, model_name: str, project_name: str) -> Dict[str, Any]:
        return {
            "model_name": model_name,
            "project": project_name,
            "updated_at": datetime.utcnow().isoformat(),
            "active_version": None,
            "previous_version": None,
            "known_good_version": None,
            "versions": {},
            "rollback_history": [],
        }

    def _load_registry(
        self,
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_model = self._sanitize_path_component(model_name or self.model_name)
        selected_project = self._sanitize_path_component(project_name or self.project_name)
        registry_name = self._registry_name(selected_model, selected_project)
        try:
            response = self.client.get_object(self.bucket_name, registry_name)
            registry = json.loads(response.read().decode("utf-8"))
            response.close()
            response.release_conn()
        except S3Error as e:
            if e.code != "NoSuchKey":
                raise
            registry = self._build_default_registry(selected_model, selected_project)

        registry.setdefault("model_name", selected_model)
        registry.setdefault("project", selected_project)
        registry.setdefault("active_version", None)
        registry.setdefault("previous_version", None)
        registry.setdefault("known_good_version", None)
        registry.setdefault("versions", {})
        registry.setdefault("rollback_history", [])
        registry.setdefault("updated_at", datetime.utcnow().isoformat())
        return registry

    def _save_registry(self, registry: Dict[str, Any]):
        payload = json.dumps(registry, indent=2)
        registry_name = self._registry_name(registry.get("model_name"), registry.get("project"))
        self.client.put_object(
            self.bucket_name,
            registry_name,
            data=payload.encode("utf-8"),
            length=len(payload),
            content_type="application/json",
        )

    @staticmethod
    def _sha256_file(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _ensure_bucket(self):
        """Ensure the bucket exists"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
            else:
                logger.info(f"Bucket exists: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"Failed to ensure bucket: {e}")
            raise

    def upload_adapter(
        self,
        local_path: str,
        version: str,
        metadata: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
        author: Optional[str] = None,
    ) -> str:
        """Upload LoRA adapter to MinIO."""
        logger.info(f"Uploading adapter {version} from {local_path}")

        archive_path = f"/tmp/adapter_{version}.tar.gz"
        shutil.make_archive(
            archive_path.replace('.tar.gz', ''),
            'gztar',
            local_path
        )

        try:
            version_prefix = self._version_prefix(version, model_name, project_name)
            object_name = f"{version_prefix}/adapter.tar.gz"
            self.client.fput_object(self.bucket_name, object_name, archive_path)
            logger.info(f"✓ Adapter uploaded: {object_name}")

            created_at = datetime.utcnow().isoformat()
            adapter_sha256 = self._sha256_file(archive_path)

            if metadata is not None:
                path_parts = version_prefix.split("/")
                metadata_payload = {
                    "model_name": path_parts[0],
                    "project": path_parts[1],
                    "version": path_parts[2],
                    "dataset_id": metadata.get("dataset_id"),
                    "validation_metrics": metadata.get("validation_metrics", {}),
                    "timestamp": metadata.get("timestamp") or created_at,
                    "author": metadata.get("author") or author or "unknown",
                    "adapter_sha256": metadata.get("adapter_sha256") or adapter_sha256,
                    "training_data_version": metadata.get("training_data_version"),
                    "eval_scores": metadata.get("eval_scores", {}),
                }
                metadata_payload.update(metadata)

                metadata_str = json.dumps(metadata_payload, indent=2)
                metadata_name = f"{version_prefix}/metadata.json"
                self.client.put_object(
                    self.bucket_name,
                    metadata_name,
                    data=metadata_str.encode('utf-8'),
                    length=len(metadata_str),
                    content_type='application/json'
                )
                logger.info(f"✓ Metadata uploaded: {metadata_name}")

                registry = self._load_registry(path_parts[0], path_parts[1])
                registry.setdefault("versions", {})
                registry["versions"][path_parts[2]] = {
                    "metadata_object": metadata_name,
                    "adapter_object": object_name,
                    "adapter_sha256": metadata_payload.get("adapter_sha256"),
                    "created_at": metadata_payload.get("timestamp") or created_at,
                    "eval_scores": metadata_payload.get("eval_scores", {}),
                    "training_data_version": metadata_payload.get("training_data_version"),
                    "dataset_id": metadata_payload.get("dataset_id"),
                }
                registry["updated_at"] = created_at
                if registry.get("active_version") is None:
                    registry["active_version"] = path_parts[2]
                if registry.get("known_good_version") is None:
                    registry["known_good_version"] = path_parts[2]
                self._save_registry(registry)

            os.remove(archive_path)
            return object_name

        except S3Error as e:
            logger.error(f"Failed to upload adapter: {e}")
            raise

    async def download_adapter(
        self,
        version: str,
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
        local_dir: str = "/tmp/adapters"
    ) -> str:
        """Download LoRA adapter from MinIO."""
        logger.info(f"Downloading adapter {version}")
        os.makedirs(local_dir, exist_ok=True)

        version_prefix = self._version_prefix(version, model_name, project_name)
        object_name = f"{version_prefix}/adapter.tar.gz"
        local_archive = os.path.join(local_dir, f"adapter_{version}.tar.gz")

        try:
            self.client.fget_object(self.bucket_name, object_name, local_archive)

            extract_dir = os.path.join(local_dir, version)
            os.makedirs(extract_dir, exist_ok=True)
            shutil.unpack_archive(local_archive, extract_dir)
            os.remove(local_archive)

            logger.info(f"✓ Adapter downloaded to {extract_dir}")
            return extract_dir

        except S3Error as e:
            logger.error(f"Failed to download adapter: {e}")
            raise

    async def list_adapters(
        self,
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all available adapters for a model/project."""
        logger.info("Listing adapters...")
        adapters = []

        try:
            selected_model = self._sanitize_path_component(model_name or self.model_name)
            selected_project = self._sanitize_path_component(project_name or self.project_name)
            prefix = f"{selected_model}/{selected_project}/"

            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=True
            )

            versions = set()
            for obj in objects:
                parts = obj.object_name.split('/')
                if len(parts) >= 4:
                    versions.add(parts[2])

            for version in sorted(versions):
                metadata = await self.get_adapter_metadata(
                    version,
                    model_name=selected_model,
                    project_name=selected_project,
                )
                if metadata:
                    adapters.append(metadata)

            logger.info(f"✓ Found {len(adapters)} adapters")
            return adapters

        except S3Error as e:
            logger.error(f"Failed to list adapters: {e}")
            return []

    async def get_adapter_metadata(
        self,
        version: str,
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific adapter."""
        try:
            version_prefix = self._version_prefix(version, model_name, project_name)
            metadata_name = f"{version_prefix}/metadata.json"

            response = self.client.get_object(self.bucket_name, metadata_name)
            metadata = json.loads(response.read().decode('utf-8'))
            metadata.setdefault('version', self._sanitize_path_component(version))

            response.close()
            response.release_conn()
            return metadata

        except S3Error as e:
            if e.code == "NoSuchKey":
                return {
                    "model_name": self._sanitize_path_component(model_name or self.model_name),
                    "project": self._sanitize_path_component(project_name or self.project_name),
                    "version": self._sanitize_path_component(version),
                    "metadata_missing": True,
                }
            logger.error(f"Failed to get adapter metadata: {e}")
            return None

    def update_rollback_pointers(
        self,
        active_version: Optional[str] = None,
        previous_version: Optional[str] = None,
        known_good_version: Optional[str] = None,
        reason: str = "manual",
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update rollback pointers persisted in registry.json."""
        registry = self._load_registry(model_name, project_name)
        event_time = datetime.utcnow().isoformat()

        if active_version is not None:
            sanitized_active = self._sanitize_path_component(active_version)
            if previous_version is None and registry.get("active_version") != sanitized_active:
                previous_version = registry.get("active_version")
            registry["active_version"] = sanitized_active

        if previous_version is not None:
            registry["previous_version"] = self._sanitize_path_component(previous_version)

        if known_good_version is not None:
            registry["known_good_version"] = self._sanitize_path_component(known_good_version)

        registry.setdefault("rollback_history", []).append(
            {
                "active_version": registry.get("active_version"),
                "previous_version": registry.get("previous_version"),
                "known_good_version": registry.get("known_good_version"),
                "reason": reason,
                "timestamp": event_time,
            }
        )
        registry["updated_at"] = event_time
        self._save_registry(registry)
        return registry

    def get_registry(
        self,
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return adapter registry and rollback pointers."""
        return self._load_registry(model_name, project_name)

    def delete_adapter(
        self,
        version: str,
        model_name: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> bool:
        """Delete an adapter version."""
        logger.info(f"Deleting adapter {version}")

        try:
            version_prefix = self._version_prefix(version, model_name, project_name)
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=f"{version_prefix}/",
                recursive=True
            )

            for obj in objects:
                self.client.remove_object(self.bucket_name, obj.object_name)

            logger.info(f"✓ Adapter {version} deleted")
            return True

        except S3Error as e:
            logger.error(f"Failed to delete adapter: {e}")
            return False

    def get_latest_version(self) -> Optional[str]:
        """Get latest adapter version for configured model/project."""
        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=f"{self.model_name}/{self.project_name}/",
                recursive=True
            )

            versions = []
            for obj in objects:
                parts = obj.object_name.split('/')
                if len(parts) >= 4:
                    versions.append(parts[2])

            if versions:
                def parse_version(value: str):
                    numeric = value.replace('v', '').split('.')
                    try:
                        return tuple(map(int, numeric))
                    except ValueError:
                        return (0,)

                sorted_versions = sorted(set(versions), key=parse_version, reverse=True)
                return sorted_versions[0]

            return None

        except S3Error as e:
            logger.error(f"Failed to get latest version: {e}")
            return None

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics for configured model/project."""
        try:
            objects = list(self.client.list_objects(
                self.bucket_name,
                prefix=f"{self.model_name}/{self.project_name}/",
                recursive=True
            ))

            total_size = sum(obj.size for obj in objects)
            num_adapters = len(set(
                obj.object_name.split('/')[2]
                for obj in objects
                if len(obj.object_name.split('/')) >= 4
            ))

            return {
                "bucket": self.bucket_name,
                "model_name": self.model_name,
                "project": self.project_name,
                "num_adapters": num_adapters,
                "total_objects": len(objects),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }

        except S3Error as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {}
