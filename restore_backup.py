#!/usr/bin/env python3
"""
Backup Restoration Script for AI Platform
Restores Qdrant, Neo4j, and PostgreSQL from MinIO backups
"""

import os
import sys
import argparse
import logging
import tempfile
import subprocess
from datetime import datetime
from typing import Optional, List, Tuple

import httpx
import psycopg2
from boto3 import client as boto3_client
from botocore.exceptions import ClientError


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RestoreService:
    """Service for restoring backups"""
    
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
        self.neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
        self.neo4j_password = os.getenv('NEO4J_PASSWORD', 'neo4j_password')
        
        # PostgreSQL configuration
        self.postgres_host = os.getenv('POSTGRES_HOST', 'postgres')
        self.postgres_port = int(os.getenv('POSTGRES_PORT', '5432'))
        self.postgres_db = os.getenv('POSTGRES_DB', 'ai_platform')
        self.postgres_user = os.getenv('POSTGRES_USER', 'ai_user')
        self.postgres_password = os.getenv('POSTGRES_PASSWORD', 'ai_password')
        
        # Initialize S3 client
        self.s3_client = boto3_client(
            's3',
            endpoint_url=f'http://{self.minio_endpoint}',
            aws_access_key_id=self.minio_access_key,
            aws_secret_access_key=self.minio_secret_key
        )
    
    def list_available_backups(self, backup_type: Optional[str] = None) -> List[dict]:
        """List available backups from MinIO"""
        logger.info(f"Listing available backups (type: {backup_type or 'all'})")
        
        try:
            prefix = f"{backup_type}/" if backup_type else ""
            
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.backup_bucket, Prefix=prefix)
            
            backups = []
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    # Get object metadata
                    try:
                        response = self.s3_client.head_object(
                            Bucket=self.backup_bucket,
                            Key=obj['Key']
                        )
                        metadata = response.get('Metadata', {})
                        
                        backups.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'],
                            'backup_id': metadata.get('backup_id', 'unknown'),
                            'backup_type': metadata.get('backup_type', 'unknown'),
                            'checksum': metadata.get('checksum', '')
                        })
                    except Exception as e:
                        logger.warning(f"Failed to get metadata for {obj['Key']}: {e}")
            
            # Sort by last modified (newest first)
            backups.sort(key=lambda x: x['last_modified'], reverse=True)
            
            return backups
            
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []
    
    def restore_qdrant(self, backup_key: str) -> bool:
        """Restore Qdrant from backup"""
        logger.info(f"Restoring Qdrant from: {backup_key}")
        
        try:
            # Download backup from MinIO
            with tempfile.NamedTemporaryFile(delete=False, suffix='.snapshot') as tmp_file:
                tmp_path = tmp_file.name
                self.s3_client.download_file(
                    self.backup_bucket,
                    backup_key,
                    tmp_path
                )
            
            logger.info(f"Downloaded backup to {tmp_path}")
            
            # Upload snapshot to Qdrant
            client = httpx.Client(timeout=300.0)
            upload_url = f"http://{self.qdrant_host}:{self.qdrant_port}/snapshots/upload"
            
            with open(tmp_path, 'rb') as f:
                files = {'snapshot': f}
                response = client.post(upload_url, files=files)
                response.raise_for_status()
            
            logger.info("Snapshot uploaded to Qdrant")
            
            # Recover from snapshot
            snapshot_name = os.path.basename(tmp_path)
            recover_url = f"http://{self.qdrant_host}:{self.qdrant_port}/snapshots/{snapshot_name}/recover"
            
            response = client.post(recover_url)
            response.raise_for_status()
            
            client.close()
            
            # Cleanup
            os.unlink(tmp_path)
            
            logger.info("Qdrant restore completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Qdrant restore failed: {e}")
            return False
    
    def restore_neo4j(self, backup_key: str) -> bool:
        """Restore Neo4j from backup"""
        logger.info(f"Restoring Neo4j from: {backup_key}")
        
        try:
            # Download backup from MinIO
            with tempfile.NamedTemporaryFile(delete=False, suffix='.dump') as tmp_file:
                tmp_path = tmp_file.name
                self.s3_client.download_file(
                    self.backup_bucket,
                    backup_key,
                    tmp_path
                )
            
            logger.info(f"Downloaded backup to {tmp_path}")
            
            # Stop Neo4j
            logger.info("Stopping Neo4j...")
            subprocess.run(
                ['docker', 'exec', 'neo4j', 'neo4j', 'stop'],
                capture_output=True,
                timeout=60
            )
            
            # Copy dump to container
            copy_cmd = [
                'docker', 'cp',
                tmp_path,
                'neo4j:/tmp/restore.dump'
            ]
            
            result = subprocess.run(
                copy_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to copy dump to container: {result.stderr}")
            
            # Load dump
            logger.info("Loading Neo4j dump...")
            load_cmd = [
                'docker', 'exec', 'neo4j',
                'neo4j-admin', 'database', 'load',
                'neo4j',
                '--from-path=/tmp',
                '--overwrite-destination=true'
            ]
            
            result = subprocess.run(
                load_cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Neo4j load failed: {result.stderr}")
            
            # Start Neo4j
            logger.info("Starting Neo4j...")
            subprocess.run(
                ['docker', 'exec', 'neo4j', 'neo4j', 'start'],
                capture_output=True,
                timeout=60
            )
            
            # Cleanup
            os.unlink(tmp_path)
            
            logger.info("Neo4j restore completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Neo4j restore failed: {e}")
            # Try to restart Neo4j anyway
            try:
                subprocess.run(
                    ['docker', 'exec', 'neo4j', 'neo4j', 'start'],
                    capture_output=True,
                    timeout=60
                )
            except:
                pass
            return False
    
    def restore_postgresql(self, backup_key: str) -> bool:
        """Restore PostgreSQL from backup"""
        logger.info(f"Restoring PostgreSQL from: {backup_key}")
        
        try:
            # Download backup from MinIO
            with tempfile.NamedTemporaryFile(delete=False, suffix='.dump') as tmp_file:
                tmp_path = tmp_file.name
                self.s3_client.download_file(
                    self.backup_bucket,
                    backup_key,
                    tmp_path
                )
            
            logger.info(f"Downloaded backup to {tmp_path}")
            
            # Copy dump to container
            copy_cmd = [
                'docker', 'cp',
                tmp_path,
                'postgres:/tmp/restore.dump'
            ]
            
            result = subprocess.run(
                copy_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to copy dump to container: {result.stderr}")
            
            # Terminate active connections
            logger.info("Terminating active connections...")
            terminate_cmd = [
                'docker', 'exec', 'postgres',
                'psql',
                '-U', self.postgres_user,
                '-d', 'postgres',
                '-c',
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{self.postgres_db}' AND pid <> pg_backend_pid();"
            ]
            
            subprocess.run(terminate_cmd, capture_output=True, timeout=30)
            
            # Drop and recreate database
            logger.info("Recreating database...")
            drop_cmd = [
                'docker', 'exec', 'postgres',
                'psql',
                '-U', self.postgres_user,
                '-d', 'postgres',
                '-c', f'DROP DATABASE IF EXISTS {self.postgres_db};'
            ]
            
            subprocess.run(drop_cmd, capture_output=True, timeout=60)
            
            create_cmd = [
                'docker', 'exec', 'postgres',
                'psql',
                '-U', self.postgres_user,
                '-d', 'postgres',
                '-c', f'CREATE DATABASE {self.postgres_db} OWNER {self.postgres_user};'
            ]
            
            result = subprocess.run(
                create_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create database: {result.stderr}")
            
            # Restore dump
            logger.info("Restoring PostgreSQL dump...")
            restore_cmd = [
                'docker', 'exec', 'postgres',
                'pg_restore',
                '-U', self.postgres_user,
                '-d', self.postgres_db,
                '-F', 'c',
                '/tmp/restore.dump'
            ]
            
            result = subprocess.run(
                restore_cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                logger.warning(f"pg_restore warnings: {result.stderr}")
            
            # Cleanup
            os.unlink(tmp_path)
            
            logger.info("PostgreSQL restore completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"PostgreSQL restore failed: {e}")
            return False
    
    def validate_restore(self, backup_type: str) -> bool:
        """Validate that restore was successful"""
        logger.info(f"Validating {backup_type} restore...")
        
        try:
            if backup_type == 'qdrant':
                # Check Qdrant health
                client = httpx.Client(timeout=30.0)
                response = client.get(f"http://{self.qdrant_host}:{self.qdrant_port}/health")
                client.close()
                return response.status_code == 200
                
            elif backup_type == 'neo4j':
                # Check Neo4j is running
                result = subprocess.run(
                    ['docker', 'exec', 'neo4j', 'neo4j', 'status'],
                    capture_output=True,
                    timeout=30
                )
                return result.returncode == 0
                
            elif backup_type == 'postgres':
                # Check PostgreSQL connection
                conn = psycopg2.connect(
                    host=self.postgres_host,
                    port=self.postgres_port,
                    database=self.postgres_db,
                    user=self.postgres_user,
                    password=self.postgres_password,
                    connect_timeout=10
                )
                conn.close()
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Restore backups for AI Platform databases'
    )
    parser.add_argument(
        '--type',
        choices=['qdrant', 'neo4j', 'postgres', 'all'],
        default='all',
        help='Type of backup to restore'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available backups'
    )
    parser.add_argument(
        '--backup-id',
        type=str,
        help='Specific backup ID to restore (uses latest if not specified)'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate current state, do not restore'
    )
    
    args = parser.parse_args()
    
    restore_service = RestoreService()
    
    # List backups
    if args.list:
        logger.info("=" * 80)
        logger.info("Available Backups")
        logger.info("=" * 80)
        
        backup_types = ['qdrant', 'neo4j', 'postgres'] if args.type == 'all' else [args.type]
        
        for btype in backup_types:
            backups = restore_service.list_available_backups(btype)
            logger.info(f"\n{btype.upper()} Backups:")
            
            if not backups:
                logger.info("  No backups found")
                continue
            
            for backup in backups[:10]:  # Show latest 10
                size_mb = backup['size'] / (1024 * 1024)
                logger.info(
                    f"  {backup['backup_id']}: "
                    f"{backup['last_modified'].strftime('%Y-%m-%d %H:%M:%S')} "
                    f"({size_mb:.2f} MB)"
                )
        
        return 0
    
    # Validate only
    if args.validate_only:
        logger.info("=" * 80)
        logger.info("Validating Current State")
        logger.info("=" * 80)
        
        backup_types = ['qdrant', 'neo4j', 'postgres'] if args.type == 'all' else [args.type]
        
        all_valid = True
        for btype in backup_types:
            is_valid = restore_service.validate_restore(btype)
            status = "✓ VALID" if is_valid else "✗ INVALID"
            logger.info(f"{btype.upper()}: {status}")
            all_valid = all_valid and is_valid
        
        return 0 if all_valid else 1
    
    # Restore backups
    logger.info("=" * 80)
    logger.info("Starting Restore Process")
    logger.info("=" * 80)
    logger.warning("This will overwrite existing data. Press Ctrl+C within 5 seconds to cancel...")
    
    import time
    time.sleep(5)
    
    backup_types = ['qdrant', 'neo4j', 'postgres'] if args.type == 'all' else [args.type]
    
    for btype in backup_types:
        # Find backup to restore
        backups = restore_service.list_available_backups(btype)
        
        if not backups:
            logger.error(f"No {btype} backups found")
            continue
        
        # Use specified backup or latest
        if args.backup_id:
            backup = next((b for b in backups if args.backup_id in b['backup_id']), None)
            if not backup:
                logger.error(f"Backup {args.backup_id} not found for {btype}")
                continue
        else:
            backup = backups[0]  # Latest
        
        logger.info(f"\nRestoring {btype} from {backup['backup_id']}...")
        
        # Execute restore
        success = False
        if btype == 'qdrant':
            success = restore_service.restore_qdrant(backup['key'])
        elif btype == 'neo4j':
            success = restore_service.restore_neo4j(backup['key'])
        elif btype == 'postgres':
            success = restore_service.restore_postgresql(backup['key'])
        
        # Validate
        if success:
            logger.info(f"Validating {btype} restore...")
            is_valid = restore_service.validate_restore(btype)
            if is_valid:
                logger.info(f"✓ {btype.upper()} restore successful and validated")
            else:
                logger.error(f"✗ {btype.upper()} restore completed but validation failed")
        else:
            logger.error(f"✗ {btype.upper()} restore failed")
    
    logger.info("=" * 80)
    logger.info("Restore Process Complete")
    logger.info("=" * 80)


if __name__ == '__main__':
    sys.exit(main())
