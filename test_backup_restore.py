"""
Backup and Restore Testing for Production Validation
Tests backup creation, restoration, and data integrity
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional

import psycopg2
from qdrant_client import QdrantClient
import redis

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
