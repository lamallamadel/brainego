"""
Adapter Storage on MinIO

Manages LoRA adapter versioning and storage on MinIO S3-compatible storage.
"""

import os
import logging
import json
import shutil
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class AdapterStorage:
    """
    Manages LoRA adapter storage on MinIO.
    
    Adapters are versioned (v1.0, v1.1, v1.2, ...) and stored with metadata.
    """
    
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str = "lora-adapters",
        secure: bool = False
    ):
        """
        Initialize adapter storage.
        
        Args:
            endpoint: MinIO endpoint (host:port)
            access_key: MinIO access key
            secret_key: MinIO secret key
            bucket_name: Bucket name for adapters
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
        
        logger.info(f"Adapter storage initialized: {endpoint}/{bucket_name}")
    
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
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Upload LoRA adapter to MinIO.
        
        Args:
            local_path: Local path to adapter directory
            version: Version identifier (e.g., v1.0)
            metadata: Optional metadata dictionary
        
        Returns:
            Object path in MinIO
        """
        logger.info(f"Uploading adapter {version} from {local_path}")
        
        # Create a tar archive of the adapter
        archive_path = f"/tmp/adapter_{version}.tar.gz"
        shutil.make_archive(
            archive_path.replace('.tar.gz', ''),
            'gztar',
            local_path
        )
        
        try:
            # Upload archive
            object_name = f"adapters/{version}/adapter.tar.gz"
            self.client.fput_object(
                self.bucket_name,
                object_name,
                archive_path
            )
            
            logger.info(f"✓ Adapter uploaded: {object_name}")
            
            # Upload metadata
            if metadata:
                metadata_str = json.dumps(metadata, indent=2)
                metadata_name = f"adapters/{version}/metadata.json"
                
                self.client.put_object(
                    self.bucket_name,
                    metadata_name,
                    data=metadata_str.encode('utf-8'),
                    length=len(metadata_str),
                    content_type='application/json'
                )
                
                logger.info(f"✓ Metadata uploaded: {metadata_name}")
            
            # Cleanup
            os.remove(archive_path)
            
            return object_name
            
        except S3Error as e:
            logger.error(f"Failed to upload adapter: {e}")
            raise
    
    async def download_adapter(
        self,
        version: str,
        local_dir: str = "/tmp/adapters"
    ) -> str:
        """
        Download LoRA adapter from MinIO.
        
        Args:
            version: Version identifier
            local_dir: Local directory to download to
        
        Returns:
            Local path to extracted adapter
        """
        logger.info(f"Downloading adapter {version}")
        
        # Create local directory
        os.makedirs(local_dir, exist_ok=True)
        
        # Download archive
        object_name = f"adapters/{version}/adapter.tar.gz"
        local_archive = os.path.join(local_dir, f"adapter_{version}.tar.gz")
        
        try:
            self.client.fget_object(
                self.bucket_name,
                object_name,
                local_archive
            )
            
            # Extract archive
            extract_dir = os.path.join(local_dir, version)
            os.makedirs(extract_dir, exist_ok=True)
            
            shutil.unpack_archive(local_archive, extract_dir)
            
            # Cleanup archive
            os.remove(local_archive)
            
            logger.info(f"✓ Adapter downloaded to {extract_dir}")
            return extract_dir
            
        except S3Error as e:
            logger.error(f"Failed to download adapter: {e}")
            raise
    
    async def list_adapters(self) -> List[Dict[str, Any]]:
        """
        List all available adapters.
        
        Returns:
            List of adapter metadata
        """
        logger.info("Listing adapters...")
        
        adapters = []
        
        try:
            # List objects in adapters/ prefix
            objects = self.client.list_objects(
                self.bucket_name,
                prefix="adapters/",
                recursive=False
            )
            
            # Extract unique versions
            versions = set()
            for obj in objects:
                parts = obj.object_name.split('/')
                if len(parts) >= 2:
                    versions.add(parts[1])
            
            # Get metadata for each version
            for version in sorted(versions):
                metadata = await self.get_adapter_metadata(version)
                if metadata:
                    adapters.append(metadata)
            
            logger.info(f"✓ Found {len(adapters)} adapters")
            return adapters
            
        except S3Error as e:
            logger.error(f"Failed to list adapters: {e}")
            return []
    
    async def get_adapter_metadata(
        self,
        version: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific adapter.
        
        Args:
            version: Version identifier
        
        Returns:
            Metadata dictionary or None
        """
        try:
            metadata_name = f"adapters/{version}/metadata.json"
            
            response = self.client.get_object(
                self.bucket_name,
                metadata_name
            )
            
            metadata = json.loads(response.read().decode('utf-8'))
            metadata['version'] = version
            
            response.close()
            response.release_conn()
            
            return metadata
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                # Metadata doesn't exist, return basic info
                return {
                    "version": version,
                    "metadata_missing": True
                }
            logger.error(f"Failed to get adapter metadata: {e}")
            return None
    
    def delete_adapter(self, version: str) -> bool:
        """
        Delete an adapter version.
        
        Args:
            version: Version identifier
        
        Returns:
            True if successful
        """
        logger.info(f"Deleting adapter {version}")
        
        try:
            # Delete all objects for this version
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=f"adapters/{version}/",
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
        """
        Get the latest adapter version.
        
        Returns:
            Latest version string or None
        """
        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix="adapters/",
                recursive=False
            )
            
            versions = []
            for obj in objects:
                parts = obj.object_name.split('/')
                if len(parts) >= 2:
                    versions.append(parts[1])
            
            if versions:
                # Sort versions (assumes vX.Y format)
                sorted_versions = sorted(
                    versions,
                    key=lambda v: tuple(map(int, v.replace('v', '').split('.'))),
                    reverse=True
                )
                return sorted_versions[0]
            
            return None
            
        except S3Error as e:
            logger.error(f"Failed to get latest version: {e}")
            return None
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Statistics dictionary
        """
        try:
            objects = list(self.client.list_objects(
                self.bucket_name,
                prefix="adapters/",
                recursive=True
            ))
            
            total_size = sum(obj.size for obj in objects)
            num_adapters = len(set(
                obj.object_name.split('/')[1]
                for obj in objects
                if len(obj.object_name.split('/')) >= 2
            ))
            
            return {
                "bucket": self.bucket_name,
                "num_adapters": num_adapters,
                "total_objects": len(objects),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
            
        except S3Error as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {}
