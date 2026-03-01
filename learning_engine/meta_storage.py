"""
Meta-Weights Storage on MinIO

Manages MAML meta-weights storage with versioning, metadata tracking,
and efficient retrieval for fast adaptation.
"""

import os
import logging
import json
from io import BytesIO
import torch
import shutil
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class MetaWeightsStorage:
    """
    Manages MAML meta-weights storage on MinIO with versioning.
    
    Features:
    - Versioned meta-weights storage
    - Metadata tracking (performance, tasks, timestamps)
    - Efficient download/upload
    - Version comparison and rollback
    """
    
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str = "meta-weights",
        secure: bool = False
    ):
        """
        Initialize meta-weights storage.
        
        Args:
            endpoint: MinIO endpoint (host:port)
            access_key: MinIO access key
            secret_key: MinIO secret key
            bucket_name: Bucket name for meta-weights
            secure: Use HTTPS
        """
        self.endpoint = endpoint
        self.bucket_name = bucket_name
        
        # Initialize MinIO client
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        
        # Ensure bucket exists
        self._ensure_bucket()
        
        logger.info(f"Meta-weights storage initialized: {endpoint}/{bucket_name}")
    
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
    
    def upload_meta_weights(
        self,
        weights: Dict[str, torch.Tensor],
        version: str,
        metadata: Optional[Dict[str, Any]] = None,
        training_config: Optional[Dict[str, Any]] = None,
        linked_adapter_versions: Optional[List[str]] = None
    ) -> str:
        """
        Upload meta-weights to MinIO.
        
        Args:
            weights: Dictionary of meta-weights
            version: Version identifier (e.g., "v1.0", "2024-01-15")
            metadata: Optional metadata (performance metrics, tasks, etc.)
            training_config: Meta-training configuration used to produce this version
            linked_adapter_versions: LoRA adapter versions depending on these meta-weights
        
        Returns:
            Object path in MinIO
        """
        logger.info(f"Uploading meta-weights version {version}")
        
        # Create temporary directory
        temp_dir = f"/tmp/meta_weights_{version}"
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # Save weights
            weights_path = os.path.join(temp_dir, "meta_weights.pt")
            torch.save(weights, weights_path)
            
            # Upload weights
            object_name = f"meta-weights/{version}/meta_weights.pt"
            upload_result = self.client.fput_object(
                self.bucket_name,
                object_name,
                weights_path
            )
            
            logger.info(f"✓ Meta-weights uploaded: {object_name}")
            
            # Build and upload metadata
            metadata_doc = dict(metadata or {})
            metadata_doc["version"] = version
            metadata_doc["uploaded_at"] = datetime.now().isoformat()
            metadata_doc["weights_object_path"] = object_name
            metadata_doc["weights_object_version_id"] = getattr(upload_result, "version_id", None)
            metadata_doc["training_config"] = training_config or metadata_doc.get("training_config", {})
            metadata_doc["linked_adapter_versions"] = sorted(
                set(linked_adapter_versions or metadata_doc.get("linked_adapter_versions", []))
            )

            metadata_name = f"meta-weights/{version}/metadata.json"
            self._put_json(metadata_name, metadata_doc)

            logger.info(f"✓ Metadata uploaded: {metadata_name}")
            
            # Cleanup
            shutil.rmtree(temp_dir)
            
            return object_name
            
        except S3Error as e:
            logger.error(f"Failed to upload meta-weights: {e}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise
    
    def download_meta_weights(
        self,
        version: str,
        local_dir: str = "/tmp/meta_weights"
    ) -> Dict[str, torch.Tensor]:
        """
        Download meta-weights from MinIO.
        
        Args:
            version: Version identifier
            local_dir: Local directory to download to
        
        Returns:
            Dictionary of meta-weights
        """
        logger.info(f"Downloading meta-weights version {version}")
        
        # Create local directory
        os.makedirs(local_dir, exist_ok=True)
        
        # Download weights
        object_name = f"meta-weights/{version}/meta_weights.pt"
        local_path = os.path.join(local_dir, f"meta_weights_{version}.pt")
        
        try:
            self.client.fget_object(
                self.bucket_name,
                object_name,
                local_path
            )
            
            # Load weights
            weights = torch.load(local_path, map_location='cpu')
            
            logger.info(f"✓ Meta-weights downloaded: {version}")
            
            return weights
            
        except S3Error as e:
            logger.error(f"Failed to download meta-weights: {e}")
            raise
    
    def list_versions(self) -> List[Dict[str, Any]]:
        """
        List all available meta-weights versions.
        
        Returns:
            List of version metadata
        """
        logger.info("Listing meta-weights versions...")
        
        versions = []
        
        try:
            # List objects in meta-weights/ prefix
            objects = self.client.list_objects(
                self.bucket_name,
                prefix="meta-weights/",
                recursive=False
            )
            
            # Extract unique versions
            version_names = set()
            for obj in objects:
                parts = obj.object_name.split('/')
                if len(parts) >= 2:
                    version_names.add(parts[1])
            
            # Get metadata for each version
            for version in sorted(version_names, reverse=True):
                metadata = self.get_metadata(version)
                if metadata:
                    versions.append(metadata)
            
            logger.info(f"✓ Found {len(versions)} versions")
            return versions
            
        except S3Error as e:
            logger.error(f"Failed to list versions: {e}")
            return []
    
    def get_metadata(self, version: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific version.
        
        Args:
            version: Version identifier
        
        Returns:
            Metadata dictionary or None
        """
        try:
            metadata_name = f"meta-weights/{version}/metadata.json"
            
            return self._get_json(metadata_name)
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                # Metadata doesn't exist, return basic info
                return {
                    "version": version,
                    "metadata_missing": True
                }
            logger.error(f"Failed to get metadata: {e}")
            return None
    
    def get_latest_version(self) -> Optional[str]:
        """
        Get the latest meta-weights version.
        
        Returns:
            Latest version string or None
        """
        versions = self.list_versions()
        
        if not versions:
            return None
        
        # Return version with latest timestamp
        latest = max(versions, key=lambda v: v.get('uploaded_at', ''))
        return latest.get('version')

    def link_adapter_to_meta_weights(
        self,
        meta_version: str,
        adapter_version: str
    ) -> bool:
        """
        Link a downstream LoRA adapter to a meta-weights version.

        Args:
            meta_version: Meta-weights version identifier
            adapter_version: Dependent LoRA adapter version identifier

        Returns:
            True if successful
        """
        metadata = self.get_metadata(meta_version)
        if not metadata:
            logger.error(f"Cannot link adapter {adapter_version}: meta version {meta_version} not found")
            return False

        linked = set(metadata.get("linked_adapter_versions", []))
        linked.add(adapter_version)
        metadata["linked_adapter_versions"] = sorted(linked)

        try:
            metadata_name = f"meta-weights/{meta_version}/metadata.json"
            self._put_json(metadata_name, metadata)
            logger.info(f"✓ Linked adapter {adapter_version} -> meta-weights {meta_version}")
            return True
        except S3Error as e:
            logger.error(f"Failed to link adapter to meta-weights: {e}")
            return False

    def get_adapter_dependencies(self, adapter_version: str) -> List[str]:
        """
        Get all meta-weights versions linked to a downstream LoRA adapter.

        Args:
            adapter_version: LoRA adapter version identifier

        Returns:
            List of dependent meta-weights versions
        """
        dependencies = []
        for version_data in self.list_versions():
            if adapter_version in version_data.get("linked_adapter_versions", []):
                dependencies.append(version_data.get("version"))
        return [version for version in dependencies if version]
    
    def delete_version(self, version: str) -> bool:
        """
        Delete a meta-weights version.
        
        Args:
            version: Version identifier
        
        Returns:
            True if successful
        """
        logger.info(f"Deleting meta-weights version {version}")
        
        try:
            # Delete all objects for this version
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=f"meta-weights/{version}/",
                recursive=True
            )
            
            for obj in objects:
                self.client.remove_object(self.bucket_name, obj.object_name)
            
            logger.info(f"✓ Version {version} deleted")
            return True
            
        except S3Error as e:
            logger.error(f"Failed to delete version: {e}")
            return False
    
    def compare_versions(
        self,
        version1: str,
        version2: str
    ) -> Dict[str, Any]:
        """
        Compare two meta-weights versions.
        
        Args:
            version1: First version
            version2: Second version
        
        Returns:
            Comparison results
        """
        logger.info(f"Comparing versions: {version1} vs {version2}")
        
        # Get metadata
        meta1 = self.get_metadata(version1)
        meta2 = self.get_metadata(version2)
        
        if not meta1 or not meta2:
            return {"error": "One or both versions not found"}
        
        comparison = {
            "version1": version1,
            "version2": version2,
            "metadata1": meta1,
            "metadata2": meta2,
            "metrics_comparison": {}
        }
        
        # Compare metrics if available
        metrics1 = meta1.get("metrics", {})
        metrics2 = meta2.get("metrics", {})
        
        for key in set(metrics1.keys()) | set(metrics2.keys()):
            v1 = metrics1.get(key)
            v2 = metrics2.get(key)
            
            if v1 is not None and v2 is not None:
                if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                    diff = v2 - v1
                    pct_change = (diff / v1 * 100) if v1 != 0 else 0
                    comparison["metrics_comparison"][key] = {
                        "v1": v1,
                        "v2": v2,
                        "diff": diff,
                        "pct_change": pct_change
                    }
        
        return comparison
    
    def export_version_history(
        self,
        output_path: str
    ):
        """
        Export version history to JSON file.
        
        Args:
            output_path: Output file path
        """
        versions = self.list_versions()
        
        history = {
            "total_versions": len(versions),
            "versions": versions,
            "exported_at": datetime.now().isoformat()
        }
        
        with open(output_path, 'w') as f:
            json.dump(history, f, indent=2, default=str)
        
        logger.info(f"✓ Version history exported to {output_path}")
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Statistics dictionary
        """
        try:
            objects = list(self.client.list_objects(
                self.bucket_name,
                prefix="meta-weights/",
                recursive=True
            ))
            
            total_size = sum(obj.size for obj in objects)
            num_versions = len(set(
                obj.object_name.split('/')[1]
                for obj in objects
                if len(obj.object_name.split('/')) >= 2
            ))
            
            return {
                "bucket": self.bucket_name,
                "num_versions": num_versions,
                "total_objects": len(objects),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "avg_size_per_version_mb": round(total_size / num_versions / (1024 * 1024), 2) if num_versions > 0 else 0
            }
            
        except S3Error as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {}
    
    def backup_version(
        self,
        version: str,
        backup_bucket: Optional[str] = None
    ) -> bool:
        """
        Backup a version to a different bucket.
        
        Args:
            version: Version to backup
            backup_bucket: Backup bucket name (defaults to <bucket>-backup)
        
        Returns:
            True if successful
        """
        if backup_bucket is None:
            backup_bucket = f"{self.bucket_name}-backup"
        
        logger.info(f"Backing up version {version} to {backup_bucket}")
        
        try:
            # Ensure backup bucket exists
            if not self.client.bucket_exists(backup_bucket):
                self.client.make_bucket(backup_bucket)
            
            # Copy all objects for this version
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=f"meta-weights/{version}/",
                recursive=True
            )
            
            for obj in objects:
                self.client.copy_object(
                    backup_bucket,
                    obj.object_name,
                    f"{self.bucket_name}/{obj.object_name}"
                )
            
            logger.info(f"✓ Version {version} backed up to {backup_bucket}")
            return True
            
        except S3Error as e:
            logger.error(f"Failed to backup version: {e}")
            return False

    def _put_json(self, object_name: str, payload: Dict[str, Any]):
        """Upload a JSON document to MinIO."""
        payload_bytes = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.client.put_object(
            self.bucket_name,
            object_name,
            data=BytesIO(payload_bytes),
            length=len(payload_bytes),
            content_type="application/json"
        )

    def _get_json(self, object_name: str) -> Dict[str, Any]:
        """Download and parse a JSON document from MinIO."""
        response = self.client.get_object(self.bucket_name, object_name)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
            response.release_conn()
