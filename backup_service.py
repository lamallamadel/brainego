#!/usr/bin/env python3
"""
Automated Backup Service for AI Platform
Handles daily backups of Qdrant, Neo4j, and PostgreSQL to MinIO with 30-day retention
"""

import os
import sys
import json
import logging
import hashlib
import tempfile
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

import httpx
import psycopg2
from boto3 import client as boto3_client
from botocore.exceptions import ClientError
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class BackupMetadata:
    """Metadata for backup tracking"""
    backup_id: str
    backup_type: str
    timestamp: str
    size_bytes: int
    checksum: str
    status: str
    error_message: Optional[str] = None


class BackupService:
    """Main backup service orchestrator"""
    
    def __init__(self):
        # MinIO configuration
        self.minio_endpoint = os.getenv('MINIO_ENDPOINT', 'minio:9000')
        self.minio_access_key = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
        self.minio_secret_key = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
        self.backup_bucket = os.getenv('BACKUP_BUCKET', 'backups')
        
        # Qdrant configuration
        self.qdrant_host = os.getenv('QDRANT_HOST', 'qdrant')
        self.qdrant_port = int(os.getenv('QDRANT_PORT', '6333'))
        
        # Neo4j configuration
        self.neo4j_host = os.getenv('NEO4J_HOST', 'neo4j')
        self.neo4j_port = int(os.getenv('NEO4J_PORT', '7687'))
        self.neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
        self.neo4j_password = os.getenv('NEO4J_PASSWORD', 'neo4j_password')
        
        # PostgreSQL configuration
        self.postgres_host = os.getenv('POSTGRES_HOST', 'postgres')
        self.postgres_port = int(os.getenv('POSTGRES_PORT', '5432'))
        self.postgres_db = os.getenv('POSTGRES_DB', 'ai_platform')
        self.postgres_user = os.getenv('POSTGRES_USER', 'ai_user')
        self.postgres_password = os.getenv('POSTGRES_PASSWORD', 'ai_password')
        
        # Backup configuration
        self.retention_days = int(os.getenv('BACKUP_RETENTION_DAYS', '30'))
        self.backup_schedule = os.getenv('BACKUP_SCHEDULE', '0 2 * * *')  # 2 AM daily
        
        # Initialize S3 client
        self.s3_client = boto3_client(
            's3',
            endpoint_url=f'http://{self.minio_endpoint}',
            aws_access_key_id=self.minio_access_key,
            aws_secret_access_key=self.minio_secret_key
        )
        
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Ensure backup bucket exists"""
        try:
            self.s3_client.head_bucket(Bucket=self.backup_bucket)
            logger.info(f"Backup bucket '{self.backup_bucket}' exists")
        except ClientError:
            logger.info(f"Creating backup bucket '{self.backup_bucket}'")
            self.s3_client.create_bucket(Bucket=self.backup_bucket)
    
    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _upload_to_minio(
        self,
        local_path: str,
        remote_key: str,
        metadata: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """Upload file to MinIO with metadata"""
        try:
            self.s3_client.upload_file(
                local_path,
                self.backup_bucket,
                remote_key,
                ExtraArgs={'Metadata': metadata}
            )
            logger.info(f"Uploaded {local_path} to {remote_key}")
            return True, None
        except Exception as e:
            error_msg = f"Failed to upload {local_path}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def backup_qdrant(self) -> BackupMetadata:
        """Backup Qdrant vector database using snapshot API"""
        backup_id = f"qdrant_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting Qdrant backup: {backup_id}")
        
        try:
            # Create snapshot via Qdrant API
            async_client = httpx.Client(timeout=300.0)
            snapshot_url = f"http://{self.qdrant_host}:{self.qdrant_port}/snapshots"
            
            response = async_client.post(snapshot_url)
            response.raise_for_status()
            snapshot_info = response.json()
            snapshot_name = snapshot_info.get('result', {}).get('name')
            
            if not snapshot_name:
                raise ValueError("Failed to get snapshot name from Qdrant")
            
            logger.info(f"Qdrant snapshot created: {snapshot_name}")
            
            # Download snapshot
            download_url = f"{snapshot_url}/{snapshot_name}"
            with tempfile.NamedTemporaryFile(delete=False, suffix='.snapshot') as tmp_file:
                response = async_client.get(download_url)
                response.raise_for_status()
                tmp_file.write(response.content)
                tmp_path = tmp_file.name
            
            # Calculate checksum
            checksum = self._calculate_checksum(tmp_path)
            size_bytes = os.path.getsize(tmp_path)
            
            # Upload to MinIO
            timestamp = datetime.utcnow().isoformat()
            remote_key = f"qdrant/{datetime.utcnow().strftime('%Y/%m/%d')}/{backup_id}.snapshot"
            
            metadata = {
                'backup_id': backup_id,
                'backup_type': 'qdrant',
                'timestamp': timestamp,
                'checksum': checksum
            }
            
            success, error = self._upload_to_minio(tmp_path, remote_key, metadata)
            
            # Cleanup
            os.unlink(tmp_path)
            async_client.close()
            
            # Delete snapshot from Qdrant to save space
            try:
                async_client = httpx.Client(timeout=30.0)
                delete_response = async_client.delete(download_url)
                delete_response.raise_for_status()
                async_client.close()
            except Exception as e:
                logger.warning(f"Failed to delete Qdrant snapshot: {e}")
            
            return BackupMetadata(
                backup_id=backup_id,
                backup_type='qdrant',
                timestamp=timestamp,
                size_bytes=size_bytes,
                checksum=checksum,
                status='success' if success else 'failed',
                error_message=error
            )
            
        except Exception as e:
            error_msg = f"Qdrant backup failed: {str(e)}"
            logger.error(error_msg)
            return BackupMetadata(
                backup_id=backup_id,
                backup_type='qdrant',
                timestamp=datetime.utcnow().isoformat(),
                size_bytes=0,
                checksum='',
                status='failed',
                error_message=error_msg
            )
    
    def backup_neo4j(self) -> BackupMetadata:
        """Backup Neo4j graph database using neo4j-admin dump"""
        backup_id = f"neo4j_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting Neo4j backup: {backup_id}")
        
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.dump') as tmp_file:
                tmp_path = tmp_file.name
            
            # Execute neo4j-admin dump command in container
            dump_cmd = [
                'docker', 'exec', 'neo4j',
                'neo4j-admin', 'database', 'dump',
                'neo4j',
                '--to-path=/tmp',
                '--overwrite-destination=true'
            ]
            
            result = subprocess.run(
                dump_cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Neo4j dump failed: {result.stderr}")
            
            logger.info("Neo4j dump created successfully")
            
            # Copy dump file from container
            copy_cmd = [
                'docker', 'cp',
                'neo4j:/tmp/neo4j.dump',
                tmp_path
            ]
            
            result = subprocess.run(
                copy_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to copy Neo4j dump: {result.stderr}")
            
            # Calculate checksum
            checksum = self._calculate_checksum(tmp_path)
            size_bytes = os.path.getsize(tmp_path)
            
            # Upload to MinIO
            timestamp = datetime.utcnow().isoformat()
            remote_key = f"neo4j/{datetime.utcnow().strftime('%Y/%m/%d')}/{backup_id}.dump"
            
            metadata = {
                'backup_id': backup_id,
                'backup_type': 'neo4j',
                'timestamp': timestamp,
                'checksum': checksum
            }
            
            success, error = self._upload_to_minio(tmp_path, remote_key, metadata)
            
            # Cleanup
            os.unlink(tmp_path)
            
            return BackupMetadata(
                backup_id=backup_id,
                backup_type='neo4j',
                timestamp=timestamp,
                size_bytes=size_bytes,
                checksum=checksum,
                status='success' if success else 'failed',
                error_message=error
            )
            
        except Exception as e:
            error_msg = f"Neo4j backup failed: {str(e)}"
            logger.error(error_msg)
            return BackupMetadata(
                backup_id=backup_id,
                backup_type='neo4j',
                timestamp=datetime.utcnow().isoformat(),
                size_bytes=0,
                checksum='',
                status='failed',
                error_message=error_msg
            )
    
    def backup_postgresql(self) -> BackupMetadata:
        """Backup PostgreSQL database using pg_dump"""
        backup_id = f"postgres_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting PostgreSQL backup: {backup_id}")
        
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.sql.gz') as tmp_file:
                tmp_path = tmp_file.name
            
            # Execute pg_dump with compression
            dump_cmd = [
                'docker', 'exec', 'postgres',
                'pg_dump',
                '-U', self.postgres_user,
                '-d', self.postgres_db,
                '-F', 'c',  # Custom format (compressed)
                '-f', '/tmp/backup.dump'
            ]
            
            env = os.environ.copy()
            env['PGPASSWORD'] = self.postgres_password
            
            result = subprocess.run(
                dump_cmd,
                capture_output=True,
                text=True,
                timeout=600,
                env=env
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"pg_dump failed: {result.stderr}")
            
            logger.info("PostgreSQL dump created successfully")
            
            # Copy dump file from container
            copy_cmd = [
                'docker', 'cp',
                'postgres:/tmp/backup.dump',
                tmp_path
            ]
            
            result = subprocess.run(
                copy_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to copy PostgreSQL dump: {result.stderr}")
            
            # Calculate checksum
            checksum = self._calculate_checksum(tmp_path)
            size_bytes = os.path.getsize(tmp_path)
            
            # Upload to MinIO
            timestamp = datetime.utcnow().isoformat()
            remote_key = f"postgres/{datetime.utcnow().strftime('%Y/%m/%d')}/{backup_id}.dump"
            
            metadata = {
                'backup_id': backup_id,
                'backup_type': 'postgres',
                'timestamp': timestamp,
                'checksum': checksum
            }
            
            success, error = self._upload_to_minio(tmp_path, remote_key, metadata)
            
            # Cleanup
            os.unlink(tmp_path)
            
            return BackupMetadata(
                backup_id=backup_id,
                backup_type='postgres',
                timestamp=timestamp,
                size_bytes=size_bytes,
                checksum=checksum,
                status='success' if success else 'failed',
                error_message=error
            )
            
        except Exception as e:
            error_msg = f"PostgreSQL backup failed: {str(e)}"
            logger.error(error_msg)
            return BackupMetadata(
                backup_id=backup_id,
                backup_type='postgres',
                timestamp=datetime.utcnow().isoformat(),
                size_bytes=0,
                checksum='',
                status='failed',
                error_message=error_msg
            )
    
    def cleanup_old_backups(self):
        """Remove backups older than retention period"""
        logger.info(f"Cleaning up backups older than {self.retention_days} days")
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
            
            # List all objects in backup bucket
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.backup_bucket)
            
            deleted_count = 0
            for page in pages:
                if 'Contents' not in page:
                    continue
                    
                for obj in page['Contents']:
                    # Check object age
                    if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                        try:
                            self.s3_client.delete_object(
                                Bucket=self.backup_bucket,
                                Key=obj['Key']
                            )
                            deleted_count += 1
                            logger.info(f"Deleted old backup: {obj['Key']}")
                        except Exception as e:
                            logger.error(f"Failed to delete {obj['Key']}: {e}")
            
            logger.info(f"Cleanup complete. Deleted {deleted_count} old backups")
            
        except Exception as e:
            logger.error(f"Backup cleanup failed: {str(e)}")
    
    def run_full_backup(self):
        """Execute full backup of all databases"""
        logger.info("=" * 80)
        logger.info("Starting full backup cycle")
        logger.info("=" * 80)
        
        results = []
        
        # Backup Qdrant
        try:
            qdrant_result = self.backup_qdrant()
            results.append(qdrant_result)
        except Exception as e:
            logger.error(f"Qdrant backup exception: {e}")
        
        # Backup Neo4j
        try:
            neo4j_result = self.backup_neo4j()
            results.append(neo4j_result)
        except Exception as e:
            logger.error(f"Neo4j backup exception: {e}")
        
        # Backup PostgreSQL
        try:
            postgres_result = self.backup_postgresql()
            results.append(postgres_result)
        except Exception as e:
            logger.error(f"PostgreSQL backup exception: {e}")
        
        # Cleanup old backups
        try:
            self.cleanup_old_backups()
        except Exception as e:
            logger.error(f"Cleanup exception: {e}")
        
        # Log summary
        logger.info("=" * 80)
        logger.info("Backup cycle complete")
        logger.info("=" * 80)
        
        for result in results:
            status_symbol = "✓" if result.status == "success" else "✗"
            logger.info(
                f"{status_symbol} {result.backup_type.upper()}: "
                f"{result.size_bytes / (1024 * 1024):.2f} MB - "
                f"{result.status}"
            )
            if result.error_message:
                logger.error(f"  Error: {result.error_message}")
        
        # Store backup metadata
        self._store_backup_metadata(results)
    
    def _store_backup_metadata(self, results: List[BackupMetadata]):
        """Store backup metadata in PostgreSQL for tracking"""
        try:
            conn = psycopg2.connect(
                host=self.postgres_host,
                port=self.postgres_port,
                database=self.postgres_db,
                user=self.postgres_user,
                password=self.postgres_password
            )
            cursor = conn.cursor()
            
            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backup_history (
                    id SERIAL PRIMARY KEY,
                    backup_id VARCHAR(255) NOT NULL,
                    backup_type VARCHAR(50) NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    size_bytes BIGINT,
                    checksum VARCHAR(64),
                    status VARCHAR(20),
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert backup records
            for result in results:
                cursor.execute("""
                    INSERT INTO backup_history 
                    (backup_id, backup_type, timestamp, size_bytes, checksum, status, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    result.backup_id,
                    result.backup_type,
                    result.timestamp,
                    result.size_bytes,
                    result.checksum,
                    result.status,
                    result.error_message
                ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info("Backup metadata stored successfully")
            
        except Exception as e:
            logger.error(f"Failed to store backup metadata: {e}")


def main():
    """Main entry point"""
    logger.info("Backup Service Starting...")
    
    backup_service = BackupService()
    
    # Check if running in one-shot mode
    if '--run-once' in sys.argv:
        logger.info("Running in one-shot mode")
        backup_service.run_full_backup()
        sys.exit(0)
    
    # Setup scheduler for periodic backups
    scheduler = BlockingScheduler()
    
    # Add backup job
    scheduler.add_job(
        backup_service.run_full_backup,
        trigger=CronTrigger.from_crontab(backup_service.backup_schedule),
        id='full_backup',
        name='Full Database Backup',
        replace_existing=True
    )
    
    logger.info(f"Backup scheduled: {backup_service.backup_schedule}")
    logger.info("Backup service running. Press Ctrl+C to exit.")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Backup service shutting down...")


if __name__ == '__main__':
    main()
