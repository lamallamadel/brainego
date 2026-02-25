"""
Production Validation Orchestrator
Coordinates all validation tests: load testing, chaos engineering, security audit, backup/restore

Run: python run_production_validation.py --full
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProductionValidator:
    """Orchestrate production validation tests"""

    def __init__(self, skip_tests: List[str] = None):
        self.skip_tests = skip_tests or []
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {},
            'overall_status': 'pending',
        }

    def run_command(self, cmd: List[str], timeout: int = 3600) -> Dict:
        """Run a command and capture results"""
        logger.info(f'Running: {" ".join(cmd)}')
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            logger.error(f'Command timeout after {timeout}s')
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': 'Timeout',
                'success': False,
            }
        except Exception as e:
            logger.error(f'Command failed: {e}')
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'success': False,
            }

    def run_locust_load_test(self) -> bool:
        """Run Locust load testing"""
        if 'locust' in self.skip_tests:
            logger.info('Skipping Locust load test')
            return True

        logger.info('=' * 60)
        logger.info('Running Locust Load Test')
        logger.info('=' * 60)

        result = self.run_command([
            'locust',
            '-f', 'locust_load_test.py',
            '--host=http://localhost:8000',
            '--users=50',
            '--spawn-rate=5',
            '--run-time=10m',
            '--headless',
            '--html=locust_report.html',
        ], timeout=900)

        self.results['tests']['locust_load_test'] = {
            'status': 'passed' if result['success'] else 'failed',
            'output': result['stdout'][-1000:],  # Last 1000 chars
        }

        if result['success']:
            logger.info('✓ Locust load test completed')
            
            # Check results file
            try:
                with open('locust_results.json', 'r') as f:
                    locust_results = json.load(f)
                    
                slo_pass = locust_results.get('slo_pass', False)
                if slo_pass:
                    logger.info('✓ SLO targets met')
                else:
                    logger.warning('⚠ SLO targets not met')
                    
                self.results['tests']['locust_load_test']['slo_pass'] = slo_pass
                self.results['tests']['locust_load_test']['metrics'] = locust_results
                
            except Exception as e:
                logger.warning(f'Could not read Locust results: {e}')
                
            return True
        else:
            logger.error(f'✗ Locust load test failed: {result["stderr"]}')
            return False

    def run_k6_load_test(self) -> bool:
        """Run k6 load testing"""
        if 'k6' in self.skip_tests:
            logger.info('Skipping k6 load test')
            return True

        logger.info('=' * 60)
        logger.info('Running k6 Load Test')
        logger.info('=' * 60)

        # Check if k6 is installed
        check = self.run_command(['k6', 'version'], timeout=5)
        if not check['success']:
            logger.warning('k6 not installed, skipping k6 tests')
            logger.warning('Install from: https://k6.io/docs/getting-started/installation/')
            return True

        result = self.run_command([
            'k6', 'run',
            '--vus=50',
            '--duration=10m',
            'k6_load_test.js',
        ], timeout=900)

        self.results['tests']['k6_load_test'] = {
            'status': 'passed' if result['success'] else 'failed',
            'output': result['stdout'][-1000:],
        }

        if result['success']:
            logger.info('✓ k6 load test completed')
            
            # Check results file
            try:
                with open('k6_results.json', 'r') as f:
                    k6_results = json.load(f)
                self.results['tests']['k6_load_test']['metrics'] = k6_results
            except Exception as e:
                logger.warning(f'Could not read k6 results: {e}')
                
            return True
        else:
            logger.error(f'✗ k6 load test failed: {result["stderr"]}')
            return False

    def run_chaos_engineering(self) -> bool:
        """Run chaos engineering tests"""
        if 'chaos' in self.skip_tests:
            logger.info('Skipping chaos engineering')
            return True

        logger.info('=' * 60)
        logger.info('Running Chaos Engineering Tests')
        logger.info('=' * 60)

        result = self.run_command([
            'python', 'chaos_engineering.py',
        ], timeout=1800)

        self.results['tests']['chaos_engineering'] = {
            'status': 'passed' if result['success'] else 'failed',
            'output': result['stdout'][-1000:],
        }

        if result['success']:
            logger.info('✓ Chaos engineering tests completed')
            
            # Check results file
            try:
                with open('chaos_report.json', 'r') as f:
                    chaos_results = json.load(f)
                self.results['tests']['chaos_engineering']['report'] = chaos_results
                
                resilience_score = chaos_results.get('resilience_score', 0)
                if resilience_score >= 90:
                    logger.info(f'✓ Excellent resilience score: {resilience_score}%')
                else:
                    logger.warning(f'⚠ Resilience score needs improvement: {resilience_score}%')
            except Exception as e:
                logger.warning(f'Could not read chaos report: {e}')
                
            return True
        else:
            logger.error(f'✗ Chaos engineering failed: {result["stderr"]}')
            return False

    def run_security_audit(self) -> bool:
        """Run security audit"""
        if 'security' in self.skip_tests:
            logger.info('Skipping security audit')
            return True

        logger.info('=' * 60)
        logger.info('Running Security Audit')
        logger.info('=' * 60)

        result = self.run_command([
            'python', 'security_audit.py',
        ], timeout=1800)

        self.results['tests']['security_audit'] = {
            'status': 'passed' if result['success'] else 'failed',
            'output': result['stdout'][-1000:],
        }

        if result['success']:
            logger.info('✓ Security audit completed')
            
            # Check results file
            try:
                with open('security_audit_report.json', 'r') as f:
                    security_results = json.load(f)
                self.results['tests']['security_audit']['report'] = security_results
                
                security_score = security_results.get('security_score', 0)
                vulns = security_results.get('vulnerabilities_found', 0)
                
                if security_score >= 95:
                    logger.info(f'✓ Excellent security score: {security_score}%')
                else:
                    logger.warning(f'⚠ Security score: {security_score}% ({vulns} vulnerabilities)')
            except Exception as e:
                logger.warning(f'Could not read security report: {e}')
                
            return True
        else:
            logger.error(f'✗ Security audit failed: {result["stderr"]}')
            return False

    def run_backup_restore_test(self) -> bool:
        """Run backup and restore testing"""
        if 'backup' in self.skip_tests:
            logger.info('Skipping backup/restore test')
            return True

        logger.info('=' * 60)
        logger.info('Running Backup/Restore Tests')
        logger.info('=' * 60)

        result = self.run_command([
            'python', 'test_backup_restore.py',
        ], timeout=900)

        self.results['tests']['backup_restore'] = {
            'status': 'passed' if result['success'] else 'failed',
            'output': result['stdout'][-1000:],
        }

        if result['success']:
            logger.info('✓ Backup/restore tests completed')
            
            # Check results file
            try:
                with open('backup_restore_report.json', 'r') as f:
                    backup_results = json.load(f)
                self.results['tests']['backup_restore']['report'] = backup_results
                
                success_rate = backup_results.get('success_rate', 0)
                if success_rate == 100:
                    logger.info('✓ All backup/restore tests passed')
                else:
                    logger.warning(f'⚠ Backup/restore success rate: {success_rate}%')
            except Exception as e:
                logger.warning(f'Could not read backup report: {e}')
                
            return True
        else:
            logger.error(f'✗ Backup/restore tests failed: {result["stderr"]}')
            return False

    def check_slo_compliance(self) -> Dict:
        """Check overall SLO compliance"""
        logger.info('\n' + '=' * 60)
        logger.info('SLO Compliance Check')
        logger.info('=' * 60)

        compliance = {
            'availability': {'target': 99.5, 'met': False, 'actual': 0},
            'p99_latency': {'target': 2000, 'met': False, 'actual': 0},
            'data_loss': {'target': 0, 'met': False, 'actual': 0},
        }

        # Check Locust results
        locust_test = self.results['tests'].get('locust_load_test', {})
        if 'metrics' in locust_test:
            metrics = locust_test['metrics']
            availability = metrics.get('availability', 0)
            p99 = metrics.get('latencies', {}).get('p99', 0)
            
            compliance['availability']['actual'] = availability
            compliance['availability']['met'] = availability >= 99.5
            
            compliance['p99_latency']['actual'] = p99
            compliance['p99_latency']['met'] = p99 < 2000

        # Check backup/restore results
        backup_test = self.results['tests'].get('backup_restore', {})
        if 'report' in backup_test:
            report = backup_test['report']
            data_loss_test = next(
                (r for r in report.get('test_results', []) if r.get('test') == 'data_loss'),
                None
            )
            if data_loss_test:
                compliance['data_loss']['met'] = data_loss_test.get('status') == 'passed'

        # Log results
        logger.info('\nSLO Compliance:')
        for metric, data in compliance.items():
            status = '✓' if data['met'] else '✗'
            logger.info(f"  {status} {metric}: Target={data['target']}, Actual={data['actual']}")

        all_met = all(data['met'] for data in compliance.values())
        
        if all_met:
            logger.info('\n✓ ALL SLOs MET')
        else:
            logger.warning('\n⚠ SOME SLOs NOT MET')

        return compliance

    def generate_final_report(self):
        """Generate final validation report"""
        logger.info('\n' + '=' * 60)
        logger.info('Production Validation Report')
        logger.info('=' * 60)

        total_tests = len(self.results['tests'])
        passed_tests = sum(
            1 for test in self.results['tests'].values()
            if test['status'] == 'passed'
        )

        logger.info(f'\nTests Run: {total_tests}')
        logger.info(f'Passed: {passed_tests}')
        logger.info(f'Failed: {total_tests - passed_tests}')

        logger.info('\nTest Summary:')
        for test_name, test_data in self.results['tests'].items():
            status = test_data['status']
            symbol = '✓' if status == 'passed' else '✗'
            logger.info(f'  {symbol} {test_name}: {status.upper()}')

        # SLO compliance
        compliance = self.check_slo_compliance()
        self.results['slo_compliance'] = compliance

        # Overall status
        all_passed = passed_tests == total_tests
        all_slos_met = all(data['met'] for data in compliance.values())

        if all_passed and all_slos_met:
            self.results['overall_status'] = 'PASSED'
            logger.info('\n' + '=' * 60)
            logger.info('✓ PRODUCTION VALIDATION PASSED')
            logger.info('=' * 60)
        else:
            self.results['overall_status'] = 'FAILED'
            logger.error('\n' + '=' * 60)
            logger.error('✗ PRODUCTION VALIDATION FAILED')
            logger.error('=' * 60)

        # Save report
        with open('production_validation_report.json', 'w') as f:
            json.dump(self.results, f, indent=2)

        logger.info('\nDetailed report saved to production_validation_report.json')

    def run_validation(self):
        """Run complete production validation"""
        logger.info('=' * 60)
        logger.info('Starting Production Validation')
        logger.info('=' * 60)
        logger.info(f'Timestamp: {self.results["timestamp"]}')
        logger.info(f'Skip tests: {self.skip_tests or "none"}')

        start_time = time.time()

        # Run all validation tests
        self.run_locust_load_test()
        time.sleep(5)

        self.run_k6_load_test()
        time.sleep(5)

        self.run_chaos_engineering()
        time.sleep(10)

        self.run_security_audit()
        time.sleep(5)

        self.run_backup_restore_test()

        # Generate final report
        duration = time.time() - start_time
        self.results['duration_seconds'] = duration

        logger.info(f'\nTotal validation time: {duration:.1f}s ({duration/60:.1f} minutes)')

        self.generate_final_report()

        # Return exit code based on overall status
        return 0 if self.results['overall_status'] == 'PASSED' else 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Production Validation Orchestrator')
    parser.add_argument(
        '--full',
        action='store_true',
        help='Run full validation suite'
    )
    parser.add_argument(
        '--skip',
        nargs='+',
        choices=['locust', 'k6', 'chaos', 'security', 'backup'],
        help='Skip specific tests'
    )
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Run quick validation (skip chaos and k6)'
    )

    args = parser.parse_args()

    skip_tests = args.skip or []
    if args.quick:
        skip_tests.extend(['chaos', 'k6'])

    validator = ProductionValidator(skip_tests=skip_tests)
    exit_code = validator.run_validation()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
