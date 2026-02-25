"""
Chaos Engineering for Production Validation
- Random pod kills
- CPU saturation
- Network partitions
- Memory pressure
"""

import asyncio
import docker
import logging
import random
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ChaosExperiment:
    """Chaos experiment configuration"""
    name: str
    description: str
    duration_seconds: int
    recovery_time_seconds: int


class ChaosEngineer:
    """Chaos engineering orchestrator"""

    def __init__(self):
        self.docker_client = docker.from_env()
        self.experiments_run = []
        self.failures_detected = []

    def get_running_containers(self) -> List[str]:
        """Get list of running containers"""
        containers = self.docker_client.containers.list()
        return [c.name for c in containers if 'ai-platform' in c.name or 'max-serve' in c.name]

    def check_service_health(self, service_name: str) -> bool:
        """Check if service is healthy"""
        try:
            container = self.docker_client.containers.get(service_name)
            return container.status == 'running'
        except docker.errors.NotFound:
            return False
        except Exception as e:
            logger.error(f'Error checking {service_name}: {e}')
            return False

    def wait_for_recovery(self, service_name: str, timeout: int = 120) -> bool:
        """Wait for service to recover"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_service_health(service_name):
                logger.info(f'{service_name} recovered')
                return True
            time.sleep(2)
        
        logger.error(f'{service_name} did not recover within {timeout}s')
        return False

    def random_pod_kill(self):
        """Kill a random container and verify recovery"""
        experiment = ChaosExperiment(
            name='Random Pod Kill',
            description='Randomly kill containers and verify automatic restart',
            duration_seconds=10,
            recovery_time_seconds=60,
        )
        
        logger.info(f'Starting: {experiment.name}')
        
        # Get non-critical containers (avoid databases)
        all_containers = self.get_running_containers()
        killable_containers = [
            c for c in all_containers
            if not any(db in c for db in ['postgres', 'qdrant', 'redis', 'neo4j', 'minio'])
        ]
        
        if not killable_containers:
            logger.warning('No killable containers found')
            return
        
        # Kill 3 random containers
        targets = random.sample(killable_containers, min(3, len(killable_containers)))
        
        for target in targets:
            logger.info(f'Killing container: {target}')
            try:
                container = self.docker_client.containers.get(target)
                container.kill()
                logger.info(f'Killed {target}')
                
                # Wait for recovery
                time.sleep(experiment.recovery_time_seconds)
                
                if self.wait_for_recovery(target):
                    logger.info(f'✓ {target} recovered successfully')
                else:
                    self.failures_detected.append({
                        'experiment': experiment.name,
                        'service': target,
                        'failure': 'Failed to recover after kill',
                    })
                    logger.error(f'✗ {target} did not recover')
                    
            except Exception as e:
                logger.error(f'Error killing {target}: {e}')
                self.failures_detected.append({
                    'experiment': experiment.name,
                    'service': target,
                    'failure': str(e),
                })
        
        self.experiments_run.append(experiment)

    def cpu_saturation(self):
        """Stress CPU on random containers"""
        experiment = ChaosExperiment(
            name='CPU Saturation',
            description='Saturate CPU on containers and monitor impact',
            duration_seconds=60,
            recovery_time_seconds=30,
        )
        
        logger.info(f'Starting: {experiment.name}')
        
        containers = self.get_running_containers()
        target_containers = random.sample(containers, min(2, len(containers)))
        
        for target in target_containers:
            logger.info(f'Saturating CPU on: {target}')
            try:
                container = self.docker_client.containers.get(target)
                
                # Run stress command in container
                exec_result = container.exec_run(
                    'sh -c "yes > /dev/null &"',
                    detach=True,
                )
                
                logger.info(f'Started CPU stress on {target}')
                
                # Monitor for duration
                time.sleep(experiment.duration_seconds)
                
                # Stop stress (kill yes processes)
                try:
                    container.exec_run('pkill -f yes')
                    logger.info(f'Stopped CPU stress on {target}')
                except:
                    pass
                
                # Verify service is still healthy
                time.sleep(experiment.recovery_time_seconds)
                
                if self.check_service_health(target):
                    logger.info(f'✓ {target} survived CPU saturation')
                else:
                    self.failures_detected.append({
                        'experiment': experiment.name,
                        'service': target,
                        'failure': 'Service unhealthy after CPU stress',
                    })
                    logger.error(f'✗ {target} unhealthy after CPU stress')
                    
            except Exception as e:
                logger.error(f'Error stressing {target}: {e}')
        
        self.experiments_run.append(experiment)

    def network_partition(self):
        """Simulate network partitions using iptables"""
        experiment = ChaosExperiment(
            name='Network Partition',
            description='Block network traffic between services',
            duration_seconds=30,
            recovery_time_seconds=60,
        )
        
        logger.info(f'Starting: {experiment.name}')
        
        # Target API server and gateway
        partitions = [
            ('api-server', 'max-serve-llama'),
            ('gateway', 'qdrant'),
            ('mcpjungle-gateway', 'redis'),
        ]
        
        for source, target in partitions:
            logger.info(f'Creating network partition: {source} -> {target}')
            try:
                # Get container IPs
                source_container = self.docker_client.containers.get(source)
                target_container = self.docker_client.containers.get(target)
                
                # Get network info
                networks = source_container.attrs['NetworkSettings']['Networks']
                if not networks:
                    logger.warning(f'{source} has no networks')
                    continue
                
                network_name = list(networks.keys())[0]
                target_ip = target_container.attrs['NetworkSettings']['Networks'][network_name]['IPAddress']
                
                # Block traffic using iptables
                block_cmd = f'iptables -A OUTPUT -d {target_ip} -j DROP'
                source_container.exec_run(f'sh -c "{block_cmd}"', privileged=True)
                logger.info(f'Blocked {source} -> {target}')
                
                # Wait for duration
                time.sleep(experiment.duration_seconds)
                
                # Restore traffic
                restore_cmd = f'iptables -D OUTPUT -d {target_ip} -j DROP'
                source_container.exec_run(f'sh -c "{restore_cmd}"', privileged=True)
                logger.info(f'Restored {source} -> {target}')
                
                # Verify recovery
                time.sleep(experiment.recovery_time_seconds)
                
                if self.check_service_health(source):
                    logger.info(f'✓ {source} recovered from network partition')
                else:
                    self.failures_detected.append({
                        'experiment': experiment.name,
                        'service': source,
                        'failure': 'Service unhealthy after network partition',
                    })
                    logger.error(f'✗ {source} unhealthy after network partition')
                    
            except docker.errors.NotFound:
                logger.warning(f'Container not found: {source} or {target}')
            except Exception as e:
                logger.error(f'Error creating partition {source}->{target}: {e}')
        
        self.experiments_run.append(experiment)

    def memory_pressure(self):
        """Create memory pressure on containers"""
        experiment = ChaosExperiment(
            name='Memory Pressure',
            description='Consume memory and test OOM handling',
            duration_seconds=45,
            recovery_time_seconds=30,
        )
        
        logger.info(f'Starting: {experiment.name}')
        
        containers = self.get_running_containers()
        target_containers = random.sample(containers, min(2, len(containers)))
        
        for target in target_containers:
            logger.info(f'Creating memory pressure on: {target}')
            try:
                container = self.docker_client.containers.get(target)
                
                # Allocate memory using stress-ng (if available) or dd
                memory_stress_cmd = 'dd if=/dev/zero of=/tmp/memory_fill bs=1M count=512 || true'
                container.exec_run(f'sh -c "{memory_stress_cmd}"', detach=True)
                
                logger.info(f'Started memory stress on {target}')
                
                # Monitor for duration
                time.sleep(experiment.duration_seconds)
                
                # Clean up
                try:
                    container.exec_run('rm -f /tmp/memory_fill')
                except:
                    pass
                
                # Verify service recovery
                time.sleep(experiment.recovery_time_seconds)
                
                if self.check_service_health(target):
                    logger.info(f'✓ {target} survived memory pressure')
                else:
                    self.failures_detected.append({
                        'experiment': experiment.name,
                        'service': target,
                        'failure': 'Service unhealthy after memory pressure',
                    })
                    logger.error(f'✗ {target} unhealthy after memory pressure')
                    
            except Exception as e:
                logger.error(f'Error stressing {target}: {e}')
        
        self.experiments_run.append(experiment)

    def run_all_experiments(self):
        """Run all chaos experiments"""
        logger.info('=' * 60)
        logger.info('Starting Chaos Engineering Validation')
        logger.info('=' * 60)
        
        experiments = [
            self.random_pod_kill,
            self.cpu_saturation,
            self.memory_pressure,
            self.network_partition,
        ]
        
        for experiment in experiments:
            try:
                experiment()
                logger.info(f'Completed: {experiment.__name__}')
                time.sleep(10)  # Cool-down between experiments
            except Exception as e:
                logger.error(f'Experiment {experiment.__name__} failed: {e}')
        
        self.generate_report()

    def generate_report(self):
        """Generate chaos engineering report"""
        logger.info('\n' + '=' * 60)
        logger.info('Chaos Engineering Report')
        logger.info('=' * 60)
        
        logger.info(f'\nExperiments Run: {len(self.experiments_run)}')
        for exp in self.experiments_run:
            logger.info(f'  - {exp.name}')
        
        logger.info(f'\nFailures Detected: {len(self.failures_detected)}')
        if self.failures_detected:
            for failure in self.failures_detected:
                logger.error(f"  - {failure['experiment']}: {failure['service']} - {failure['failure']}")
        else:
            logger.info('  None - System is resilient!')
        
        # Calculate resilience score
        total_tests = len(self.experiments_run) * 3  # Average 3 services per experiment
        failures = len(self.failures_detected)
        resilience_score = ((total_tests - failures) / total_tests * 100) if total_tests > 0 else 0
        
        logger.info(f'\nResilience Score: {resilience_score:.1f}%')
        
        if resilience_score >= 90:
            logger.info('Status: EXCELLENT ✓')
        elif resilience_score >= 75:
            logger.info('Status: GOOD ⚠')
        else:
            logger.info('Status: NEEDS IMPROVEMENT ✗')
        
        logger.info('=' * 60)
        
        # Save report
        report = {
            'timestamp': datetime.now().isoformat(),
            'experiments_run': len(self.experiments_run),
            'failures_detected': len(self.failures_detected),
            'resilience_score': resilience_score,
            'failures': self.failures_detected,
        }
        
        import json
        with open('chaos_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info('Report saved to chaos_report.json')


def main():
    """Run chaos engineering tests"""
    engineer = ChaosEngineer()
    engineer.run_all_experiments()


if __name__ == '__main__':
    main()
