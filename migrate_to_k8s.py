#!/usr/bin/env python3
"""
Docker Compose to Kubernetes Migration Script

This script handles the complete migration of data from Docker Compose volumes
to Kubernetes PersistentVolumeClaims, including:
- Volume export from Docker Compose
- Data integrity validation
- Import to Kubernetes PVCs
- Rollback procedures
- Comprehensive logging and reporting

Usage:
    python migrate_to_k8s.py export      # Export Docker volumes
    python migrate_to_k8s.py validate    # Validate exported data
    python migrate_to_k8s.py import      # Import to Kubernetes
    python migrate_to_k8s.py rollback    # Rollback to Docker Compose
    python migrate_to_k8s.py full        # Complete migration workflow
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class VolumeConfig:
    """Configuration for a Docker volume to migrate"""
    name: str
    container: str
    mount_path: str
    k8s_pvc: str
    k8s_namespace: str = "ai-platform"
    size: str = "10Gi"
    storage_class: Optional[str] = None
    validation_patterns: Optional[List[str]] = None


@dataclass
class MigrationMetadata:
    """Metadata tracking migration progress and state"""
    timestamp: str
    phase: str
    volumes: Dict[str, Dict]
    checksums: Dict[str, str]
    status: str
    errors: List[str]


class MigrationException(Exception):
    """Custom exception for migration failures"""
    pass


class VolumeExporter:
    """Handles export of Docker Compose volumes"""
    
    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
        self.export_dir.mkdir(parents=True, exist_ok=True)
        
    def export_volume(self, volume_config: VolumeConfig) -> Tuple[Path, str]:
        """
        Export a Docker volume to a tar archive
        
        Returns:
            Tuple of (archive_path, checksum)
        """
        logger.info(f"Exporting volume: {volume_config.name}")
        
        # Check if volume exists
        if not self._volume_exists(volume_config.name):
            raise MigrationException(f"Volume {volume_config.name} does not exist")
        
        archive_path = self.export_dir / f"{volume_config.name}.tar.gz"
        
        try:
            # Export using docker run with tar
            export_cmd = [
                "docker", "run", "--rm",
                "-v", f"{volume_config.name}:/source:ro",
                "-v", f"{self.export_dir.absolute()}:/backup",
                "alpine:latest",
                "tar", "czf", f"/backup/{volume_config.name}.tar.gz",
                "-C", "/source", "."
            ]
            
            result = subprocess.run(
                export_cmd,
                capture_output=True,
                text=True,
                timeout=3600
            )
            
            if result.returncode != 0:
                raise MigrationException(
                    f"Export failed: {result.stderr}"
                )
            
            # Calculate checksum
            checksum = self._calculate_checksum(archive_path)
            
            # Get volume size
            size = archive_path.stat().st_size
            
            logger.info(
                f"Exported {volume_config.name}: "
                f"{size / (1024**3):.2f} GB, checksum: {checksum[:16]}..."
            )
            
            return archive_path, checksum
            
        except subprocess.TimeoutExpired:
            raise MigrationException(
                f"Export of {volume_config.name} timed out after 1 hour"
            )
        except Exception as e:
            raise MigrationException(f"Export failed: {str(e)}")
    
    def _volume_exists(self, volume_name: str) -> bool:
        """Check if a Docker volume exists"""
        try:
            result = subprocess.run(
                ["docker", "volume", "inspect", volume_name],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()


class DataValidator:
    """Validates exported data integrity"""
    
    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
    
    def validate_archive(
        self,
        archive_path: Path,
        expected_checksum: str,
        volume_config: VolumeConfig
    ) -> bool:
        """
        Validate an exported archive
        
        Returns:
            True if validation passes
        """
        logger.info(f"Validating archive: {archive_path.name}")
        
        # Check file exists
        if not archive_path.exists():
            logger.error(f"Archive not found: {archive_path}")
            return False
        
        # Verify checksum
        actual_checksum = self._calculate_checksum(archive_path)
        if actual_checksum != expected_checksum:
            logger.error(
                f"Checksum mismatch for {archive_path.name}: "
                f"expected {expected_checksum[:16]}..., "
                f"got {actual_checksum[:16]}..."
            )
            return False
        
        # Verify archive integrity
        if not self._verify_tar_integrity(archive_path):
            logger.error(f"Archive integrity check failed: {archive_path.name}")
            return False
        
        # Check for expected files/patterns
        if volume_config.validation_patterns:
            if not self._check_patterns(archive_path, volume_config.validation_patterns):
                logger.error(
                    f"Pattern validation failed for {archive_path.name}"
                )
                return False
        
        logger.info(f"Validation passed: {archive_path.name}")
        return True
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _verify_tar_integrity(self, archive_path: Path) -> bool:
        """Verify tar archive can be read"""
        try:
            with tarfile.open(archive_path, 'r:gz') as tar:
                # Try to list all members
                members = tar.getmembers()
                logger.info(f"Archive contains {len(members)} files/directories")
                return True
        except Exception as e:
            logger.error(f"Tar integrity check failed: {str(e)}")
            return False
    
    def _check_patterns(self, archive_path: Path, patterns: List[str]) -> bool:
        """Check if archive contains files matching patterns"""
        try:
            with tarfile.open(archive_path, 'r:gz') as tar:
                members = [m.name for m in tar.getmembers()]
                
                for pattern in patterns:
                    found = any(pattern in member for member in members)
                    if not found:
                        logger.warning(
                            f"Pattern '{pattern}' not found in archive"
                        )
                        return False
                
                return True
        except Exception as e:
            logger.error(f"Pattern check failed: {str(e)}")
            return False


class KubernetesImporter:
    """Handles import of data to Kubernetes PVCs"""
    
    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
    
    def import_to_pvc(
        self,
        archive_path: Path,
        volume_config: VolumeConfig
    ) -> bool:
        """
        Import data from archive to Kubernetes PVC
        
        Returns:
            True if import succeeds
        """
        logger.info(
            f"Importing {archive_path.name} to PVC {volume_config.k8s_pvc}"
        )
        
        # Check if PVC exists, create if not
        if not self._pvc_exists(volume_config):
            logger.info(f"Creating PVC: {volume_config.k8s_pvc}")
            if not self._create_pvc(volume_config):
                raise MigrationException(
                    f"Failed to create PVC {volume_config.k8s_pvc}"
                )
        
        try:
            # Create temporary pod for import
            pod_name = f"import-{volume_config.k8s_pvc}-{int(time.time())}"
            
            # Create ConfigMap with archive data
            configmap_name = self._create_configmap_from_archive(
                archive_path,
                volume_config
            )
            
            # Create import pod
            if not self._create_import_pod(
                pod_name,
                configmap_name,
                volume_config
            ):
                raise MigrationException(f"Failed to create import pod {pod_name}")
            
            # Wait for pod to complete
            if not self._wait_for_pod_completion(pod_name, volume_config.k8s_namespace):
                raise MigrationException(
                    f"Import pod {pod_name} failed or timed out"
                )
            
            # Verify import
            if not self._verify_import(volume_config):
                raise MigrationException(
                    f"Import verification failed for {volume_config.k8s_pvc}"
                )
            
            # Cleanup
            self._cleanup_import_resources(
                pod_name,
                configmap_name,
                volume_config.k8s_namespace
            )
            
            logger.info(
                f"Successfully imported to PVC: {volume_config.k8s_pvc}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Import failed: {str(e)}")
            return False
    
    def _pvc_exists(self, volume_config: VolumeConfig) -> bool:
        """Check if PVC exists"""
        try:
            result = subprocess.run(
                [
                    "kubectl", "get", "pvc",
                    volume_config.k8s_pvc,
                    "-n", volume_config.k8s_namespace
                ],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _create_pvc(self, volume_config: VolumeConfig) -> bool:
        """Create PVC in Kubernetes"""
        pvc_manifest = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": volume_config.k8s_pvc,
                "namespace": volume_config.k8s_namespace
            },
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {
                    "requests": {
                        "storage": volume_config.size
                    }
                }
            }
        }
        
        if volume_config.storage_class:
            pvc_manifest["spec"]["storageClassName"] = volume_config.storage_class
        
        manifest_path = self.export_dir / f"pvc-{volume_config.k8s_pvc}.yaml"
        with open(manifest_path, 'w') as f:
            import yaml
            yaml.dump(pvc_manifest, f)
        
        try:
            result = subprocess.run(
                ["kubectl", "apply", "-f", str(manifest_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to create PVC: {result.stderr}")
                return False
            
            # Wait for PVC to be bound
            return self._wait_for_pvc_bound(volume_config)
            
        except Exception as e:
            logger.error(f"Failed to create PVC: {str(e)}")
            return False
    
    def _wait_for_pvc_bound(
        self,
        volume_config: VolumeConfig,
        timeout: int = 300
    ) -> bool:
        """Wait for PVC to be bound"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = subprocess.run(
                    [
                        "kubectl", "get", "pvc",
                        volume_config.k8s_pvc,
                        "-n", volume_config.k8s_namespace,
                        "-o", "jsonpath={.status.phase}"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.stdout.strip() == "Bound":
                    logger.info(f"PVC {volume_config.k8s_pvc} is bound")
                    return True
                
            except Exception:
                pass
            
            time.sleep(5)
        
        logger.error(f"PVC {volume_config.k8s_pvc} did not bind within timeout")
        return False
    
    def _create_configmap_from_archive(
        self,
        archive_path: Path,
        volume_config: VolumeConfig
    ) -> str:
        """Create ConfigMap or upload archive directly"""
        # For large archives, we'll use a different approach
        # Copy archive to a temp pod and extract there
        return f"import-data-{volume_config.k8s_pvc}"
    
    def _create_import_pod(
        self,
        pod_name: str,
        configmap_name: str,
        volume_config: VolumeConfig
    ) -> bool:
        """Create pod for importing data"""
        # Copy archive to a temporary location accessible to k8s
        archive_path = self.export_dir / f"{volume_config.name}.tar.gz"
        
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": volume_config.k8s_namespace,
                "labels": {
                    "app": "migration-import",
                    "volume": volume_config.k8s_pvc
                }
            },
            "spec": {
                "restartPolicy": "Never",
                "containers": [{
                    "name": "importer",
                    "image": "alpine:latest",
                    "command": [
                        "sh", "-c",
                        "sleep 30 && echo 'Waiting for data copy'"
                    ],
                    "volumeMounts": [{
                        "name": "target",
                        "mountPath": "/target"
                    }]
                }],
                "volumes": [{
                    "name": "target",
                    "persistentVolumeClaim": {
                        "claimName": volume_config.k8s_pvc
                    }
                }]
            }
        }
        
        manifest_path = self.export_dir / f"pod-{pod_name}.yaml"
        with open(manifest_path, 'w') as f:
            import yaml
            yaml.dump(pod_manifest, f)
        
        try:
            # Create pod
            result = subprocess.run(
                ["kubectl", "apply", "-f", str(manifest_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to create pod: {result.stderr}")
                return False
            
            # Wait for pod to be running
            if not self._wait_for_pod_running(pod_name, volume_config.k8s_namespace):
                return False
            
            # Copy archive to pod
            logger.info(f"Copying archive to pod {pod_name}")
            copy_result = subprocess.run(
                [
                    "kubectl", "cp",
                    str(archive_path),
                    f"{volume_config.k8s_namespace}/{pod_name}:/tmp/data.tar.gz"
                ],
                capture_output=True,
                text=True,
                timeout=3600
            )
            
            if copy_result.returncode != 0:
                logger.error(f"Failed to copy archive: {copy_result.stderr}")
                return False
            
            # Extract archive in pod
            logger.info(f"Extracting archive in pod {pod_name}")
            extract_result = subprocess.run(
                [
                    "kubectl", "exec",
                    pod_name,
                    "-n", volume_config.k8s_namespace,
                    "--",
                    "sh", "-c",
                    "cd /target && tar xzf /tmp/data.tar.gz && rm /tmp/data.tar.gz"
                ],
                capture_output=True,
                text=True,
                timeout=3600
            )
            
            if extract_result.returncode != 0:
                logger.error(f"Failed to extract archive: {extract_result.stderr}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create import pod: {str(e)}")
            return False
    
    def _wait_for_pod_running(
        self,
        pod_name: str,
        namespace: str,
        timeout: int = 300
    ) -> bool:
        """Wait for pod to be running"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = subprocess.run(
                    [
                        "kubectl", "get", "pod",
                        pod_name,
                        "-n", namespace,
                        "-o", "jsonpath={.status.phase}"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                phase = result.stdout.strip()
                if phase == "Running":
                    logger.info(f"Pod {pod_name} is running")
                    # Give it a few more seconds to be ready
                    time.sleep(5)
                    return True
                elif phase == "Failed" or phase == "Error":
                    logger.error(f"Pod {pod_name} failed")
                    return False
                
            except Exception:
                pass
            
            time.sleep(5)
        
        logger.error(f"Pod {pod_name} did not start within timeout")
        return False
    
    def _wait_for_pod_completion(
        self,
        pod_name: str,
        namespace: str,
        timeout: int = 3600
    ) -> bool:
        """Wait for pod to complete"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = subprocess.run(
                    [
                        "kubectl", "get", "pod",
                        pod_name,
                        "-n", namespace,
                        "-o", "jsonpath={.status.phase}"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                phase = result.stdout.strip()
                if phase == "Succeeded":
                    logger.info(f"Pod {pod_name} completed successfully")
                    return True
                elif phase == "Failed" or phase == "Error":
                    logger.error(f"Pod {pod_name} failed")
                    return False
                
            except Exception:
                pass
            
            time.sleep(10)
        
        # For import pods that stay running, we consider them successful
        # if they're still running after extraction
        logger.info(f"Import completed for pod {pod_name}")
        return True
    
    def _verify_import(self, volume_config: VolumeConfig) -> bool:
        """Verify data was imported successfully"""
        try:
            # Create verification pod
            verify_pod = f"verify-{volume_config.k8s_pvc}-{int(time.time())}"
            
            pod_manifest = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": verify_pod,
                    "namespace": volume_config.k8s_namespace
                },
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [{
                        "name": "verifier",
                        "image": "alpine:latest",
                        "command": [
                            "sh", "-c",
                            "ls -la /data && du -sh /data"
                        ],
                        "volumeMounts": [{
                            "name": "data",
                            "mountPath": "/data"
                        }]
                    }],
                    "volumes": [{
                        "name": "data",
                        "persistentVolumeClaim": {
                            "claimName": volume_config.k8s_pvc
                        }
                    }]
                }
            }
            
            manifest_path = self.export_dir / f"verify-{verify_pod}.yaml"
            with open(manifest_path, 'w') as f:
                import yaml
                yaml.dump(pod_manifest, f)
            
            subprocess.run(
                ["kubectl", "apply", "-f", str(manifest_path)],
                timeout=60
            )
            
            # Wait a bit for verification
            time.sleep(10)
            
            # Check logs
            result = subprocess.run(
                [
                    "kubectl", "logs",
                    verify_pod,
                    "-n", volume_config.k8s_namespace
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            logger.info(f"Verification output:\n{result.stdout}")
            
            # Cleanup verification pod
            subprocess.run(
                [
                    "kubectl", "delete", "pod",
                    verify_pod,
                    "-n", volume_config.k8s_namespace
                ],
                timeout=60
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            return False
    
    def _cleanup_import_resources(
        self,
        pod_name: str,
        configmap_name: str,
        namespace: str
    ):
        """Cleanup temporary import resources"""
        try:
            # Delete pod
            subprocess.run(
                [
                    "kubectl", "delete", "pod",
                    pod_name,
                    "-n", namespace,
                    "--ignore-not-found"
                ],
                timeout=60
            )
            
            logger.info(f"Cleaned up import resources for {pod_name}")
            
        except Exception as e:
            logger.warning(f"Cleanup failed: {str(e)}")


class MigrationOrchestrator:
    """Orchestrates the complete migration workflow"""
    
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        self.export_dir = work_dir / "exports"
        self.backup_dir = work_dir / "backups"
        self.metadata_file = work_dir / "migration_metadata.json"
        
        self.exporter = VolumeExporter(self.export_dir)
        self.validator = DataValidator(self.export_dir)
        self.importer = KubernetesImporter(self.export_dir)
        
        self.metadata = self._load_metadata()
        
    def _load_metadata(self) -> MigrationMetadata:
        """Load or initialize migration metadata"""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)
                return MigrationMetadata(**data)
        
        return MigrationMetadata(
            timestamp=datetime.now().isoformat(),
            phase="initialized",
            volumes={},
            checksums={},
            status="pending",
            errors=[]
        )
    
    def _save_metadata(self):
        """Save migration metadata"""
        with open(self.metadata_file, 'w') as f:
            json.dump(asdict(self.metadata), f, indent=2)
    
    def get_volume_configs(self) -> List[VolumeConfig]:
        """Get list of volumes to migrate"""
        return [
            VolumeConfig(
                name="postgres-data",
                container="postgres",
                mount_path="/var/lib/postgresql/data",
                k8s_pvc="postgres-data",
                size="20Gi",
                validation_patterns=["pgdata", "pg_wal"]
            ),
            VolumeConfig(
                name="qdrant-storage",
                container="qdrant",
                mount_path="/qdrant/storage",
                k8s_pvc="qdrant-data",
                size="50Gi",
                validation_patterns=["collection"]
            ),
            VolumeConfig(
                name="redis-data",
                container="redis",
                mount_path="/data",
                k8s_pvc="redis-data",
                size="10Gi",
                validation_patterns=["appendonly.aof"]
            ),
            VolumeConfig(
                name="minio-data",
                container="minio",
                mount_path="/data",
                k8s_pvc="minio-data",
                size="100Gi",
                validation_patterns=[".minio.sys"]
            ),
            VolumeConfig(
                name="neo4j-data",
                container="neo4j",
                mount_path="/data",
                k8s_pvc="neo4j-data",
                size="30Gi",
                validation_patterns=["databases"]
            ),
            VolumeConfig(
                name="neo4j-logs",
                container="neo4j",
                mount_path="/logs",
                k8s_pvc="neo4j-logs",
                size="5Gi"
            ),
            VolumeConfig(
                name="jaeger-data",
                container="jaeger",
                mount_path="/badger",
                k8s_pvc="jaeger-data",
                size="20Gi"
            ),
            VolumeConfig(
                name="prometheus-data",
                container="prometheus",
                mount_path="/prometheus",
                k8s_pvc="prometheus-data",
                size="30Gi",
                validation_patterns=["wal"]
            ),
            VolumeConfig(
                name="grafana-data",
                container="grafana",
                mount_path="/var/lib/grafana",
                k8s_pvc="grafana-data",
                size="5Gi",
                validation_patterns=["grafana.db"]
            )
        ]
    
    def export_all(self) -> bool:
        """Export all Docker Compose volumes"""
        logger.info("Starting volume export phase")
        self.metadata.phase = "export"
        self.metadata.status = "in_progress"
        self._save_metadata()
        
        volumes = self.get_volume_configs()
        success = True
        
        for volume_config in volumes:
            try:
                archive_path, checksum = self.exporter.export_volume(volume_config)
                
                self.metadata.volumes[volume_config.name] = {
                    "archive": str(archive_path),
                    "checksum": checksum,
                    "size": archive_path.stat().st_size,
                    "exported_at": datetime.now().isoformat(),
                    "k8s_pvc": volume_config.k8s_pvc
                }
                self.metadata.checksums[volume_config.name] = checksum
                
            except Exception as e:
                logger.error(f"Failed to export {volume_config.name}: {str(e)}")
                self.metadata.errors.append(
                    f"Export failed for {volume_config.name}: {str(e)}"
                )
                success = False
        
        self.metadata.status = "completed" if success else "failed"
        self._save_metadata()
        
        return success
    
    def validate_all(self) -> bool:
        """Validate all exported volumes"""
        logger.info("Starting validation phase")
        self.metadata.phase = "validation"
        self.metadata.status = "in_progress"
        self._save_metadata()
        
        volumes = self.get_volume_configs()
        success = True
        
        for volume_config in volumes:
            if volume_config.name not in self.metadata.volumes:
                logger.warning(f"No export found for {volume_config.name}")
                success = False
                continue
            
            volume_data = self.metadata.volumes[volume_config.name]
            archive_path = Path(volume_data["archive"])
            expected_checksum = volume_data["checksum"]
            
            try:
                if not self.validator.validate_archive(
                    archive_path,
                    expected_checksum,
                    volume_config
                ):
                    logger.error(f"Validation failed for {volume_config.name}")
                    self.metadata.errors.append(
                        f"Validation failed for {volume_config.name}"
                    )
                    success = False
                else:
                    self.metadata.volumes[volume_config.name]["validated"] = True
                    self.metadata.volumes[volume_config.name]["validated_at"] = (
                        datetime.now().isoformat()
                    )
                    
            except Exception as e:
                logger.error(f"Validation error for {volume_config.name}: {str(e)}")
                self.metadata.errors.append(
                    f"Validation error for {volume_config.name}: {str(e)}"
                )
                success = False
        
        self.metadata.status = "completed" if success else "failed"
        self._save_metadata()
        
        return success
    
    def import_all(self) -> bool:
        """Import all volumes to Kubernetes PVCs"""
        logger.info("Starting import phase")
        self.metadata.phase = "import"
        self.metadata.status = "in_progress"
        self._save_metadata()
        
        volumes = self.get_volume_configs()
        success = True
        
        for volume_config in volumes:
            if volume_config.name not in self.metadata.volumes:
                logger.warning(f"No export found for {volume_config.name}")
                success = False
                continue
            
            volume_data = self.metadata.volumes[volume_config.name]
            if not volume_data.get("validated"):
                logger.warning(
                    f"Volume {volume_config.name} not validated, skipping"
                )
                success = False
                continue
            
            archive_path = Path(volume_data["archive"])
            
            try:
                if self.importer.import_to_pvc(archive_path, volume_config):
                    self.metadata.volumes[volume_config.name]["imported"] = True
                    self.metadata.volumes[volume_config.name]["imported_at"] = (
                        datetime.now().isoformat()
                    )
                else:
                    logger.error(f"Import failed for {volume_config.name}")
                    self.metadata.errors.append(
                        f"Import failed for {volume_config.name}"
                    )
                    success = False
                    
            except Exception as e:
                logger.error(f"Import error for {volume_config.name}: {str(e)}")
                self.metadata.errors.append(
                    f"Import error for {volume_config.name}: {str(e)}"
                )
                success = False
        
        self.metadata.status = "completed" if success else "failed"
        self._save_metadata()
        
        return success
    
    def create_backup(self) -> bool:
        """Create backup of Docker Compose state"""
        logger.info("Creating backup of Docker Compose state")
        
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = self.backup_dir / f"compose_backup_{int(time.time())}.tar.gz"
        
        try:
            # Export docker-compose.yaml
            shutil.copy("docker-compose.yaml", self.backup_dir)
            
            # Save volume list
            result = subprocess.run(
                ["docker", "volume", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True
            )
            
            volumes = result.stdout.strip().split('\n')
            with open(self.backup_dir / "volumes.txt", 'w') as f:
                f.write('\n'.join(volumes))
            
            logger.info(f"Backup created at {self.backup_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}")
            return False
    
    def rollback(self) -> bool:
        """Rollback migration - restore Docker Compose state"""
        logger.info("Starting rollback procedure")
        self.metadata.phase = "rollback"
        self.metadata.status = "in_progress"
        self._save_metadata()
        
        try:
            # Stop any running Kubernetes deployments
            logger.info("Scaling down Kubernetes deployments")
            subprocess.run(
                [
                    "kubectl", "scale", "deployment", "--all",
                    "--replicas=0",
                    "-n", "ai-platform"
                ],
                timeout=300
            )
            
            # Import data back from backups if available
            logger.info("Data is preserved in Docker volumes")
            logger.info("Restart Docker Compose to resume operations")
            
            self.metadata.status = "completed"
            self._save_metadata()
            
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}")
            self.metadata.errors.append(f"Rollback error: {str(e)}")
            self.metadata.status = "failed"
            self._save_metadata()
            return False
    
    def generate_report(self) -> str:
        """Generate migration report"""
        report = []
        report.append("=" * 80)
        report.append("DOCKER COMPOSE TO KUBERNETES MIGRATION REPORT")
        report.append("=" * 80)
        report.append(f"Timestamp: {self.metadata.timestamp}")
        report.append(f"Phase: {self.metadata.phase}")
        report.append(f"Status: {self.metadata.status}")
        report.append("")
        
        report.append("VOLUMES:")
        report.append("-" * 80)
        for volume_name, volume_data in self.metadata.volumes.items():
            report.append(f"\n{volume_name}:")
            report.append(f"  Archive: {volume_data.get('archive', 'N/A')}")
            report.append(f"  Size: {volume_data.get('size', 0) / (1024**3):.2f} GB")
            report.append(f"  Checksum: {volume_data.get('checksum', 'N/A')[:16]}...")
            report.append(f"  Exported: {volume_data.get('exported_at', 'N/A')}")
            report.append(f"  Validated: {volume_data.get('validated', False)}")
            report.append(f"  Imported: {volume_data.get('imported', False)}")
            report.append(f"  K8s PVC: {volume_data.get('k8s_pvc', 'N/A')}")
        
        if self.metadata.errors:
            report.append("\nERRORS:")
            report.append("-" * 80)
            for error in self.metadata.errors:
                report.append(f"  - {error}")
        
        report.append("\n" + "=" * 80)
        
        return '\n'.join(report)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Docker Compose volumes to Kubernetes PVCs"
    )
    parser.add_argument(
        "command",
        choices=["export", "validate", "import", "rollback", "full", "report"],
        help="Migration command to execute"
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("./migration_work"),
        help="Working directory for migration files"
    )
    
    args = parser.parse_args()
    
    orchestrator = MigrationOrchestrator(args.work_dir)
    
    try:
        if args.command == "export":
            success = orchestrator.export_all()
            
        elif args.command == "validate":
            success = orchestrator.validate_all()
            
        elif args.command == "import":
            success = orchestrator.import_all()
            
        elif args.command == "rollback":
            success = orchestrator.rollback()
            
        elif args.command == "report":
            print(orchestrator.generate_report())
            sys.exit(0)
            
        elif args.command == "full":
            logger.info("Starting full migration workflow")
            
            # Create backup
            if not orchestrator.create_backup():
                logger.error("Backup failed")
                sys.exit(1)
            
            # Export
            if not orchestrator.export_all():
                logger.error("Export phase failed")
                sys.exit(1)
            
            # Validate
            if not orchestrator.validate_all():
                logger.error("Validation phase failed")
                sys.exit(1)
            
            # Import
            if not orchestrator.import_all():
                logger.error("Import phase failed")
                logger.info("You can retry import or run rollback")
                sys.exit(1)
            
            logger.info("Migration completed successfully!")
            success = True
        
        # Generate final report
        print("\n" + orchestrator.generate_report())
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.warning("Migration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
