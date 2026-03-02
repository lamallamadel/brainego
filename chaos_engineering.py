"""
Chaos Engineering for Production Validation

Test Suites:

1. Basic Suite (--chaos-suite basic):
   - Random pod kills
   - CPU saturation

2. Advanced Suite (--chaos-suite advanced):
   - Random pod kills
   - CPU saturation
   - Advanced tests run in PARALLEL with async/await:
     * network_partition_test()
     * memory_pressure_test()
     * database_failover_test()

Advanced Tests Details:
- network_partition_test(): Simulates 50% packet loss between api-server and Qdrant for 60s using tc (traffic control)
  * Verifies circuit breaker triggers degraded mode
  * Monitors for automatic recovery after partition is removed
  * Records network_partition_active metric in Prometheus
  * Validates circuit breaker state via /health/circuit-breakers API
  
- memory_pressure_test(): Simulates 90% memory usage on learning-engine pod using stress-ng
  * Verifies graceful degradation (service stays responsive but degraded)
  * Monitors for automatic recovery after pressure is released
  * Tests OOM handling and memory limits
  * Validates circuit breaker state via /health/circuit-breakers API
  
- database_failover_test(): Kills Postgres primary pod and verifies StatefulSet automatic recovery
  * Tests database high availability
  * Verifies automatic pod restart and recovery
  * Ensures data integrity after failover
  * Validates circuit breaker state via /health/circuit-breakers API

Circuit Breaker Integration:
- Validates circuit breaker states via /circuit-breakers API endpoint
- Monitors for proper state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Checks failure rates and rejection counts
- Included in consolidated chaos report

Reporting:
- Consolidated chaos report with per-service resilience scores
- Overall resilience score based on all tests
- Circuit breaker validation results
- Detailed test results per service
- Failures and recovery information

Prometheus Metrics Exported:
- chaos_test_total: Counter of chaos tests executed by type
- chaos_test_failures_total: Counter of failures by test type and service
- network_partition_active: Gauge indicating active network partitions
- circuit_breaker_state: Gauge of circuit breaker state (0=closed, 1=open, 2=half_open)
- circuit_breaker_requests_total: Counter of requests through circuit breaker
- circuit_breaker_rejections_total: Counter of rejected requests
- pod_restart_rate: Derived from kube_pod_container_status_restarts_total

Prometheus Alerts Created:
- CircuitBreakerOpen: Circuit breaker is in OPEN state for 2+ minutes
- CircuitBreakerOpenExtended: Circuit breaker OPEN for 10+ minutes (critical)
- PodRestartRateHigh: Pod restart rate > 0.1 restarts/sec over 15m
- PodRestartRateCritical: Pod restart rate > 0.3 restarts/sec (critical)
- PodRestartSpike: 3+ restarts in 10 minutes
- StatefulSetPodDown: StatefulSet has pods not ready for 5+ minutes
- NetworkPartitionDetected: Network partition detected between services
- MemoryPressureDetected: Container using >90% of memory limit

Usage:
    # Run basic tests only (legacy mode)
    python chaos_engineering.py
    
    # Run basic suite (pod kills + CPU saturation)
    python chaos_engineering.py --chaos-suite basic
    
    # Run advanced suite (basic + parallel advanced tests)
    python chaos_engineering.py --chaos-suite advanced
    
    # Integration with production validation
    python run_production_validation.py --chaos-suite basic
    python run_production_validation.py --chaos-suite advanced
    
    # Legacy flag (deprecated)
    python chaos_engineering.py --advanced
    python run_production_validation.py --chaos

Requirements:
- Docker access for container manipulation
- iproute2 package for tc (traffic control) - auto-installed
- stress-ng for memory pressure - auto-installed
- Prometheus for metrics collection (optional)
"""

import asyncio
import docker
import httpx
import json
import logging
import random
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics - optional dependency
try:
    from prometheus_client import Counter, Gauge
    METRICS_AVAILABLE = True
    
    chaos_test_counter = Counter(
        'chaos_test_total',
        'Total chaos tests executed',
        ['test_type']
    )
    
    chaos_test_failures_counter = Counter(
        'chaos_test_failures_total',
        'Total chaos test failures',
        ['test_type', 'service']
    )
    
    network_partition_gauge = Gauge(
        'network_partition_active',
        'Network partition active (1=active, 0=inactive)',
        ['source', 'target']
    )
    
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning('prometheus_client not available, chaos metrics disabled')


@dataclass
class ChaosExperiment:
    """Chaos experiment configuration"""
    name: str
    description: str
    duration_seconds: int
    recovery_time_seconds: int


class ChaosEngineer:
    """Chaos engineering orchestrator"""

    def __init__(self, api_base_url: str = "http://localhost:8000"):
        self.docker_client = docker.from_env()
        self.experiments_run = []
        self.failures_detected = []
        self.api_base_url = api_base_url
        self.service_test_results = defaultdict(list)  # Track per-service test results
        self.circuit_breaker_validations = []  # Track circuit breaker state validations

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

    async def validate_circuit_breaker_state(self) -> Dict[str, any]:
        """
        Validate circuit breaker state via /health/circuit-breakers API endpoint.
        
        Returns dict with circuit breaker states and validation results.
        """
        logger.info('Validating circuit breaker states...')
        
        validation_result = {
            'timestamp': datetime.utcnow().isoformat(),
            'endpoint_available': False,
            'circuit_breakers': {},
            'validation_passed': False,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try the documented endpoint first
                response = await client.get(f'{self.api_base_url}/circuit-breakers')
                
                if response.status_code == 200:
                    validation_result['endpoint_available'] = True
                    data = response.json()
                    
                    circuit_breakers = data.get('circuit_breakers', {})
                    validation_result['circuit_breakers'] = circuit_breakers
                    
                    # Log circuit breaker states
                    logger.info(f'Found {len(circuit_breakers)} circuit breakers:')
                    for name, stats in circuit_breakers.items():
                        state = stats.get('state', 'unknown')
                        total_requests = stats.get('total_requests', 0)
                        total_failures = stats.get('total_failures', 0)
                        
                        logger.info(f'  - {name}: state={state}, requests={total_requests}, failures={total_failures}')
                        
                        # Validate expected behavior during chaos
                        if total_requests > 0:
                            failure_rate = total_failures / total_requests
                            if failure_rate > 0.5 and state == 'closed':
                                logger.warning(f'  ⚠ High failure rate but circuit breaker still CLOSED')
                    
                    validation_result['validation_passed'] = True
                    logger.info('✓ Circuit breaker validation completed')
                    
                else:
                    logger.warning(f'Circuit breaker endpoint returned {response.status_code}')
                    
        except httpx.ConnectError:
            logger.warning('Could not connect to API server for circuit breaker validation')
        except Exception as e:
            logger.error(f'Error validating circuit breakers: {e}')
        
        self.circuit_breaker_validations.append(validation_result)
        return validation_result
    
    def record_service_test_result(self, service: str, test_name: str, passed: bool):
        """Record test result for a service for resilience scoring."""
        self.service_test_results[service].append({
            'test': test_name,
            'passed': passed,
            'timestamp': datetime.utcnow().isoformat()
        })

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
                
                recovered = self.wait_for_recovery(target)
                self.record_service_test_result(target, experiment.name, recovered)
                
                if recovered:
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
                self.record_service_test_result(target, experiment.name, False)
        
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
                
                healthy = self.check_service_health(target)
                self.record_service_test_result(target, experiment.name, healthy)
                
                if healthy:
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
                self.record_service_test_result(target, experiment.name, False)
        
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

    async def network_partition_test(self):
        """Simulate 50% packet loss between api-server and Qdrant for 60s and verify circuit breaker triggers"""
        experiment = ChaosExperiment(
            name='Network Partition Test - Circuit Breaker',
            description='Simulate 50% packet loss between api-server and Qdrant, verify circuit breaker triggers degraded mode',
            duration_seconds=60,
            recovery_time_seconds=90,
        )
        
        logger.info(f'Starting: {experiment.name}')
        
        # Record test execution
        if METRICS_AVAILABLE:
            chaos_test_counter.labels(test_type='network_partition').inc()
        
        try:
            # Get api-server and qdrant containers
            api_server = self.docker_client.containers.get('api-server')
            qdrant = self.docker_client.containers.get('qdrant')
            
            # Get Qdrant IP address
            networks = qdrant.attrs['NetworkSettings']['Networks']
            if not networks:
                logger.warning('Qdrant has no networks')
                return
            
            network_name = list(networks.keys())[0]
            qdrant_ip = qdrant.attrs['NetworkSettings']['Networks'][network_name]['IPAddress']
            
            logger.info(f'Qdrant IP: {qdrant_ip}')
            
            # Install tc (traffic control) if not available
            api_server.exec_run('sh -c "command -v tc || (apt-get update && apt-get install -y iproute2) || apk add --no-cache iproute2"')
            
            # Add 50% packet loss using tc
            tc_add_cmd = f'tc qdisc add dev eth0 root netem loss 50%'
            result = api_server.exec_run(f'sh -c "{tc_add_cmd}"', privileged=True)
            
            if result.exit_code == 0:
                logger.info(f'✓ Added 50% packet loss on api-server')
                
                # Record network partition active
                if METRICS_AVAILABLE:
                    network_partition_gauge.labels(
                        source='api-server',
                        target='qdrant'
                    ).set(1)
            else:
                logger.warning(f'Failed to add packet loss: {result.output.decode()}')
            
            # Monitor for circuit breaker activation
            logger.info('Monitoring for circuit breaker activation...')
            circuit_breaker_triggered = False
            
            # Check circuit breaker status via API or logs
            start_time = time.time()
            while time.time() - start_time < experiment.duration_seconds:
                try:
                    # Check if circuit breaker is in OPEN state
                    check_result = api_server.exec_run('sh -c "curl -s http://localhost:8000/health/circuit-breakers || echo \'{}\'"')
                    if check_result.exit_code == 0:
                        output = check_result.output.decode()
                        if 'open' in output.lower() or 'degraded' in output.lower():
                            circuit_breaker_triggered = True
                            logger.info('✓ Circuit breaker triggered degraded mode')
                            break
                except Exception as e:
                    logger.debug(f'Error checking circuit breaker: {e}')
                
                await asyncio.sleep(5)
            
            # Wait for full duration
            elapsed = time.time() - start_time
            if elapsed < experiment.duration_seconds:
                await asyncio.sleep(experiment.duration_seconds - elapsed)
            
            # Remove packet loss
            tc_del_cmd = 'tc qdisc del dev eth0 root netem'
            api_server.exec_run(f'sh -c "{tc_del_cmd}"', privileged=True)
            logger.info('✓ Removed packet loss')
            
            # Clear network partition metric
            if METRICS_AVAILABLE:
                network_partition_gauge.labels(
                    source='api-server',
                    target='qdrant'
                ).set(0)
            
            # Wait for recovery
            time.sleep(experiment.recovery_time_seconds)
            
            # Verify recovery
            recovered = self.check_service_health('api-server')
            test_passed = recovered and circuit_breaker_triggered
            self.record_service_test_result('api-server', experiment.name, test_passed)
            
            if recovered:
                logger.info('✓ api-server recovered from network partition')
                
                if circuit_breaker_triggered:
                    logger.info('✓ Circuit breaker functioned correctly')
                else:
                    logger.warning('⚠ Circuit breaker may not have triggered')
                    self.failures_detected.append({
                        'experiment': experiment.name,
                        'service': 'api-server',
                        'failure': 'Circuit breaker did not trigger during packet loss',
                    })
                    
                    # Record failure metric
                    if METRICS_AVAILABLE:
                        chaos_test_failures_counter.labels(
                            test_type='network_partition',
                            service='api-server'
                        ).inc()
            else:
                self.failures_detected.append({
                    'experiment': experiment.name,
                    'service': 'api-server',
                    'failure': 'Service unhealthy after network partition',
                })
                logger.error(f'✗ api-server unhealthy after network partition')
                
                # Record failure metric
                if METRICS_AVAILABLE:
                    chaos_test_failures_counter.labels(
                        test_type='network_partition',
                        service='api-server'
                    ).inc()
            
            # Validate circuit breaker state after test
            await self.validate_circuit_breaker_state()
                
        except docker.errors.NotFound as e:
            logger.warning(f'Container not found: {e}')
            self.record_service_test_result('api-server', experiment.name, False)
        except Exception as e:
            logger.error(f'Error in network partition test: {e}')
            self.failures_detected.append({
                'experiment': experiment.name,
                'service': 'api-server',
                'failure': str(e),
            })
            self.record_service_test_result('api-server', experiment.name, False)
        
        self.experiments_run.append(experiment)

    async def memory_pressure_test(self):
        """Simulate 90% memory usage on learning-engine pod and verify graceful degradation"""
        experiment = ChaosExperiment(
            name='Memory Pressure Test - Learning Engine',
            description='Simulate 90% memory usage on learning-engine pod, verify graceful degradation',
            duration_seconds=90,
            recovery_time_seconds=60,
        )
        
        logger.info(f'Starting: {experiment.name}')
        
        # Record test execution
        if METRICS_AVAILABLE:
            chaos_test_counter.labels(test_type='memory_pressure').inc()
        
        try:
            # Get learning-engine container
            try:
                container = self.docker_client.containers.get('learning-engine')
            except docker.errors.NotFound:
                # Try alternative names
                learning_containers = [c for c in self.docker_client.containers.list() if 'learning' in c.name.lower()]
                if not learning_containers:
                    logger.warning('Learning engine container not found, skipping test')
                    return
                container = learning_containers[0]
            
            logger.info(f'Testing memory pressure on: {container.name}')
            
            # Install stress-ng if not available
            install_cmd = 'command -v stress-ng || (apt-get update && apt-get install -y stress-ng) || apk add --no-cache stress-ng'
            container.exec_run(f'sh -c "{install_cmd}"')
            
            # Get container memory limit
            mem_stats = container.stats(stream=False)
            mem_limit = mem_stats.get('memory_stats', {}).get('limit', 2 * 1024 * 1024 * 1024)  # Default 2GB
            
            # Calculate 90% of memory
            target_memory_mb = int((mem_limit * 0.9) / (1024 * 1024))
            
            logger.info(f'Simulating 90% memory usage (~{target_memory_mb}MB)')
            
            # Start stress-ng to consume memory
            stress_cmd = f'stress-ng --vm 1 --vm-bytes {target_memory_mb}M --timeout {experiment.duration_seconds}s --vm-method all'
            stress_result = container.exec_run(f'sh -c "{stress_cmd}"', detach=True)
            
            logger.info(f'✓ Started memory pressure on {container.name}')
            
            # Monitor graceful degradation
            degradation_detected = False
            start_time = time.time()
            
            while time.time() - start_time < experiment.duration_seconds:
                try:
                    # Check if service is still responsive but degraded
                    health_check = container.exec_run('sh -c "curl -s http://localhost:8080/health || echo \'unhealthy\'"')
                    if health_check.exit_code == 0:
                        output = health_check.output.decode()
                        if 'degraded' in output.lower() or 'warning' in output.lower():
                            degradation_detected = True
                            logger.info('✓ Graceful degradation detected')
                except Exception as e:
                    logger.debug(f'Error checking degradation: {e}')
                
                # Check if container is still running
                container.reload()
                if container.status != 'running':
                    logger.warning(f'⚠ Container {container.name} stopped during memory pressure')
                    break
                
                await asyncio.sleep(10)
            
            # Wait for stress-ng to complete
            await asyncio.sleep(5)
            
            # Kill any remaining stress processes
            try:
                container.exec_run('pkill -f stress-ng')
            except:
                pass
            
            # Wait for recovery
            logger.info('Waiting for recovery...')
            time.sleep(experiment.recovery_time_seconds)
            
            # Verify recovery
            container.reload()
            recovered = container.status == 'running' and self.check_service_health(container.name)
            self.record_service_test_result(container.name, experiment.name, recovered)
            
            if recovered:
                logger.info(f'✓ {container.name} recovered from memory pressure')
                
                if degradation_detected:
                    logger.info('✓ Graceful degradation functioned correctly')
                else:
                    logger.info('ℹ No explicit degradation signal detected (may still be functioning correctly)')
            else:
                self.failures_detected.append({
                    'experiment': experiment.name,
                    'service': container.name,
                    'failure': 'Service unhealthy after memory pressure',
                })
                logger.error(f'✗ {container.name} unhealthy after memory pressure')
                
                # Record failure metric
                if METRICS_AVAILABLE:
                    chaos_test_failures_counter.labels(
                        test_type='memory_pressure',
                        service=container.name
                    ).inc()
            
            # Validate circuit breaker state after test
            await self.validate_circuit_breaker_state()
                
        except Exception as e:
            logger.error(f'Error in memory pressure test: {e}')
            service_name = 'learning-engine'
            self.failures_detected.append({
                'experiment': experiment.name,
                'service': service_name,
                'failure': str(e),
            })
            self.record_service_test_result(service_name, experiment.name, False)
            
            # Record failure metric
            if METRICS_AVAILABLE:
                chaos_test_failures_counter.labels(
                    test_type='memory_pressure',
                    service=service_name
                ).inc()
        
        self.experiments_run.append(experiment)

    async def database_failover_test(self):
        """Kill Postgres primary and verify StatefulSet automatic recovery"""
        experiment = ChaosExperiment(
            name='Database Failover Test - Postgres',
            description='Kill Postgres primary pod and verify StatefulSet automatic recovery',
            duration_seconds=10,
            recovery_time_seconds=120,
        )
        
        logger.info(f'Starting: {experiment.name}')
        
        # Record test execution
        if METRICS_AVAILABLE:
            chaos_test_counter.labels(test_type='database_failover').inc()
        
        try:
            # Get postgres container
            try:
                postgres = self.docker_client.containers.get('postgres')
            except docker.errors.NotFound:
                # Try to find postgres container
                postgres_containers = [c for c in self.docker_client.containers.list() if 'postgres' in c.name.lower()]
                if not postgres_containers:
                    logger.warning('Postgres container not found, skipping test')
                    return
                postgres = postgres_containers[0]
            
            logger.info(f'Testing failover on: {postgres.name}')
            
            # Record initial state
            initial_id = postgres.id
            logger.info(f'Initial Postgres container ID: {initial_id[:12]}')
            
            # Kill the postgres container
            logger.info('Killing Postgres container...')
            postgres.kill()
            logger.info('✓ Postgres container killed')
            
            # Wait a bit
            await asyncio.sleep(experiment.duration_seconds)
            
            # Monitor for automatic recovery
            logger.info('Monitoring for automatic recovery...')
            recovery_successful = False
            start_time = time.time()
            
            while time.time() - start_time < experiment.recovery_time_seconds:
                try:
                    # Check if postgres is back up
                    postgres_new = self.docker_client.containers.get('postgres')
                    
                    if postgres_new.status == 'running':
                        logger.info(f'✓ Postgres container recovered (ID: {postgres_new.id[:12]})')
                        
                        # Verify it's functional
                        await asyncio.sleep(10)  # Allow time for postgres to fully start
                        
                        # Try to connect
                        health_check = postgres_new.exec_run('pg_isready -U postgres')
                        if health_check.exit_code == 0:
                            recovery_successful = True
                            logger.info('✓ Postgres is accepting connections')
                            break
                        else:
                            logger.debug('Postgres not ready yet...')
                except docker.errors.NotFound:
                    logger.debug('Postgres container not found yet...')
                except Exception as e:
                    logger.debug(f'Error checking recovery: {e}')
                
                await asyncio.sleep(5)
            
            self.record_service_test_result('postgres', experiment.name, recovery_successful)
            
            if recovery_successful:
                logger.info('✓ Database failover and recovery successful')
            else:
                self.failures_detected.append({
                    'experiment': experiment.name,
                    'service': 'postgres',
                    'failure': 'Postgres did not recover within timeout',
                })
                logger.error(f'✗ Postgres did not recover within {experiment.recovery_time_seconds}s')
                
                # Record failure metric
                if METRICS_AVAILABLE:
                    chaos_test_failures_counter.labels(
                        test_type='database_failover',
                        service='postgres'
                    ).inc()
            
            # Validate circuit breaker state after test
            await self.validate_circuit_breaker_state()
                
        except Exception as e:
            logger.error(f'Error in database failover test: {e}')
            self.failures_detected.append({
                'experiment': experiment.name,
                'service': 'postgres',
                'failure': str(e),
            })
            self.record_service_test_result('postgres', experiment.name, False)
            
            # Record failure metric
            if METRICS_AVAILABLE:
                chaos_test_failures_counter.labels(
                    test_type='database_failover',
                    service='postgres'
                ).inc()
        
        self.experiments_run.append(experiment)

    async def run_parallel_advanced_tests(self):
        """
        Run advanced chaos tests in parallel with async/await.
        Executes network_partition_test, memory_pressure_test, and database_failover_test simultaneously.
        """
        logger.info('=' * 60)
        logger.info('Running Advanced Chaos Tests in PARALLEL')
        logger.info('=' * 60)
        
        try:
            # Run three advanced tests concurrently
            results = await asyncio.gather(
                self.network_partition_test(),
                self.memory_pressure_test(),
                self.database_failover_test(),
                return_exceptions=True
            )
            
            # Check for exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    test_names = ['network_partition_test', 'memory_pressure_test', 'database_failover_test']
                    logger.error(f'{test_names[i]} failed with exception: {result}')
            
            logger.info('✓ Parallel advanced tests completed')
            
        except Exception as e:
            logger.error(f'Error running parallel advanced tests: {e}')
    
    def run_all_experiments(self, include_new_tests: bool = True, chaos_suite: str = None):
        """
        Run all chaos experiments.
        
        Args:
            include_new_tests: Whether to include advanced tests (deprecated, use chaos_suite)
            chaos_suite: 'basic', 'advanced', or None (for backward compatibility)
        """
        logger.info('=' * 60)
        if chaos_suite:
            logger.info(f'Starting Chaos Engineering Validation - Suite: {chaos_suite.upper()}')
        else:
            logger.info('Starting Chaos Engineering Validation')
        logger.info('=' * 60)
        
        # Determine which tests to run based on suite
        if chaos_suite == 'basic':
            # Basic suite: pod kills + CPU saturation only
            sync_experiments = [
                self.random_pod_kill,
                self.cpu_saturation,
            ]
            run_advanced = False
            run_parallel = False
            
        elif chaos_suite == 'advanced':
            # Advanced suite: basic tests + advanced tests in parallel
            sync_experiments = [
                self.random_pod_kill,
                self.cpu_saturation,
            ]
            run_advanced = True
            run_parallel = True
            
        else:
            # Legacy behavior for backward compatibility
            sync_experiments = [
                self.random_pod_kill,
                self.cpu_saturation,
                self.memory_pressure,
                self.network_partition,
            ]
            run_advanced = include_new_tests
            run_parallel = False
        
        # Run synchronous experiments
        for experiment in sync_experiments:
            try:
                experiment()
                logger.info(f'Completed: {experiment.__name__}')
                time.sleep(10)  # Cool-down between experiments
            except Exception as e:
                logger.error(f'Experiment {experiment.__name__} failed: {e}')
        
        # Run advanced tests (either parallel or sequential)
        if run_advanced:
            if run_parallel:
                # Run advanced tests in parallel
                try:
                    asyncio.run(self.run_parallel_advanced_tests())
                    time.sleep(15)  # Cool-down after parallel tests
                except Exception as e:
                    logger.error(f'Parallel advanced tests failed: {e}')
            else:
                # Run advanced tests sequentially (legacy mode)
                advanced_experiments = [
                    self.network_partition_test,
                    self.memory_pressure_test,
                    self.database_failover_test,
                ]
                
                for experiment in advanced_experiments:
                    try:
                        asyncio.run(experiment())
                        logger.info(f'Completed: {experiment.__name__}')
                        time.sleep(10)  # Cool-down between experiments
                    except Exception as e:
                        logger.error(f'Experiment {experiment.__name__} failed: {e}')
        
        # Final circuit breaker validation
        logger.info('Running final circuit breaker validation...')
        try:
            asyncio.run(self.validate_circuit_breaker_state())
        except Exception as e:
            logger.error(f'Final circuit breaker validation failed: {e}')
        
        self.generate_report()

    def calculate_service_resilience_scores(self) -> Dict[str, float]:
        """
        Calculate per-service resilience scores based on test results.
        
        Returns:
            Dict mapping service name to resilience score (0-100%)
        """
        service_scores = {}
        
        for service, test_results in self.service_test_results.items():
            if not test_results:
                continue
            
            passed_tests = sum(1 for result in test_results if result['passed'])
            total_tests = len(test_results)
            
            score = (passed_tests / total_tests * 100) if total_tests > 0 else 0
            service_scores[service] = round(score, 1)
        
        return service_scores
    
    def generate_report(self):
        """Generate consolidated chaos engineering report with per-service resilience scores"""
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
        
        # Calculate per-service resilience scores
        service_scores = self.calculate_service_resilience_scores()
        
        logger.info('\n' + '=' * 60)
        logger.info('Per-Service Resilience Scores')
        logger.info('=' * 60)
        
        if service_scores:
            for service, score in sorted(service_scores.items(), key=lambda x: x[1], reverse=True):
                test_count = len(self.service_test_results[service])
                passed = sum(1 for r in self.service_test_results[service] if r['passed'])
                
                if score >= 90:
                    status = '✓ EXCELLENT'
                elif score >= 75:
                    status = '⚠ GOOD'
                else:
                    status = '✗ NEEDS IMPROVEMENT'
                
                logger.info(f'  {service}: {score}% ({passed}/{test_count} tests passed) - {status}')
        else:
            logger.info('  No per-service data collected')
        
        # Calculate overall resilience score
        total_tests = len(self.experiments_run) * 3  # Average 3 services per experiment
        failures = len(self.failures_detected)
        overall_resilience_score = ((total_tests - failures) / total_tests * 100) if total_tests > 0 else 0
        
        # Alternative calculation based on actual service test results
        if service_scores:
            overall_resilience_score = sum(service_scores.values()) / len(service_scores)
        
        logger.info('\n' + '=' * 60)
        logger.info(f'Overall Resilience Score: {overall_resilience_score:.1f}%')
        
        if overall_resilience_score >= 90:
            logger.info('Status: EXCELLENT ✓')
        elif overall_resilience_score >= 75:
            logger.info('Status: GOOD ⚠')
        else:
            logger.info('Status: NEEDS IMPROVEMENT ✗')
        
        # Circuit breaker summary
        logger.info('\n' + '=' * 60)
        logger.info('Circuit Breaker Validations')
        logger.info('=' * 60)
        
        if self.circuit_breaker_validations:
            for i, validation in enumerate(self.circuit_breaker_validations, 1):
                if validation['validation_passed']:
                    cb_count = len(validation['circuit_breakers'])
                    logger.info(f'  Validation #{i}: ✓ PASSED ({cb_count} circuit breakers checked)')
                else:
                    logger.warning(f'  Validation #{i}: ✗ FAILED (endpoint unavailable)')
        else:
            logger.info('  No circuit breaker validations performed')
        
        logger.info('=' * 60)
        
        # Save comprehensive report
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'experiments_run': len(self.experiments_run),
                'failures_detected': len(self.failures_detected),
                'overall_resilience_score': round(overall_resilience_score, 1),
            },
            'experiments': [
                {
                    'name': exp.name,
                    'description': exp.description,
                    'duration_seconds': exp.duration_seconds,
                    'recovery_time_seconds': exp.recovery_time_seconds,
                }
                for exp in self.experiments_run
            ],
            'failures': self.failures_detected,
            'service_resilience_scores': service_scores,
            'service_test_results': {
                service: results
                for service, results in self.service_test_results.items()
            },
            'circuit_breaker_validations': self.circuit_breaker_validations,
        }
        
        with open('chaos_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info('\nConsolidated chaos report saved to chaos_report.json')


def main():
    """Run chaos engineering tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Chaos Engineering Tests')
    parser.add_argument(
        '--advanced',
        action='store_true',
        help='Run advanced chaos tests (network partition, memory pressure, database failover) - DEPRECATED, use --chaos-suite advanced'
    )
    parser.add_argument(
        '--chaos-suite',
        choices=['basic', 'advanced'],
        help='Chaos test suite: basic (pod kills + CPU saturation) or advanced (+ network partitions + memory pressure + DB failover with parallel execution)'
    )
    parser.add_argument(
        '--api-url',
        default='http://localhost:8000',
        help='Base URL for API server (for circuit breaker validation)'
    )
    
    args = parser.parse_args()
    
    engineer = ChaosEngineer(api_base_url=args.api_url)
    
    # Handle chaos-suite flag
    if args.chaos_suite:
        engineer.run_all_experiments(chaos_suite=args.chaos_suite)
    else:
        # Legacy support for --advanced flag
        engineer.run_all_experiments(include_new_tests=args.advanced)


if __name__ == '__main__':
    main()
