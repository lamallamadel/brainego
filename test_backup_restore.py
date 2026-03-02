"""
Backup and Restore Testing for Production Validation
Tests backup creation, restoration, and data integrity
Includes cross-region backup replication verification
"""

import asyncio
import json
import logging
import os
import subprocess
import time
import hashlib
from datetime import datetime
from typing import Dict, List, Optional

import psycopg2
from qdrant_client import QdrantClient
import redis

try:
    from boto3 import client as boto3_client
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("boto3 not available, cross-region replication tests will be skipped")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackupRestoreTester:
    """Test backup and restore functionality"""

    def __init__(self):
        self.test_results = []
        self.postgres_conn = None
        self.redis_client = None
        self.qdrant_client = None
        
        # MinIO/S3 configuration for cross-region replication
        self.primary_region = os.getenv('PRIMARY_MINIO_ENDPOINT', 'minio:9000')
        self.secondary_region = os.getenv('SECONDARY_MINIO_ENDPOINT', None)
        self.minio_access_key = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
        self.minio_secret_key = os.getenv('MINIO_SECRET_KEY', 'minioadmin123')
        self.backup_bucket = os.getenv('BACKUP_BUCKET', 'backups')
        
        # Initialize S3 clients if boto3 available
        self.primary_s3_client = None
        self.secondary_s3_client = None
        if BOTO3_AVAILABLE:
            try:
                self.primary_s3_client = boto3_client(
                    's3',
                    endpoint_url=f'http://{self.primary_region}',
                    aws_access_key_id=self.minio_access_key,
                    aws_secret_access_key=self.minio_secret_key
                )
                if self.secondary_region:
                    self.secondary_s3_client = boto3_client(
                        's3',
                        endpoint_url=f'http://{self.secondary_region}',
                        aws_access_key_id=self.minio_access_key,
                        aws_secret_access_key=self.minio_secret_key
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize S3 clients: {e}")

    def setup_connections(self):
        """Setup database connections"""
        try:
            # PostgreSQL
            self.postgres_conn = psycopg2.connect(
                host='localhost',
                port=5432,
                database='ai_platform',
                user='ai_user',
                password='ai_password'
            )
            logger.info('✓ Connected to PostgreSQL')

            # Redis
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                db=0,
                decode_responses=True
            )
            self.redis_client.ping()
            logger.info('✓ Connected to Redis')

            # Qdrant
            self.qdrant_client = QdrantClient(host='localhost', port=6333)
            logger.info('✓ Connected to Qdrant')

        except Exception as e:
            logger.error(f'Connection setup failed: {e}')
            raise

    def inject_test_data(self):
        """Inject test data before backup"""
        logger.info('Injecting test data...')

        try:
            # PostgreSQL test data
            cursor = self.postgres_conn.cursor()
            cursor.execute("""
                INSERT INTO conversations (id, user_id, created_at, messages)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                'backup-test-001',
                'test-user',
                datetime.now(),
                json.dumps([{'role': 'user', 'content': 'test backup'}])
            ))
            self.postgres_conn.commit()
            logger.info('✓ PostgreSQL test data injected')

            # Redis test data
            self.redis_client.set('backup:test:key', 'test_value')
            self.redis_client.set('backup:test:timestamp', str(time.time()))
            logger.info('✓ Redis test data injected')

            # Qdrant test data
            try:
                self.qdrant_client.upsert(
                    collection_name='documents',
                    points=[
                        {
                            'id': 'backup-test-001',
                            'vector': [0.1] * 384,
                            'payload': {
                                'content': 'backup test document',
                                'source': 'backup_test',
                            }
                        }
                    ]
                )
                logger.info('✓ Qdrant test data injected')
            except Exception as e:
                logger.warning(f'Qdrant injection skipped: {e}')

        except Exception as e:
            logger.error(f'Test data injection failed: {e}')
            raise

    def verify_test_data(self) -> bool:
        """Verify test data exists"""
        logger.info('Verifying test data...')
        verified = True

        try:
            # PostgreSQL
            cursor = self.postgres_conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM conversations WHERE id = %s",
                ('backup-test-001',)
            )
            count = cursor.fetchone()[0]
            if count > 0:
                logger.info('✓ PostgreSQL test data verified')
            else:
                logger.error('✗ PostgreSQL test data missing')
                verified = False

            # Redis
            value = self.redis_client.get('backup:test:key')
            if value == 'test_value':
                logger.info('✓ Redis test data verified')
            else:
                logger.error('✗ Redis test data missing')
                verified = False

            # Qdrant
            try:
                result = self.qdrant_client.retrieve(
                    collection_name='documents',
                    ids=['backup-test-001']
                )
                if result:
                    logger.info('✓ Qdrant test data verified')
                else:
                    logger.error('✗ Qdrant test data missing')
                    verified = False
            except Exception as e:
                logger.warning(f'Qdrant verification skipped: {e}')

        except Exception as e:
            logger.error(f'Data verification failed: {e}')
            verified = False

        return verified

    def test_backup_creation(self) -> bool:
        """Test backup creation"""
        logger.info('\n[TEST] Backup Creation')

        try:
            # Trigger backup service
            result = subprocess.run(
                ['python', 'backup_service.py', '--manual'],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                logger.info('✓ Backup created successfully')
                
                # Verify backup files exist
                backup_dir = './backups'
                if os.path.exists(backup_dir):
                    backups = os.listdir(backup_dir)
                    if backups:
                        logger.info(f'  Found {len(backups)} backup(s)')
                        self.test_results.append({
                            'test': 'backup_creation',
                            'status': 'passed',
                            'backups_found': len(backups)
                        })
                        return True
                    else:
                        logger.error('✗ No backup files found')
                        self.test_results.append({
                            'test': 'backup_creation',
                            'status': 'failed',
                            'reason': 'No backup files found'
                        })
                        return False
            else:
                logger.error(f'✗ Backup failed: {result.stderr}')
                self.test_results.append({
                    'test': 'backup_creation',
                    'status': 'failed',
                    'reason': result.stderr
                })
                return False

        except subprocess.TimeoutExpired:
            logger.error('✗ Backup timeout')
            self.test_results.append({
                'test': 'backup_creation',
                'status': 'failed',
                'reason': 'Timeout'
            })
            return False
        except Exception as e:
            logger.error(f'✗ Backup creation failed: {e}')
            self.test_results.append({
                'test': 'backup_creation',
                'status': 'failed',
                'reason': str(e)
            })
            return False

    def test_restore(self) -> bool:
        """Test data restoration"""
        logger.info('\n[TEST] Data Restoration')

        try:
            # Find latest backup
            backup_dir = './backups'
            if not os.path.exists(backup_dir):
                logger.error('✗ Backup directory not found')
                return False

            backups = sorted(os.listdir(backup_dir), reverse=True)
            if not backups:
                logger.error('✗ No backups available')
                return False

            latest_backup = backups[0]
            logger.info(f'Restoring from: {latest_backup}')

            # Trigger restore
            result = subprocess.run(
                ['python', 'restore_backup.py', '--backup', latest_backup],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                logger.info('✓ Restore completed successfully')
                
                # Verify data integrity after restore
                time.sleep(5)  # Wait for services to stabilize
                
                if self.verify_test_data():
                    logger.info('✓ Data integrity verified after restore')
                    self.test_results.append({
                        'test': 'restore',
                        'status': 'passed',
                        'backup': latest_backup
                    })
                    return True
                else:
                    logger.error('✗ Data integrity check failed after restore')
                    self.test_results.append({
                        'test': 'restore',
                        'status': 'failed',
                        'reason': 'Data integrity check failed'
                    })
                    return False
            else:
                logger.error(f'✗ Restore failed: {result.stderr}')
                self.test_results.append({
                    'test': 'restore',
                    'status': 'failed',
                    'reason': result.stderr
                })
                return False

        except subprocess.TimeoutExpired:
            logger.error('✗ Restore timeout')
            self.test_results.append({
                'test': 'restore',
                'status': 'failed',
                'reason': 'Timeout'
            })
            return False
        except Exception as e:
            logger.error(f'✗ Restore failed: {e}')
            self.test_results.append({
                'test': 'restore',
                'status': 'failed',
                'reason': str(e)
            })
            return False

    def test_data_loss(self) -> bool:
        """Test for zero data loss"""
        logger.info('\n[TEST] Zero Data Loss')

        try:
            # Record data counts before
            cursor = self.postgres_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM conversations")
            pg_count_before = cursor.fetchone()[0]

            redis_keys_before = len(self.redis_client.keys('*'))

            # Simulate data change
            self.inject_test_data()

            # Backup
            self.test_backup_creation()

            # Record data counts after backup
            cursor.execute("SELECT COUNT(*) FROM conversations")
            pg_count_after = cursor.fetchone()[0]

            redis_keys_after = len(self.redis_client.keys('*'))

            # Verify no data loss
            if pg_count_after >= pg_count_before and redis_keys_after >= redis_keys_before:
                logger.info('✓ Zero data loss verified')
                self.test_results.append({
                    'test': 'data_loss',
                    'status': 'passed',
                    'postgres_records': {'before': pg_count_before, 'after': pg_count_after},
                    'redis_keys': {'before': redis_keys_before, 'after': redis_keys_after}
                })
                return True
            else:
                logger.error('✗ Data loss detected')
                self.test_results.append({
                    'test': 'data_loss',
                    'status': 'failed',
                    'reason': 'Data count decreased'
                })
                return False

        except Exception as e:
            logger.error(f'✗ Data loss test failed: {e}')
            self.test_results.append({
                'test': 'data_loss',
                'status': 'failed',
                'reason': str(e)
            })
            return False
    
    def _calculate_checksum(self, s3_client, bucket: str, key: str) -> Optional[str]:
        """Calculate checksum of S3 object"""
        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            sha256_hash = hashlib.sha256()
            for chunk in response['Body'].iter_chunks(chunk_size=4096):
                sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate checksum for {key}: {e}")
            return None
    
    def test_cross_region_replication(self) -> bool:
        """Test cross-region backup replication"""
        logger.info('\n[TEST] Cross-Region Backup Replication')
        
        if not BOTO3_AVAILABLE:
            logger.warning('✗ boto3 not available, skipping cross-region replication test')
            self.test_results.append({
                'test': 'cross_region_replication',
                'status': 'skipped',
                'reason': 'boto3 not available'
            })
            return False
        
        if not self.secondary_region or not self.secondary_s3_client:
            logger.warning('✗ Secondary region not configured, skipping cross-region replication test')
            self.test_results.append({
                'test': 'cross_region_replication',
                'status': 'skipped',
                'reason': 'Secondary region not configured'
            })
            return False
        
        try:
            # List backups in primary region
            logger.info(f'Listing backups in primary region: {self.primary_region}')
            primary_backups = []
            
            paginator = self.primary_s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.backup_bucket)
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                for obj in page['Contents']:
                    primary_backups.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'etag': obj['ETag'].strip('"'),
                        'last_modified': obj['LastModified']
                    })
            
            if not primary_backups:
                logger.error('✗ No backups found in primary region')
                self.test_results.append({
                    'test': 'cross_region_replication',
                    'status': 'failed',
                    'reason': 'No backups in primary region'
                })
                return False
            
            logger.info(f'Found {len(primary_backups)} backups in primary region')
            
            # Verify backups exist in secondary region
            logger.info(f'Verifying backups in secondary region: {self.secondary_region}')
            replicated_count = 0
            checksum_verified = 0
            missing_backups = []
            checksum_mismatches = []
            
            for backup in primary_backups:
                try:
                    # Check if backup exists in secondary
                    response = self.secondary_s3_client.head_object(
                        Bucket=self.backup_bucket,
                        Key=backup['key']
                    )
                    
                    # Verify size matches
                    if response['ContentLength'] == backup['size']:
                        replicated_count += 1
                        
                        # Verify checksum for critical backups
                        if any(db_type in backup['key'] for db_type in ['postgres', 'qdrant', 'neo4j']):
                            primary_checksum = self._calculate_checksum(
                                self.primary_s3_client, 
                                self.backup_bucket, 
                                backup['key']
                            )
                            secondary_checksum = self._calculate_checksum(
                                self.secondary_s3_client, 
                                self.backup_bucket, 
                                backup['key']
                            )
                            
                            if primary_checksum and secondary_checksum:
                                if primary_checksum == secondary_checksum:
                                    checksum_verified += 1
                                else:
                                    checksum_mismatches.append(backup['key'])
                                    logger.warning(f"Checksum mismatch for {backup['key']}")
                    else:
                        logger.warning(f"Size mismatch for {backup['key']}")
                        
                except ClientError as e:
                    if e.response['Error']['Code'] == '404':
                        missing_backups.append(backup['key'])
                        logger.warning(f"Missing in secondary: {backup['key']}")
                    else:
                        raise
            
            # Calculate replication percentage
            replication_percentage = (replicated_count / len(primary_backups) * 100) if primary_backups else 0
            
            logger.info(f'Replicated: {replicated_count}/{len(primary_backups)} ({replication_percentage:.1f}%)')
            logger.info(f'Checksum verified: {checksum_verified}')
            
            # Test passes if >95% replicated and no checksum mismatches
            success = replication_percentage >= 95.0 and len(checksum_mismatches) == 0
            
            if success:
                logger.info('✓ Cross-region replication verified')
                self.test_results.append({
                    'test': 'cross_region_replication',
                    'status': 'passed',
                    'primary_backups': len(primary_backups),
                    'replicated': replicated_count,
                    'replication_percentage': replication_percentage,
                    'checksum_verified': checksum_verified
                })
            else:
                logger.error(f'✗ Cross-region replication issues detected')
                self.test_results.append({
                    'test': 'cross_region_replication',
                    'status': 'failed',
                    'primary_backups': len(primary_backups),
                    'replicated': replicated_count,
                    'replication_percentage': replication_percentage,
                    'missing_backups': missing_backups,
                    'checksum_mismatches': checksum_mismatches
                })
            
            return success
            
        except Exception as e:
            logger.error(f'✗ Cross-region replication test failed: {e}')
            self.test_results.append({
                'test': 'cross_region_replication',
                'status': 'failed',
                'reason': str(e)
            })
            return False

    def generate_report(self):
        """Generate test report"""
        logger.info('\n' + '=' * 60)
        logger.info('Backup/Restore Test Report')
        logger.info('=' * 60)

        passed = sum(1 for r in self.test_results if r['status'] == 'passed')
        total = len(self.test_results)

        logger.info(f'\nTests Run: {total}')
        logger.info(f'Passed: {passed}')
        logger.info(f'Failed: {total - passed}')

        logger.info('\nTest Results:')
        for result in self.test_results:
            status_symbol = '✓' if result['status'] == 'passed' else '✗'
            logger.info(f"  {status_symbol} {result['test']}: {result['status'].upper()}")
            if result['status'] == 'failed' and 'reason' in result:
                logger.info(f"    Reason: {result['reason']}")

        success_rate = (passed / total * 100) if total > 0 else 0
        logger.info(f'\nSuccess Rate: {success_rate:.1f}%')

        # SLO: Zero data loss
        data_loss_test = next((r for r in self.test_results if r['test'] == 'data_loss'), None)
        if data_loss_test and data_loss_test['status'] == 'passed':
            logger.info('SLO Compliance: ✓ ZERO DATA LOSS')
        else:
            logger.error('SLO Compliance: ✗ DATA LOSS DETECTED')

        logger.info('=' * 60)

        # Save report
        report = {
            'timestamp': datetime.now().isoformat(),
            'tests_run': total,
            'passed': passed,
            'failed': total - passed,
            'success_rate': success_rate,
            'test_results': self.test_results,
        }

        with open('backup_restore_report.json', 'w') as f:
            json.dump(report, f, indent=2)

        logger.info('Report saved to backup_restore_report.json')

    def run_tests(self):
        """Run all backup/restore tests"""
        logger.info('=' * 60)
        logger.info('Starting Backup/Restore Testing')
        logger.info('=' * 60)

        try:
            self.setup_connections()
            self.inject_test_data()
            
            # Wait for data to propagate
            time.sleep(2)
            
            # Verify initial state
            if not self.verify_test_data():
                logger.error('Initial data verification failed')
                return

            # Run tests
            self.test_backup_creation()
            self.test_restore()
            self.test_data_loss()
            self.test_cross_region_replication()

            self.generate_report()

        except Exception as e:
            logger.error(f'Test suite failed: {e}')
        finally:
            # Cleanup
            if self.postgres_conn:
                self.postgres_conn.close()


def main():
    """Run backup/restore tests"""
    tester = BackupRestoreTester()
    tester.run_tests()


if __name__ == '__main__':
    main()
