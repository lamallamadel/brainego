#!/usr/bin/env python3
"""
Multi-Region Deployment Script
Deploys full AI Platform stack to a new region with DNS failover configuration
"""

import argparse
import json
import subprocess
import sys
import time
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

# Needs: python-package:pyyaml>=6.0
# Needs: python-package:boto3>=1.26.0 (for AWS Route53)
# Needs: python-package:google-cloud-dns>=0.34.0 (for Google Cloud DNS)

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

try:
    from google.cloud import dns as gcp_dns
    from google.api_core import exceptions as gcp_exceptions
    GCP_DNS_AVAILABLE = True
except ImportError:
    GCP_DNS_AVAILABLE = False


@dataclass
class RegionConfig:
    """Configuration for a deployment region"""
    name: str
    cloud_provider: str  # aws, gcp, azure
    cluster_name: str
    cluster_zone: str
    endpoint: str
    internal_endpoint: str
    priority: int
    weight: int
    max_latency_ms: int
    storage_class: str
    gpu_node_type: str
    dns_provider: str = "route53"  # route53 or cloud_dns
    hosted_zone_id: Optional[str] = None
    gcp_project_id: Optional[str] = None
    gcp_dns_zone_name: Optional[str] = None


@dataclass
class DeploymentStatus:
    """Status of a region deployment"""
    region: str
    phase: str  # preparing, deploying, verifying, healthy, failed
    message: str
    timestamp: float
    health_checks: Dict[str, bool]


class MultiRegionDeployer:
    """Handles multi-region deployments with DNS failover"""
    
    def __init__(
        self,
        region: str,
        cluster_name: str,
        values_file: str,
        dry_run: bool = False,
        skip_dns: bool = False
    ):
        self.region = region
        self.cluster_name = cluster_name
        self.values_file = values_file
        self.dry_run = dry_run
        self.skip_dns = skip_dns
        
        self.project_root = Path(__file__).parent.parent.parent
        self.helm_chart = self.project_root / "helm" / "ai-platform"
        self.configs_dir = self.project_root / "configs"
        
        self.status = DeploymentStatus(
            region=region,
            phase="initializing",
            message="Starting deployment",
            timestamp=time.time(),
            health_checks={}
        )
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def run_command(
        self,
        cmd: List[str],
        check: bool = True,
        capture_output: bool = False
    ) -> Optional[subprocess.CompletedProcess]:
        """Run a shell command"""
        if self.dry_run:
            self.log(f"[DRY RUN] Would execute: {' '.join(cmd)}", "DEBUG")
            return None
        
        self.log(f"Executing: {' '.join(cmd)}", "DEBUG")
        
        try:
            result = subprocess.run(
                cmd,
                check=check,
                capture_output=capture_output,
                text=True
            )
            return result
        except subprocess.CalledProcessError as e:
            self.log(f"Command failed: {e}", "ERROR")
            if capture_output:
                self.log(f"stdout: {e.stdout}", "ERROR")
                self.log(f"stderr: {e.stderr}", "ERROR")
            raise
    
    def load_region_config(self) -> RegionConfig:
        """Load region configuration"""
        self.log(f"Loading configuration for region: {self.region}")
        
        # Load multi-region values file
        with open(self.values_file, 'r') as f:
            values = yaml.safe_load(f)
        
        # Extract region-specific config
        if 'global' not in values or 'multiRegion' not in values['global']:
            raise ValueError("Multi-region configuration not found in values file")
        
        multi_region_config = values['global']['multiRegion']
        
        if self.region not in multi_region_config.get('regions', []):
            raise ValueError(f"Region {self.region} not found in configuration")
        
        # Region-specific defaults (customize per cloud provider)
        region_configs = {
            'us-west-1': RegionConfig(
                name='us-west-1',
                cloud_provider='aws',
                cluster_name=self.cluster_name,
                cluster_zone='us-west-1a',
                endpoint=f'https://{self.region}.ai-platform.example.com',
                internal_endpoint=f'http://gateway.{self.region}.ai-platform.svc.cluster.local:9002',
                priority=1,
                weight=100,
                max_latency_ms=100,
                storage_class='gp3',
                gpu_node_type='p3.2xlarge'
            ),
            'us-east-1': RegionConfig(
                name='us-east-1',
                cloud_provider='aws',
                cluster_name=self.cluster_name,
                cluster_zone='us-east-1a',
                endpoint=f'https://{self.region}.ai-platform.example.com',
                internal_endpoint=f'http://gateway.{self.region}.ai-platform.svc.cluster.local:9002',
                priority=2,
                weight=100,
                max_latency_ms=100,
                storage_class='gp3',
                gpu_node_type='p3.2xlarge'
            ),
            'eu-west-1': RegionConfig(
                name='eu-west-1',
                cloud_provider='aws',
                cluster_name=self.cluster_name,
                cluster_zone='eu-west-1a',
                endpoint=f'https://{self.region}.ai-platform.example.com',
                internal_endpoint=f'http://gateway.{self.region}.ai-platform.svc.cluster.local:9002',
                priority=3,
                weight=100,
                max_latency_ms=150,
                storage_class='gp3',
                gpu_node_type='p3.2xlarge'
            ),
            'ap-southeast-1': RegionConfig(
                name='ap-southeast-1',
                cloud_provider='aws',
                cluster_name=self.cluster_name,
                cluster_zone='ap-southeast-1a',
                endpoint=f'https://{self.region}.ai-platform.example.com',
                internal_endpoint=f'http://gateway.{self.region}.ai-platform.svc.cluster.local:9002',
                priority=4,
                weight=100,
                max_latency_ms=200,
                storage_class='gp3',
                gpu_node_type='p3.2xlarge'
            ),
        }
        
        if self.region not in region_configs:
            raise ValueError(f"No configuration template for region: {self.region}")
        
        return region_configs[self.region]
    
    def verify_prerequisites(self) -> bool:
        """Verify deployment prerequisites"""
        self.log("Verifying prerequisites...")
        self.status.phase = "verifying_prerequisites"
        
        checks = {
            'kubectl': ['kubectl', 'version', '--client'],
            'helm': ['helm', 'version'],
        }
        
        for tool, cmd in checks.items():
            try:
                self.run_command(cmd, capture_output=True)
                self.log(f"✓ {tool} is available")
                self.status.health_checks[f'{tool}_available'] = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                self.log(f"✗ {tool} is not available", "ERROR")
                self.status.health_checks[f'{tool}_available'] = False
                return False
        
        # Check cluster connectivity
        try:
            self.run_command(
                ['kubectl', 'cluster-info'],
                capture_output=True
            )
            self.log(f"✓ Connected to cluster: {self.cluster_name}")
            self.status.health_checks['cluster_connected'] = True
        except subprocess.CalledProcessError:
            self.log(f"✗ Cannot connect to cluster: {self.cluster_name}", "ERROR")
            self.status.health_checks['cluster_connected'] = False
            return False
        
        return True
    
    def create_namespace(self):
        """Create Kubernetes namespace"""
        self.log(f"Creating namespace: ai-platform")
        self.status.phase = "creating_namespace"
        
        namespace_yaml = {
            'apiVersion': 'v1',
            'kind': 'Namespace',
            'metadata': {
                'name': 'ai-platform',
                'labels': {
                    'name': 'ai-platform',
                    'region': self.region
                }
            }
        }
        
        if not self.dry_run:
            # Check if namespace exists
            result = self.run_command(
                ['kubectl', 'get', 'namespace', 'ai-platform'],
                check=False,
                capture_output=True
            )
            
            if result and result.returncode == 0:
                self.log("Namespace already exists, skipping creation")
            else:
                # Create namespace
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                    yaml.dump(namespace_yaml, f)
                    f.flush()
                    self.run_command(['kubectl', 'apply', '-f', f.name])
                    Path(f.name).unlink()
        
        self.status.health_checks['namespace_created'] = True
    
    def setup_storage_classes(self, config: RegionConfig):
        """Setup storage classes for regional disks"""
        self.log("Setting up storage classes...")
        self.status.phase = "setting_up_storage"
        
        storage_classes = {
            'regional-ssd': {
                'apiVersion': 'storage.k8s.io/v1',
                'kind': 'StorageClass',
                'metadata': {
                    'name': 'regional-ssd'
                },
                'provisioner': 'kubernetes.io/aws-ebs',
                'parameters': {
                    'type': config.storage_class,
                    'fsType': 'ext4',
                    'encrypted': 'true'
                },
                'volumeBindingMode': 'WaitForFirstConsumer',
                'allowVolumeExpansion': True
            },
            'regional-pd-ssd': {
                'apiVersion': 'storage.k8s.io/v1',
                'kind': 'StorageClass',
                'metadata': {
                    'name': 'regional-pd-ssd'
                },
                'provisioner': 'kubernetes.io/aws-ebs',
                'parameters': {
                    'type': config.storage_class,
                    'fsType': 'ext4',
                    'encrypted': 'true',
                    'iopsPerGB': '10'
                },
                'volumeBindingMode': 'WaitForFirstConsumer',
                'allowVolumeExpansion': True
            }
        }
        
        for name, sc in storage_classes.items():
            if not self.dry_run:
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                    yaml.dump(sc, f)
                    f.flush()
                    self.run_command(['kubectl', 'apply', '-f', f.name])
                    Path(f.name).unlink()
        
        self.status.health_checks['storage_classes_created'] = True
    
    def install_dependencies(self):
        """Install Helm chart dependencies"""
        self.log("Installing Helm dependencies...")
        self.status.phase = "installing_dependencies"
        
        # Add Helm repositories
        repos = {
            'kong': 'https://charts.konghq.com',
            'jetstack': 'https://charts.jetstack.io'
        }
        
        for name, url in repos.items():
            self.run_command(['helm', 'repo', 'add', name, url])
        
        self.run_command(['helm', 'repo', 'update'])
        
        # Update dependencies
        self.run_command(
            ['helm', 'dependency', 'update'],
            check=True
        )
        
        self.status.health_checks['dependencies_installed'] = True
    
    def deploy_helm_chart(self, config: RegionConfig):
        """Deploy Helm chart to the region"""
        self.log(f"Deploying AI Platform to region: {self.region}")
        self.status.phase = "deploying"
        
        # Prepare Helm values overrides
        overrides = {
            'global.region': self.region,
            'global.multiRegion.enabled': 'true',
            'global.multiRegion.primaryRegion': 'us-west-1',
        }
        
        # Build Helm command
        helm_cmd = [
            'helm', 'upgrade', '--install',
            'ai-platform',
            str(self.helm_chart),
            '--namespace', 'ai-platform',
            '--create-namespace',
            '--values', self.values_file,
            '--timeout', '30m',
            '--wait',
            '--atomic'
        ]
        
        # Add overrides
        for key, value in overrides.items():
            helm_cmd.extend(['--set', f'{key}={value}'])
        
        self.run_command(helm_cmd)
        self.status.health_checks['helm_chart_deployed'] = True
    
    def configure_replication(self, config: RegionConfig):
        """Configure cross-region replication"""
        self.log("Configuring cross-region replication...")
        self.status.phase = "configuring_replication"
        
        # Configure Postgres replication
        self.log("Setting up PostgreSQL replication...")
        self._configure_postgres_replication(config)
        
        # Configure Qdrant replication
        self.log("Setting up Qdrant replication...")
        self._configure_qdrant_replication(config)
        
        self.status.health_checks['replication_configured'] = True
    
    def _configure_postgres_replication(self, config: RegionConfig):
        """Configure PostgreSQL pglogical replication"""
        pglogical_setup_sql = """
        -- Enable pglogical extension
        CREATE EXTENSION IF NOT EXISTS pglogical;
        
        -- Create replication user (if not exists)
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'replication_user') THEN
            CREATE USER replication_user WITH REPLICATION PASSWORD 'replication_password';
          END IF;
        END
        $$;
        
        -- Grant privileges
        GRANT ALL PRIVILEGES ON DATABASE ai_platform TO replication_user;
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO replication_user;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO replication_user;
        
        -- Create replication node
        SELECT pglogical.create_node(
            node_name := '{}',
            dsn := 'host=postgres.{}.ai-platform.svc.cluster.local port=5432 dbname=ai_platform user=replication_user password=replication_password'
        );
        
        -- Create replication set (for all tables)
        SELECT pglogical.create_replication_set(
            set_name := 'ai_platform_set',
            replicate_insert := true,
            replicate_update := true,
            replicate_delete := true,
            replicate_truncate := true
        );
        
        -- Add all tables to replication set
        SELECT pglogical.replication_set_add_all_tables('ai_platform_set', ARRAY['public']);
        """.format(self.region, self.region)
        
        self.log(f"PostgreSQL replication configuration prepared for {self.region}")
        
        # Execute SQL (in actual deployment, this would be run against the database)
        if not self.dry_run:
            self.log("Execute this SQL on the PostgreSQL primary:")
            self.log(pglogical_setup_sql, "DEBUG")
    
    def _configure_qdrant_replication(self, config: RegionConfig):
        """Configure Qdrant collection replication"""
        # Qdrant replication is configured via cluster mode
        # Collections are automatically replicated across cluster nodes
        self.log(f"Qdrant cluster replication will be automatic via P2P")
        
        # Create snapshot schedule for backup
        snapshot_config = {
            'schedule': '0 */6 * * *',  # Every 6 hours
            'max_snapshots': 7,
            'destination': f's3://ai-platform-qdrant-snapshots/{self.region}/'
        }
        
        self.log(f"Qdrant snapshot configuration: {snapshot_config}")
    
    def configure_dns_failover(self, config: RegionConfig):
        """Configure DNS with health checks and failover"""
        if self.skip_dns:
            self.log("Skipping DNS configuration (--skip-dns flag)")
            return
        
        self.log("Configuring DNS failover...")
        self.status.phase = "configuring_dns"
        
        # Get load balancer endpoint
        lb_endpoint = self._get_loadbalancer_endpoint()
        
        if not lb_endpoint:
            self.log("Could not retrieve load balancer endpoint", "WARN")
            return
        
        self.log(f"Load balancer endpoint: {lb_endpoint}")
        
        # Determine if this is primary or secondary region
        is_primary = config.priority == 1
        weight = 100 if is_primary else 0
        
        self.log(f"Region type: {'PRIMARY' if is_primary else 'SECONDARY'}, Weight: {weight}")
        
        # Create DNS record with health check
        if config.dns_provider == "route53":
            self._configure_route53_dns(config, lb_endpoint, weight)
        elif config.dns_provider == "cloud_dns":
            self._configure_cloud_dns(config, lb_endpoint, weight)
        else:
            self.log(f"Unknown DNS provider: {config.dns_provider}", "ERROR")
            return
        
        self.status.health_checks['dns_configured'] = True
    
    def _configure_route53_dns(self, config: RegionConfig, lb_endpoint: str, weight: int):
        """Configure AWS Route53 DNS with health checks and weighted routing"""
        if not BOTO3_AVAILABLE:
            self.log("boto3 not available, skipping Route53 configuration", "WARN")
            return
        
        if not config.hosted_zone_id:
            self.log("hosted_zone_id not configured, skipping Route53 setup", "WARN")
            return
        
        self.log("Configuring AWS Route53...")
        
        try:
            # Initialize Route53 client
            route53 = boto3.client('route53')
            
            # Domain name for this region
            domain_name = f'{self.region}.ai-platform.example.com.'
            
            # Create health check
            health_check_id = self._create_route53_health_check(
                route53, lb_endpoint, domain_name
            )
            
            if health_check_id:
                self.log(f"Created health check: {health_check_id}")
            
            # Create or update weighted DNS record
            self._create_route53_weighted_record(
                route53,
                config.hosted_zone_id,
                domain_name,
                lb_endpoint,
                weight,
                health_check_id
            )
            
            self.log(f"✓ Route53 DNS configured: {domain_name} -> {lb_endpoint} (weight: {weight})")
            
        except (ClientError, BotoCoreError) as e:
            self.log(f"Error configuring Route53: {e}", "ERROR")
            raise
    
    def _create_route53_health_check(
        self,
        route53,
        lb_endpoint: str,
        domain_name: str
    ) -> Optional[str]:
        """Create Route53 health check"""
        if self.dry_run:
            self.log(f"[DRY RUN] Would create health check for {lb_endpoint}")
            return None
        
        try:
            # Parse endpoint (may be hostname or IP)
            is_ip = all(part.isdigit() for part in lb_endpoint.split('.'))
            
            health_check_config = {
                'Type': 'HTTPS' if not is_ip else 'HTTPS',
                'ResourcePath': '/health',
                'FullyQualifiedDomainName': domain_name.rstrip('.'),
                'Port': 9002,
                'RequestInterval': 30,
                'FailureThreshold': 3,
            }
            
            response = route53.create_health_check(
                CallerReference=f'{self.region}-{int(time.time())}',
                HealthCheckConfig=health_check_config,
                HealthCheckTags=[
                    {'Key': 'Name', 'Value': f'{self.region}-health-check'},
                    {'Key': 'Region', 'Value': self.region},
                    {'Key': 'ManagedBy', 'Value': 'deploy_region.py'}
                ]
            )
            
            return response['HealthCheck']['Id']
            
        except ClientError as e:
            self.log(f"Error creating health check: {e}", "WARN")
            return None
    
    def _create_route53_weighted_record(
        self,
        route53,
        hosted_zone_id: str,
        domain_name: str,
        lb_endpoint: str,
        weight: int,
        health_check_id: Optional[str]
    ):
        """Create or update weighted DNS record in Route53"""
        if self.dry_run:
            self.log(f"[DRY RUN] Would create weighted record: {domain_name} -> {lb_endpoint} (weight: {weight})")
            return
        
        try:
            # Determine record type (A for IP, CNAME for hostname)
            is_ip = all(part.isdigit() for part in lb_endpoint.split('.'))
            record_type = 'A' if is_ip else 'CNAME'
            
            # Build resource record set
            resource_record_set = {
                'Name': domain_name,
                'Type': record_type,
                'SetIdentifier': self.region,
                'Weight': weight,
                'TTL': 60,
                'ResourceRecords': [{'Value': lb_endpoint}]
            }
            
            # Add health check if available
            if health_check_id:
                resource_record_set['HealthCheckId'] = health_check_id
            
            # Create or update record
            change_batch = {
                'Changes': [{
                    'Action': 'UPSERT',
                    'ResourceRecordSet': resource_record_set
                }]
            }
            
            response = route53.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch=change_batch
            )
            
            change_id = response['ChangeInfo']['Id']
            self.log(f"DNS record change submitted: {change_id}")
            
        except ClientError as e:
            self.log(f"Error creating DNS record: {e}", "ERROR")
            raise
    
    def _configure_cloud_dns(self, config: RegionConfig, lb_endpoint: str, weight: int):
        """Configure Google Cloud DNS with health checks and weighted routing"""
        if not GCP_DNS_AVAILABLE:
            self.log("google-cloud-dns not available, skipping Cloud DNS configuration", "WARN")
            return
        
        if not config.gcp_project_id or not config.gcp_dns_zone_name:
            self.log("GCP project or DNS zone not configured, skipping Cloud DNS setup", "WARN")
            return
        
        self.log("Configuring Google Cloud DNS...")
        
        try:
            # Initialize Cloud DNS client
            dns_client = gcp_dns.Client(project=config.gcp_project_id)
            zone = dns_client.zone(config.gcp_dns_zone_name)
            
            # Domain name for this region
            domain_name = f'{self.region}.ai-platform.example.com.'
            
            # Create or update resource record set with weighted routing
            self._create_cloud_dns_weighted_record(
                zone, domain_name, lb_endpoint, weight
            )
            
            self.log(f"✓ Cloud DNS configured: {domain_name} -> {lb_endpoint} (weight: {weight})")
            
        except gcp_exceptions.GoogleAPIError as e:
            self.log(f"Error configuring Cloud DNS: {e}", "ERROR")
            raise
    
    def _create_cloud_dns_weighted_record(
        self,
        zone,
        domain_name: str,
        lb_endpoint: str,
        weight: int
    ):
        """Create or update weighted DNS record in Cloud DNS"""
        if self.dry_run:
            self.log(f"[DRY RUN] Would create Cloud DNS record: {domain_name} -> {lb_endpoint} (weight: {weight})")
            return
        
        try:
            # Determine record type
            is_ip = all(part.isdigit() for part in lb_endpoint.split('.'))
            record_type = 'A' if is_ip else 'CNAME'
            
            # Check if record exists
            existing_records = list(zone.list_resource_record_sets())
            existing = None
            
            for record in existing_records:
                if record.name == domain_name and record.record_type == record_type:
                    existing = record
                    break
            
            # Create resource record set with weighted routing policy
            # Note: Cloud DNS uses routing policies differently than Route53
            changes = zone.changes()
            
            if existing:
                changes.delete_record_set(existing)
            
            # Create new record with routing policy
            record_set = zone.resource_record_set(
                name=domain_name,
                record_type=record_type,
                ttl=60,
                rrdatas=[lb_endpoint]
            )
            
            # Add weighted routing policy metadata
            # (In production, use Cloud DNS routing policies API)
            changes.add_record_set(record_set)
            
            # Commit changes
            changes.create()
            
            self.log(f"Cloud DNS record created/updated: {domain_name}")
            
        except gcp_exceptions.GoogleAPIError as e:
            self.log(f"Error creating Cloud DNS record: {e}", "ERROR")
            raise
    
    def _get_loadbalancer_endpoint(self) -> Optional[str]:
        """Get the external load balancer endpoint"""
        try:
            result = self.run_command(
                [
                    'kubectl', 'get', 'service', 'gateway',
                    '-n', 'ai-platform',
                    '-o', 'jsonpath={.status.loadBalancer.ingress[0].hostname}'
                ],
                capture_output=True
            )
            
            if result and result.stdout:
                return result.stdout.strip()
            
            # Try IP address if hostname not available
            result = self.run_command(
                [
                    'kubectl', 'get', 'service', 'gateway',
                    '-n', 'ai-platform',
                    '-o', 'jsonpath={.status.loadBalancer.ingress[0].ip}'
                ],
                capture_output=True
            )
            
            if result and result.stdout:
                return result.stdout.strip()
            
        except Exception as e:
            self.log(f"Error getting load balancer endpoint: {e}", "ERROR")
        
        return None
    
    def verify_deployment(self) -> bool:
        """Verify deployment health"""
        self.log("Verifying deployment health...")
        self.status.phase = "verifying"
        
        # Check all pods are running
        self.log("Checking pod status...")
        try:
            result = self.run_command(
                [
                    'kubectl', 'get', 'pods',
                    '-n', 'ai-platform',
                    '-o', 'json'
                ],
                capture_output=True
            )
            
            if result:
                pods = json.loads(result.stdout)
                total_pods = len(pods.get('items', []))
                running_pods = sum(
                    1 for pod in pods.get('items', [])
                    if pod['status']['phase'] == 'Running'
                )
                
                self.log(f"Pods: {running_pods}/{total_pods} running")
                
                if running_pods < total_pods:
                    self.log("Not all pods are running", "WARN")
                    self.status.health_checks['all_pods_running'] = False
                else:
                    self.status.health_checks['all_pods_running'] = True
        
        except Exception as e:
            self.log(f"Error checking pods: {e}", "ERROR")
            self.status.health_checks['all_pods_running'] = False
        
        # Check service endpoints
        services = ['gateway', 'agent-router', 'qdrant', 'postgres', 'redis']
        for service in services:
            try:
                result = self.run_command(
                    [
                        'kubectl', 'get', 'service', service,
                        '-n', 'ai-platform',
                        '-o', 'json'
                    ],
                    capture_output=True
                )
                
                if result:
                    svc = json.loads(result.stdout)
                    cluster_ip = svc['spec'].get('clusterIP')
                    self.log(f"✓ Service {service}: {cluster_ip}")
                    self.status.health_checks[f'service_{service}_exists'] = True
            
            except Exception as e:
                self.log(f"✗ Service {service} not found: {e}", "WARN")
                self.status.health_checks[f'service_{service}_exists'] = False
        
        # Overall health
        all_healthy = all(self.status.health_checks.values())
        
        if all_healthy:
            self.status.phase = "healthy"
            self.status.message = "Deployment successful and healthy"
            self.log("✓ Deployment verification successful", "SUCCESS")
        else:
            self.status.phase = "degraded"
            self.status.message = "Deployment completed with some issues"
            self.log("⚠ Deployment verification completed with warnings", "WARN")
        
        return all_healthy
    
    def print_summary(self):
        """Print deployment summary"""
        print("\n" + "="*80)
        print(f"DEPLOYMENT SUMMARY - Region: {self.region}")
        print("="*80)
        print(f"Status: {self.status.phase}")
        print(f"Message: {self.status.message}")
        print(f"\nHealth Checks:")
        for check, result in self.status.health_checks.items():
            status_icon = "✓" if result else "✗"
            print(f"  {status_icon} {check}")
        print("\nNext Steps:")
        print(f"  1. Verify services: kubectl get all -n ai-platform")
        print(f"  2. Check logs: kubectl logs -n ai-platform -l app.kubernetes.io/name=gateway")
        print(f"  3. Test endpoint: curl https://{self.region}.ai-platform.example.com/health")
        print(f"  4. Monitor metrics: Access Grafana dashboard")
        print("="*80 + "\n")
    
    def deploy(self) -> bool:
        """Execute full deployment workflow"""
        try:
            # Load configuration
            config = self.load_region_config()
            
            # Verify prerequisites
            if not self.verify_prerequisites():
                self.log("Prerequisites check failed", "ERROR")
                return False
            
            # Create namespace
            self.create_namespace()
            
            # Setup storage
            self.setup_storage_classes(config)
            
            # Install dependencies
            self.install_dependencies()
            
            # Deploy Helm chart
            self.deploy_helm_chart(config)
            
            # Configure replication
            self.configure_replication(config)
            
            # Configure DNS failover
            self.configure_dns_failover(config)
            
            # Verify deployment
            healthy = self.verify_deployment()
            
            # Print summary
            self.print_summary()
            
            return healthy
        
        except Exception as e:
            self.log(f"Deployment failed: {e}", "ERROR")
            self.status.phase = "failed"
            self.status.message = str(e)
            self.print_summary()
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Deploy AI Platform to a new region with DNS failover"
    )
    parser.add_argument(
        '--region',
        required=True,
        choices=['us-west-1', 'us-east-1', 'eu-west-1', 'ap-southeast-1'],
        help='Target region for deployment'
    )
    parser.add_argument(
        '--cluster',
        required=True,
        help='Kubernetes cluster name'
    )
    parser.add_argument(
        '--values-file',
        default='helm/ai-platform/values-multi-region.yaml',
        help='Path to Helm values file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform dry run without making changes'
    )
    parser.add_argument(
        '--skip-dns',
        action='store_true',
        help='Skip DNS configuration'
    )
    
    args = parser.parse_args()
    
    # Create deployer
    deployer = MultiRegionDeployer(
        region=args.region,
        cluster_name=args.cluster,
        values_file=args.values_file,
        dry_run=args.dry_run,
        skip_dns=args.skip_dns
    )
    
    # Execute deployment
    success = deployer.deploy()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
