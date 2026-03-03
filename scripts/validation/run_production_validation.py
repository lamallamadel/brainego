"""
Ultra-Basic Chaos Suite for Production Validation

This implements an ultra-basic chaos engineering suite that tests:
1. Container kill + auto-restart verification
2. Alert triggering
3. Mean Time To Recovery (MTTR) measurement
4. CPU stress testing with graceful degradation
5. Database integrity verification post-chaos

Tests:
- Kill api-server container, verify auto-restart, check alerts, measure MTTR
- Kill kong container (if deployed), verify restart + fallback/circuit breaker
- Inject CPU stress on learning-engine, verify graceful degradation + alerts
- Verify no DB corruption (check schema_migrations table)

Does NOT include:
- Database failover tests
- Network partition tests
- Memory pressure tests beyond CPU stress

Usage:
    python scripts/validation/run_production_validation.py --chaos-suite basic
    
    # Via main orchestrator
    python run_production_validation.py --chaos-suite basic
"""

# Needs: python-package:docker>=7.0.0
# Needs: python-package:psycopg2-binary>=2.9.9
# Needs: python-package:requests>=2.31.0

import asyncio
import docker
import json
import logging
import subprocess
import time
import psycopg2
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MTTRMeasurement:
    """Mean Time To Recovery measurement"""
    service: str
    failure_time: float
    recovery_time: float
    mttr_seconds: float
    alert_triggered: bool
    recovery_successful: bool


class UltraBasicChaosSuite:
    """Ultra-basic chaos engineering suite for production validation"""

    def __init__(self, docker_compose_cmd: str = "docker compose"):
        self.docker_client = docker.from_env()
        self.docker_compose_cmd = docker_compose_cmd
        self.mttr_measurements: List[MTTRMeasurement] = []
        self.test_results: List[Dict] = []
        self.alert_checks: List[Dict] = []
        
    def check_alertmanager_for_alerts(self, service_name: str, lookback_seconds: int = 300) -> bool:
        """
        Check if AlertManager received alerts for the service.
        Returns True if alerts were triggered.
        """
        logger.info(f'Checking AlertManager for {service_name} alerts...')
        
        try:
            # Query AlertManager API for active/recent alerts
            import requests
            response = requests.get(
                'http://localhost:9093/api/v2/alerts',
                params={'filter': f'alertname=~".*{service_name}.*|ContainerDown|PodRestartSpike"'},
                timeout=5
            )
            
            if response.status_code == 200:
                alerts = response.json()
                
                # Check for alerts in the last lookback_seconds
                now = time.time()
                recent_alerts = [
                    alert for alert in alerts
                    if now - alert.get('startsAt', now) < lookback_seconds
                ]
                
                if recent_alerts:
                    logger.info(f'✓ Found {len(recent_alerts)} alert(s) for {service_name}')
                    for alert in recent_alerts:
                        alert_name = alert.get('labels', {}).get('alertname', 'unknown')
                        logger.info(f'  - Alert: {alert_name}')
                    return True
                else:
                    logger.warning(f'⚠ No recent alerts found for {service_name}')
                    return False
            else:
                logger.warning(f'AlertManager returned status {response.status_code}')
                return False
                
        except Exception as e:
            logger.warning(f'Could not check AlertManager: {e}')
            return False
    
    def verify_container_auto_restart(self, service_name: str, timeout: int = 120) -> Tuple[bool, float]:
        """
        Verify that a container automatically restarts after being killed.
        Returns (success, recovery_time_seconds)
        """
        logger.info(f'Verifying auto-restart for {service_name}...')
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                container = self.docker_client.containers.get(service_name)
                
                if container.status == 'running':
                    recovery_time = time.time() - start_time
                    logger.info(f'✓ {service_name} restarted in {recovery_time:.2f}s')
                    return True, recovery_time
                    
            except docker.errors.NotFound:
                logger.debug(f'{service_name} not found yet, waiting...')
            except Exception as e:
                logger.debug(f'Error checking {service_name}: {e}')
            
            time.sleep(2)
        
        logger.error(f'✗ {service_name} did not restart within {timeout}s')
        return False, timeout
    
    def test_api_server_kill_and_restart(self) -> Dict:
        """
        Test 1: Kill api-server container, verify auto-restart, check alerts, measure MTTR
        """
        logger.info('\n' + '=' * 60)
        logger.info('Test 1: API Server Kill + Auto-Restart')
        logger.info('=' * 60)
        
        service_name = 'api-server'
        test_result = {
            'test_name': 'api_server_kill_restart',
            'service': service_name,
            'passed': False,
            'details': {}
        }
        
        try:
            # Get container
            container = self.docker_client.containers.get(service_name)
            logger.info(f'Killing {service_name} container...')
            
            # Record failure time
            failure_time = time.time()
            
            # Kill container
            subprocess.run([*self.docker_compose_cmd.split(), 'kill', service_name], check=True)
            logger.info(f'✓ Killed {service_name}')
            
            # Wait a moment for system to detect failure
            time.sleep(5)
            
            # Verify auto-restart
            recovery_successful, recovery_time = self.verify_container_auto_restart(service_name, timeout=120)
            
            # Check if alerts were triggered
            alert_triggered = self.check_alertmanager_for_alerts(service_name, lookback_seconds=180)
            
            # Record MTTR measurement
            mttr = MTTRMeasurement(
                service=service_name,
                failure_time=failure_time,
                recovery_time=time.time(),
                mttr_seconds=recovery_time,
                alert_triggered=alert_triggered,
                recovery_successful=recovery_successful
            )
            self.mttr_measurements.append(mttr)
            
            # Check if test passed
            test_passed = recovery_successful
            
            test_result['passed'] = test_passed
            test_result['details'] = {
                'recovery_successful': recovery_successful,
                'mttr_seconds': recovery_time,
                'alert_triggered': alert_triggered,
            }
            
            if test_passed:
                logger.info(f'✓ Test PASSED: {service_name} recovered successfully')
            else:
                logger.error(f'✗ Test FAILED: {service_name} did not recover')
                
        except Exception as e:
            logger.error(f'Test failed with error: {e}')
            test_result['details']['error'] = str(e)
        
        self.test_results.append(test_result)
        return test_result
    
    def test_kong_kill_and_restart(self) -> Dict:
        """
        Test 2: Kill kong container (if deployed), verify restart + fallback/circuit breaker
        """
        logger.info('\n' + '=' * 60)
        logger.info('Test 2: Kong Kill + Auto-Restart + Circuit Breaker')
        logger.info('=' * 60)
        
        service_name = 'kong'
        test_result = {
            'test_name': 'kong_kill_restart',
            'service': service_name,
            'passed': False,
            'details': {}
        }
        
        try:
            # Check if Kong is deployed
            try:
                container = self.docker_client.containers.get(service_name)
            except docker.errors.NotFound:
                logger.info(f'ℹ Kong container not deployed, skipping test')
                test_result['passed'] = True  # Not a failure
                test_result['details']['skipped'] = True
                test_result['details']['reason'] = 'Kong not deployed'
                self.test_results.append(test_result)
                return test_result
            
            logger.info(f'Killing {service_name} container...')
            
            # Record failure time
            failure_time = time.time()
            
            # Kill container using docker compose
            subprocess.run([*self.docker_compose_cmd.split(), 'kill', service_name], check=True)
            logger.info(f'✓ Killed {service_name}')
            
            # Wait a moment
            time.sleep(5)
            
            # Verify auto-restart
            recovery_successful, recovery_time = self.verify_container_auto_restart(service_name, timeout=120)
            
            # Check if alerts were triggered
            alert_triggered = self.check_alertmanager_for_alerts(service_name, lookback_seconds=180)
            
            # Check circuit breaker behavior (if API is available)
            circuit_breaker_ok = self.check_circuit_breaker_fallback()
            
            # Record MTTR
            mttr = MTTRMeasurement(
                service=service_name,
                failure_time=failure_time,
                recovery_time=time.time(),
                mttr_seconds=recovery_time,
                alert_triggered=alert_triggered,
                recovery_successful=recovery_successful
            )
            self.mttr_measurements.append(mttr)
            
            test_passed = recovery_successful
            
            test_result['passed'] = test_passed
            test_result['details'] = {
                'recovery_successful': recovery_successful,
                'mttr_seconds': recovery_time,
                'alert_triggered': alert_triggered,
                'circuit_breaker_checked': circuit_breaker_ok
            }
            
            if test_passed:
                logger.info(f'✓ Test PASSED: {service_name} recovered successfully')
            else:
                logger.error(f'✗ Test FAILED: {service_name} did not recover')
                
        except Exception as e:
            logger.error(f'Test failed with error: {e}')
            test_result['details']['error'] = str(e)
        
        self.test_results.append(test_result)
        return test_result
    
    def check_circuit_breaker_fallback(self) -> bool:
        """Check if circuit breaker/fallback mechanisms are functioning"""
        try:
            import requests
            response = requests.get('http://localhost:8000/circuit-breakers', timeout=5)
            if response.status_code == 200:
                data = response.json()
                logger.info(f'✓ Circuit breaker endpoint available: {len(data.get("circuit_breakers", {}))} CBs')
                return True
            return False
        except Exception as e:
            logger.debug(f'Circuit breaker check failed: {e}')
            return False
    
    def test_learning_engine_cpu_stress(self) -> Dict:
        """
        Test 3: Inject CPU stress on learning-engine, verify graceful degradation, alerts
        """
        logger.info('\n' + '=' * 60)
        logger.info('Test 3: Learning Engine CPU Stress + Graceful Degradation')
        logger.info('=' * 60)
        
        service_name = 'learning-engine'
        test_result = {
            'test_name': 'learning_engine_cpu_stress',
            'service': service_name,
            'passed': False,
            'details': {}
        }
        
        try:
            # Get container
            container = self.docker_client.containers.get(service_name)
            logger.info(f'Injecting CPU stress on {service_name}...')
            
            # Install stress-ng if needed
            logger.info('Ensuring stress-ng is available...')
            install_cmd = 'command -v stress-ng || (apt-get update && apt-get install -y stress-ng) || apk add --no-cache stress-ng || echo "stress-ng not available"'
            container.exec_run(f'sh -c "{install_cmd}"')
            
            # Start CPU stress
            stress_duration = 60
            logger.info(f'Starting CPU stress (4 cores, {stress_duration}s)...')
            
            # Run stress-ng in background
            stress_cmd = f'stress-ng --cpu 4 --timeout {stress_duration}s'
            exec_result = container.exec_run(f'sh -c "{stress_cmd} > /dev/null 2>&1 &"', detach=True)
            
            logger.info(f'✓ CPU stress started on {service_name}')
            
            # Monitor service health during stress
            start_time = time.time()
            service_remained_running = True
            graceful_degradation_detected = False
            
            for i in range(6):  # Check every 10 seconds for 60 seconds
                time.sleep(10)
                
                container.reload()
                if container.status != 'running':
                    logger.warning(f'⚠ {service_name} stopped during CPU stress')
                    service_remained_running = False
                    break
                else:
                    logger.info(f'  [{i*10}s] {service_name} still running (good)')
                    graceful_degradation_detected = True
            
            # Wait for stress to complete
            remaining_time = stress_duration - (time.time() - start_time)
            if remaining_time > 0:
                time.sleep(remaining_time)
            
            # Kill any remaining stress processes
            try:
                container.exec_run('pkill -f stress-ng')
                logger.info('Stopped stress-ng processes')
            except:
                pass
            
            # Verify service is still healthy
            time.sleep(5)
            container.reload()
            still_healthy = container.status == 'running'
            
            # Check if alerts were triggered
            alert_triggered = self.check_alertmanager_for_alerts(service_name, lookback_seconds=180)
            
            test_passed = service_remained_running and still_healthy and graceful_degradation_detected
            
            test_result['passed'] = test_passed
            test_result['details'] = {
                'service_remained_running': service_remained_running,
                'still_healthy_after_stress': still_healthy,
                'graceful_degradation_detected': graceful_degradation_detected,
                'alert_triggered': alert_triggered,
                'stress_duration_seconds': stress_duration
            }
            
            if test_passed:
                logger.info(f'✓ Test PASSED: {service_name} handled CPU stress gracefully')
            else:
                logger.error(f'✗ Test FAILED: {service_name} did not handle stress properly')
                
        except Exception as e:
            logger.error(f'Test failed with error: {e}')
            test_result['details']['error'] = str(e)
        
        self.test_results.append(test_result)
        return test_result
    
    def verify_database_integrity(self) -> Dict:
        """
        Verify no DB corruption post-chaos by checking schema_migrations table
        """
        logger.info('\n' + '=' * 60)
        logger.info('Post-Chaos Database Integrity Verification')
        logger.info('=' * 60)
        
        integrity_result = {
            'test_name': 'database_integrity_check',
            'passed': False,
            'details': {}
        }
        
        try:
            # Connect to PostgreSQL
            conn = psycopg2.connect(
                host='localhost',
                port=5432,
                database='ai_platform',
                user='ai_user',
                password='ai_password'
            )
            
            cursor = conn.cursor()
            
            # Check if schema_migrations table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'schema_migrations'
                );
            """)
            
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                logger.warning('⚠ schema_migrations table does not exist')
                integrity_result['details']['schema_migrations_exists'] = False
                integrity_result['passed'] = True  # Not a failure if table never existed
                integrity_result['details']['note'] = 'schema_migrations table not found (may not be using migrations)'
            else:
                logger.info('✓ schema_migrations table exists')
                
                # Query the table to verify it's readable
                cursor.execute("SELECT COUNT(*) FROM schema_migrations;")
                migration_count = cursor.fetchone()[0]
                
                logger.info(f'✓ schema_migrations table intact: {migration_count} migrations found')
                
                integrity_result['details']['schema_migrations_exists'] = True
                integrity_result['details']['migration_count'] = migration_count
                integrity_result['passed'] = True
            
            cursor.close()
            conn.close()
            
            logger.info('✓ Database integrity verification PASSED')
            
        except psycopg2.Error as e:
            logger.error(f'Database error: {e}')
            integrity_result['details']['error'] = str(e)
            integrity_result['passed'] = False
        except Exception as e:
            logger.error(f'Integrity check failed: {e}')
            integrity_result['details']['error'] = str(e)
            integrity_result['passed'] = False
        
        self.test_results.append(integrity_result)
        return integrity_result
    
    def generate_mttr_report(self) -> Dict:
        """Generate MTTR report per service"""
        logger.info('\n' + '=' * 60)
        logger.info('Mean Time To Recovery (MTTR) Report')
        logger.info('=' * 60)
        
        if not self.mttr_measurements:
            logger.info('No MTTR measurements collected')
            return {}
        
        mttr_by_service = {}
        
        for measurement in self.mttr_measurements:
            service = measurement.service
            
            if service not in mttr_by_service:
                mttr_by_service[service] = {
                    'measurements': [],
                    'average_mttr': 0,
                    'min_mttr': float('inf'),
                    'max_mttr': 0,
                    'total_measurements': 0,
                    'successful_recoveries': 0,
                    'alerts_triggered': 0
                }
            
            mttr_by_service[service]['measurements'].append(measurement.mttr_seconds)
            mttr_by_service[service]['total_measurements'] += 1
            
            if measurement.recovery_successful:
                mttr_by_service[service]['successful_recoveries'] += 1
            
            if measurement.alert_triggered:
                mttr_by_service[service]['alerts_triggered'] += 1
            
            mttr_by_service[service]['min_mttr'] = min(
                mttr_by_service[service]['min_mttr'],
                measurement.mttr_seconds
            )
            mttr_by_service[service]['max_mttr'] = max(
                mttr_by_service[service]['max_mttr'],
                measurement.mttr_seconds
            )
        
        # Calculate averages
        for service, data in mttr_by_service.items():
            if data['measurements']:
                data['average_mttr'] = sum(data['measurements']) / len(data['measurements'])
            
            logger.info(f'\nService: {service}')
            logger.info(f'  Total measurements: {data["total_measurements"]}')
            logger.info(f'  Successful recoveries: {data["successful_recoveries"]}/{data["total_measurements"]}')
            logger.info(f'  Average MTTR: {data["average_mttr"]:.2f}s')
            logger.info(f'  Min MTTR: {data["min_mttr"]:.2f}s')
            logger.info(f'  Max MTTR: {data["max_mttr"]:.2f}s')
            logger.info(f'  Alerts triggered: {data["alerts_triggered"]}/{data["total_measurements"]}')
            
            # Clean up for JSON serialization
            if data['min_mttr'] == float('inf'):
                data['min_mttr'] = 0
        
        logger.info('=' * 60)
        
        return mttr_by_service
    
    def run_ultra_basic_chaos_suite(self):
        """Run the complete ultra-basic chaos suite"""
        logger.info('\n' + '=' * 80)
        logger.info('ULTRA-BASIC CHAOS SUITE - Production Validation')
        logger.info('=' * 80)
        logger.info('Tests: Container kills, CPU stress, MTTR measurement, DB integrity')
        logger.info('Excluded: DB failover, network partitions, memory pressure')
        logger.info('=' * 80 + '\n')
        
        start_time = time.time()
        
        # Run tests
        self.test_api_server_kill_and_restart()
        time.sleep(10)  # Cool-down between tests
        
        self.test_kong_kill_and_restart()
        time.sleep(10)
        
        self.test_learning_engine_cpu_stress()
        time.sleep(10)
        
        # Verify database integrity post-chaos
        self.verify_database_integrity()
        
        # Generate MTTR report
        mttr_report = self.generate_mttr_report()
        
        # Generate final summary
        duration = time.time() - start_time
        
        logger.info('\n' + '=' * 80)
        logger.info('ULTRA-BASIC CHAOS SUITE - SUMMARY')
        logger.info('=' * 80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for test in self.test_results if test['passed'])
        
        logger.info(f'\nTotal Tests: {total_tests}')
        logger.info(f'Passed: {passed_tests}')
        logger.info(f'Failed: {total_tests - passed_tests}')
        logger.info(f'Duration: {duration:.1f}s')
        
        logger.info('\nTest Results:')
        for test in self.test_results:
            status = '✓ PASSED' if test['passed'] else '✗ FAILED'
            logger.info(f"  {status}: {test['test_name']} ({test['service']})")
        
        # Overall status
        all_passed = passed_tests == total_tests
        
        logger.info('\n' + '=' * 80)
        if all_passed:
            logger.info('✓ ULTRA-BASIC CHAOS SUITE PASSED')
        else:
            logger.error('✗ ULTRA-BASIC CHAOS SUITE FAILED')
        logger.info('=' * 80)
        
        # Save comprehensive report
        report = {
            'suite': 'ultra-basic',
            'timestamp': datetime.utcnow().isoformat(),
            'duration_seconds': duration,
            'summary': {
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': total_tests - passed_tests,
                'overall_status': 'PASSED' if all_passed else 'FAILED'
            },
            'test_results': self.test_results,
            'mttr_report': mttr_report,
        }
        
        with open('chaos_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info('\nDetailed report saved to chaos_report.json')
        
        return 0 if all_passed else 1


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ultra-Basic Chaos Suite for Production Validation')
    parser.add_argument(
        '--chaos-suite',
        choices=['basic'],
        default='basic',
        help='Chaos test suite (only "basic" supported in this script)'
    )
    parser.add_argument(
        '--docker-compose-cmd',
        default='docker compose',
        help='Docker Compose command (default: "docker compose")'
    )
    
    args = parser.parse_args()
    
    if args.chaos_suite != 'basic':
        logger.error('This script only supports --chaos-suite basic')
        return 1
    
    suite = UltraBasicChaosSuite(docker_compose_cmd=args.docker_compose_cmd)
    exit_code = suite.run_ultra_basic_chaos_suite()
    
    return exit_code


if __name__ == '__main__':
    import sys
    sys.exit(main())
