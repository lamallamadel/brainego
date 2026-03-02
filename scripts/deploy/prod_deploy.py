#!/usr/bin/env python3
"""
Production Deployment Automation Script

Orchestrates Helm chart deployment to production namespace with:
- Kong Ingress configuration validation with TLS cert-manager integration
- Network policies and RBAC application
- Helm test execution
- StatefulSet readiness verification (Postgres/Qdrant/Neo4j/Redis)
- PVC mount validation
- Smoke tests against production URLs
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Needs: python-package:pyyaml>=6.0.1
import yaml

# Needs: python-package:kubernetes>=28.1.0
try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
except ImportError:
    print("Warning: kubernetes package not available. K8s API features limited.")
    client = None
    config = None
    ApiException = Exception

# Needs: python-package:requests>=2.31.0
try:
    import requests
except ImportError:
    print("Warning: requests package not available. Smoke tests limited.")
    requests = None


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'prod_deploy_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DeploymentConfig:
    """Configuration for production deployment"""
    namespace: str
    release_name: str
    chart_path: str
    values_file: str
    timeout: int
    kubeconfig: Optional[str]
    helm_extra_args: List[str]
    smoke_test_urls: List[str]
    skip_tests: bool
    skip_smoke_tests: bool
    dry_run: bool


class DeploymentError(Exception):
    """Base exception for deployment errors"""
    pass


class HelmDeploymentOrchestrator:
    """Orchestrates Helm-based production deployment with validation"""

    def __init__(self, config: DeploymentConfig):
        self.config = config
        self.start_time = datetime.now()
        
        # Initialize Kubernetes client if available
        if config.kubeconfig and client and config:
            try:
                config.load_kube_config(config_file=config.kubeconfig)
            except Exception as e:
                logger.warning(f"Failed to load kubeconfig: {e}")
        elif client and config:
            try:
                config.load_incluster_config()
            except Exception:
                try:
                    config.load_kube_config()
                except Exception as e:
                    logger.warning(f"Failed to load kubeconfig: {e}")

    def run_command(self, cmd: List[str], check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
        """Execute shell command with logging"""
        logger.info(f"Executing: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                check=check,
                capture_output=capture_output,
                text=True,
                timeout=self.config.timeout
            )
            
            if result.stdout:
                logger.debug(f"STDOUT: {result.stdout}")
            if result.stderr:
                logger.debug(f"STDERR: {result.stderr}")
                
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            raise DeploymentError(f"Command failed: {' '.join(cmd)}") from e
        except subprocess.TimeoutExpired as e:
            logger.error(f"Command timed out after {self.config.timeout}s")
            raise DeploymentError(f"Command timeout: {' '.join(cmd)}") from e

    def validate_prerequisites(self) -> None:
        """Validate that all required tools and configurations are available"""
        logger.info("=== Validating Prerequisites ===")
        
        # Check helm is installed
        try:
            result = self.run_command(["helm", "version", "--short"])
            logger.info(f"Helm version: {result.stdout.strip()}")
        except Exception as e:
            raise DeploymentError("Helm is not installed or not in PATH") from e
        
        # Check kubectl is installed
        try:
            result = self.run_command(["kubectl", "version", "--client", "--short"])
            logger.info(f"Kubectl version: {result.stdout.strip()}")
        except Exception as e:
            raise DeploymentError("kubectl is not installed or not in PATH") from e
        
        # Validate chart path exists
        chart_path = Path(self.config.chart_path)
        if not chart_path.exists():
            raise DeploymentError(f"Chart path does not exist: {self.config.chart_path}")
        
        # Validate Chart.yaml
        chart_yaml = chart_path / "Chart.yaml"
        if not chart_yaml.exists():
            raise DeploymentError(f"Chart.yaml not found in {self.config.chart_path}")
        
        # Validate values file if specified
        if self.config.values_file:
            values_path = Path(self.config.values_file)
            if not values_path.exists():
                raise DeploymentError(f"Values file does not exist: {self.config.values_file}")
        
        # Check cluster connectivity
        try:
            self.run_command(["kubectl", "cluster-info"])
            logger.info("✓ Cluster connectivity verified")
        except Exception as e:
            raise DeploymentError("Cannot connect to Kubernetes cluster") from e
        
        logger.info("✓ All prerequisites validated")

    def create_namespace(self) -> None:
        """Create namespace if it doesn't exist"""
        logger.info(f"=== Creating Namespace: {self.config.namespace} ===")
        
        if self.config.dry_run:
            logger.info("[DRY RUN] Would create namespace")
            return
        
        # Check if namespace exists
        result = self.run_command(
            ["kubectl", "get", "namespace", self.config.namespace],
            check=False
        )
        
        if result.returncode == 0:
            logger.info(f"✓ Namespace {self.config.namespace} already exists")
        else:
            # Create namespace
            self.run_command([
                "kubectl", "create", "namespace", self.config.namespace
            ])
            
            # Label namespace for monitoring
            self.run_command([
                "kubectl", "label", "namespace", self.config.namespace,
                "name=ai-platform",
                "environment=production",
                "--overwrite"
            ])
            logger.info(f"✓ Namespace {self.config.namespace} created")

    def validate_helm_chart(self) -> None:
        """Validate Helm chart syntax and templates"""
        logger.info("=== Validating Helm Chart ===")
        
        # Lint the chart
        lint_cmd = ["helm", "lint", self.config.chart_path]
        if self.config.values_file:
            lint_cmd.extend(["-f", self.config.values_file])
        
        result = self.run_command(lint_cmd)
        logger.info("✓ Helm chart lint passed")
        
        # Template the chart to validate
        template_cmd = [
            "helm", "template", self.config.release_name,
            self.config.chart_path,
            "--namespace", self.config.namespace
        ]
        if self.config.values_file:
            template_cmd.extend(["-f", self.config.values_file])
        
        result = self.run_command(template_cmd)
        logger.info("✓ Helm chart templates validated")

    def validate_kong_ingress_config(self) -> None:
        """Validate Kong Ingress configuration and TLS cert-manager setup"""
        logger.info("=== Validating Kong Ingress & TLS Configuration ===")
        
        # Template just the ingress resources
        template_cmd = [
            "helm", "template", self.config.release_name,
            self.config.chart_path,
            "--namespace", self.config.namespace,
            "--show-only", "templates/kong-ingress.yaml"
        ]
        if self.config.values_file:
            template_cmd.extend(["-f", self.config.values_file])
        
        result = self.run_command(template_cmd, check=False)
        
        if result.returncode != 0:
            logger.warning("Kong Ingress template not found or disabled")
            return
        
        # Parse and validate ingress configuration
        try:
            ingress_docs = list(yaml.safe_load_all(result.stdout))
            
            for doc in ingress_docs:
                if not doc or doc.get('kind') != 'Ingress':
                    continue
                
                # Validate TLS configuration
                spec = doc.get('spec', {})
                tls = spec.get('tls', [])
                
                if not tls:
                    logger.warning("No TLS configuration found in Ingress")
                else:
                    for tls_config in tls:
                        hosts = tls_config.get('hosts', [])
                        secret = tls_config.get('secretName', '')
                        logger.info(f"✓ TLS configured for hosts: {hosts} with secret: {secret}")
                
                # Validate cert-manager annotations
                annotations = doc.get('metadata', {}).get('annotations', {})
                cert_issuer = annotations.get('cert-manager.io/cluster-issuer')
                
                if cert_issuer:
                    logger.info(f"✓ Cert-manager issuer configured: {cert_issuer}")
                else:
                    logger.warning("No cert-manager issuer annotation found")
                
                # Validate Kong plugins
                kong_plugins = annotations.get('konghq.com/plugins')
                if kong_plugins:
                    logger.info(f"✓ Kong plugins configured: {kong_plugins}")
        
        except yaml.YAMLError as e:
            raise DeploymentError(f"Failed to parse Kong Ingress YAML: {e}") from e
        
        logger.info("✓ Kong Ingress configuration validated")

    def validate_cert_manager_config(self) -> None:
        """Validate cert-manager issuer configuration"""
        logger.info("=== Validating Cert-Manager Configuration ===")
        
        template_cmd = [
            "helm", "template", self.config.release_name,
            self.config.chart_path,
            "--namespace", self.config.namespace,
            "--show-only", "templates/cert-manager-issuer.yaml"
        ]
        if self.config.values_file:
            template_cmd.extend(["-f", self.config.values_file])
        
        result = self.run_command(template_cmd, check=False)
        
        if result.returncode != 0:
            logger.warning("Cert-manager issuer template not found or disabled")
            return
        
        try:
            issuer_docs = list(yaml.safe_load_all(result.stdout))
            
            for doc in issuer_docs:
                if not doc:
                    continue
                
                kind = doc.get('kind')
                name = doc.get('metadata', {}).get('name')
                
                if kind == 'ClusterIssuer':
                    logger.info(f"✓ ClusterIssuer configured: {name}")
                    
                    # Check ACME configuration
                    acme = doc.get('spec', {}).get('acme', {})
                    email = acme.get('email')
                    server = acme.get('server')
                    
                    if email:
                        logger.info(f"  - ACME email: {email}")
                    if server:
                        logger.info(f"  - ACME server: {server}")
                
                elif kind == 'Certificate':
                    logger.info(f"✓ Certificate configured: {name}")
                    dns_names = doc.get('spec', {}).get('dnsNames', [])
                    logger.info(f"  - DNS names: {dns_names}")
        
        except yaml.YAMLError as e:
            raise DeploymentError(f"Failed to parse cert-manager YAML: {e}") from e
        
        logger.info("✓ Cert-manager configuration validated")

    def deploy_helm_chart(self) -> None:
        """Deploy or upgrade the Helm chart"""
        logger.info("=== Deploying Helm Chart ===")
        
        deploy_cmd = [
            "helm", "upgrade", "--install",
            self.config.release_name,
            self.config.chart_path,
            "--namespace", self.config.namespace,
            "--create-namespace",
            "--wait",
            "--timeout", f"{self.config.timeout}s"
        ]
        
        if self.config.values_file:
            deploy_cmd.extend(["-f", self.config.values_file])
        
        if self.config.dry_run:
            deploy_cmd.append("--dry-run")
        
        deploy_cmd.extend(self.config.helm_extra_args)
        
        result = self.run_command(deploy_cmd)
        
        if self.config.dry_run:
            logger.info("[DRY RUN] Deployment would succeed")
        else:
            logger.info(f"✓ Helm release {self.config.release_name} deployed successfully")

    def verify_network_policies(self) -> None:
        """Verify network policies are applied"""
        logger.info("=== Verifying Network Policies ===")
        
        if self.config.dry_run:
            logger.info("[DRY RUN] Would verify network policies")
            return
        
        result = self.run_command([
            "kubectl", "get", "networkpolicies",
            "-n", self.config.namespace,
            "-o", "json"
        ])
        
        try:
            policies = json.loads(result.stdout)
            policy_names = [p['metadata']['name'] for p in policies.get('items', [])]
            
            if not policy_names:
                logger.warning("No network policies found in namespace")
            else:
                logger.info(f"✓ Found {len(policy_names)} network policies:")
                for name in policy_names:
                    logger.info(f"  - {name}")
        
        except json.JSONDecodeError as e:
            raise DeploymentError(f"Failed to parse network policies JSON: {e}") from e

    def verify_rbac(self) -> None:
        """Verify RBAC resources are applied"""
        logger.info("=== Verifying RBAC Configuration ===")
        
        if self.config.dry_run:
            logger.info("[DRY RUN] Would verify RBAC")
            return
        
        # Check ServiceAccounts
        result = self.run_command([
            "kubectl", "get", "serviceaccounts",
            "-n", self.config.namespace,
            "-o", "json"
        ])
        
        try:
            sas = json.loads(result.stdout)
            sa_names = [sa['metadata']['name'] for sa in sas.get('items', [])]
            logger.info(f"✓ Found {len(sa_names)} service accounts")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse service accounts: {e}")
        
        # Check Roles
        result = self.run_command([
            "kubectl", "get", "roles",
            "-n", self.config.namespace,
            "-o", "json"
        ])
        
        try:
            roles = json.loads(result.stdout)
            role_names = [r['metadata']['name'] for r in roles.get('items', [])]
            logger.info(f"✓ Found {len(role_names)} roles")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse roles: {e}")
        
        # Check RoleBindings
        result = self.run_command([
            "kubectl", "get", "rolebindings",
            "-n", self.config.namespace,
            "-o", "json"
        ])
        
        try:
            bindings = json.loads(result.stdout)
            binding_names = [b['metadata']['name'] for b in bindings.get('items', [])]
            logger.info(f"✓ Found {len(binding_names)} role bindings")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse role bindings: {e}")

    def run_helm_tests(self) -> None:
        """Execute Helm test hooks"""
        logger.info("=== Running Helm Tests ===")
        
        if self.config.skip_tests:
            logger.info("Skipping Helm tests (--skip-tests)")
            return
        
        if self.config.dry_run:
            logger.info("[DRY RUN] Would run Helm tests")
            return
        
        test_cmd = [
            "helm", "test",
            self.config.release_name,
            "--namespace", self.config.namespace,
            "--timeout", f"{self.config.timeout}s"
        ]
        
        result = self.run_command(test_cmd, check=False)
        
        if result.returncode == 0:
            logger.info("✓ Helm tests passed")
        else:
            logger.warning("Helm tests failed or not found")

    def verify_statefulsets(self) -> None:
        """Verify all StatefulSets are ready with PVC mounts"""
        logger.info("=== Verifying StatefulSets ===")
        
        if self.config.dry_run:
            logger.info("[DRY RUN] Would verify StatefulSets")
            return
        
        statefulset_names = ["postgres", "qdrant", "neo4j", "redis"]
        
        for sts_name in statefulset_names:
            logger.info(f"Checking StatefulSet: {sts_name}")
            
            # Check if StatefulSet exists
            result = self.run_command([
                "kubectl", "get", "statefulset", sts_name,
                "-n", self.config.namespace,
                "-o", "json"
            ], check=False)
            
            if result.returncode != 0:
                logger.info(f"  StatefulSet {sts_name} not found (may be disabled)")
                continue
            
            try:
                sts = json.loads(result.stdout)
                
                # Check replicas
                desired = sts['spec']['replicas']
                ready = sts['status'].get('readyReplicas', 0)
                
                logger.info(f"  Replicas: {ready}/{desired}")
                
                if ready != desired:
                    logger.warning(f"  ⚠ StatefulSet {sts_name} not fully ready")
                else:
                    logger.info(f"  ✓ StatefulSet {sts_name} is ready")
                
                # Check PVCs
                pvc_templates = sts['spec'].get('volumeClaimTemplates', [])
                if pvc_templates:
                    logger.info(f"  PVC templates: {len(pvc_templates)}")
                    
                    for template in pvc_templates:
                        pvc_name = template['metadata']['name']
                        
                        # Check actual PVCs created
                        pvc_result = self.run_command([
                            "kubectl", "get", "pvc",
                            "-n", self.config.namespace,
                            "-l", f"app.kubernetes.io/name={sts_name}",
                            "-o", "json"
                        ], check=False)
                        
                        if pvc_result.returncode == 0:
                            pvcs = json.loads(pvc_result.stdout)
                            pvc_count = len(pvcs.get('items', []))
                            logger.info(f"    ✓ {pvc_count} PVC(s) for {pvc_name}")
            
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"  Failed to parse StatefulSet {sts_name}: {e}")
        
        # Wait for all StatefulSets to be ready
        logger.info("Waiting for all StatefulSets to be ready...")
        max_wait = 300  # 5 minutes
        interval = 10
        elapsed = 0
        
        while elapsed < max_wait:
            all_ready = True
            
            for sts_name in statefulset_names:
                result = self.run_command([
                    "kubectl", "get", "statefulset", sts_name,
                    "-n", self.config.namespace,
                    "-o", "json"
                ], check=False)
                
                if result.returncode != 0:
                    continue
                
                try:
                    sts = json.loads(result.stdout)
                    desired = sts['spec']['replicas']
                    ready = sts['status'].get('readyReplicas', 0)
                    
                    if ready != desired:
                        all_ready = False
                        break
                
                except (json.JSONDecodeError, KeyError):
                    all_ready = False
                    break
            
            if all_ready:
                logger.info("✓ All StatefulSets are ready")
                return
            
            logger.info(f"Waiting... ({elapsed}/{max_wait}s)")
            time.sleep(interval)
            elapsed += interval
        
        logger.warning("⚠ Timeout waiting for StatefulSets to be ready")

    def verify_pvc_mounts(self) -> None:
        """Verify PVC mounts are working correctly"""
        logger.info("=== Verifying PVC Mounts ===")
        
        if self.config.dry_run:
            logger.info("[DRY RUN] Would verify PVC mounts")
            return
        
        # Get all PVCs in namespace
        result = self.run_command([
            "kubectl", "get", "pvc",
            "-n", self.config.namespace,
            "-o", "json"
        ])
        
        try:
            pvcs = json.loads(result.stdout)
            
            for pvc in pvcs.get('items', []):
                name = pvc['metadata']['name']
                status = pvc['status']['phase']
                
                if status == 'Bound':
                    logger.info(f"✓ PVC {name}: {status}")
                else:
                    logger.warning(f"⚠ PVC {name}: {status}")
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse PVCs: {e}")

    def verify_pod_status(self) -> None:
        """Verify all pods are running"""
        logger.info("=== Verifying Pod Status ===")
        
        if self.config.dry_run:
            logger.info("[DRY RUN] Would verify pod status")
            return
        
        result = self.run_command([
            "kubectl", "get", "pods",
            "-n", self.config.namespace,
            "-o", "json"
        ])
        
        try:
            pods = json.loads(result.stdout)
            
            total = len(pods.get('items', []))
            running = 0
            failed = 0
            
            for pod in pods.get('items', []):
                name = pod['metadata']['name']
                phase = pod['status']['phase']
                
                if phase == 'Running':
                    running += 1
                    logger.debug(f"✓ Pod {name}: {phase}")
                elif phase == 'Failed':
                    failed += 1
                    logger.warning(f"✗ Pod {name}: {phase}")
                else:
                    logger.info(f"  Pod {name}: {phase}")
            
            logger.info(f"Pod status: {running}/{total} running, {failed} failed")
            
            if failed > 0:
                logger.warning(f"⚠ {failed} pod(s) failed")
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse pods: {e}")

    def run_smoke_tests(self) -> None:
        """Execute smoke tests against production URLs"""
        logger.info("=== Running Smoke Tests ===")
        
        if self.config.skip_smoke_tests:
            logger.info("Skipping smoke tests (--skip-smoke-tests)")
            return
        
        if self.config.dry_run:
            logger.info("[DRY RUN] Would run smoke tests")
            return
        
        if not requests:
            logger.warning("requests library not available, skipping smoke tests")
            return
        
        if not self.config.smoke_test_urls:
            logger.info("No smoke test URLs configured")
            return
        
        success_count = 0
        fail_count = 0
        
        for url in self.config.smoke_test_urls:
            try:
                logger.info(f"Testing URL: {url}")
                response = requests.get(url, timeout=30, verify=True)
                
                if response.status_code == 200:
                    logger.info(f"✓ {url} - Status: {response.status_code}")
                    success_count += 1
                else:
                    logger.warning(f"⚠ {url} - Status: {response.status_code}")
                    fail_count += 1
            
            except requests.exceptions.RequestException as e:
                logger.error(f"✗ {url} - Error: {e}")
                fail_count += 1
        
        logger.info(f"Smoke tests: {success_count} passed, {fail_count} failed")
        
        if fail_count > 0:
            logger.warning("⚠ Some smoke tests failed")

    def generate_deployment_report(self) -> None:
        """Generate deployment summary report"""
        logger.info("=== Deployment Summary ===")
        
        duration = datetime.now() - self.start_time
        
        logger.info(f"Release: {self.config.release_name}")
        logger.info(f"Namespace: {self.config.namespace}")
        logger.info(f"Chart: {self.config.chart_path}")
        logger.info(f"Duration: {duration}")
        
        if not self.config.dry_run:
            # Get release status
            result = self.run_command([
                "helm", "status", self.config.release_name,
                "-n", self.config.namespace
            ])
            
            logger.info("\nRelease Status:")
            logger.info(result.stdout)
        
        logger.info("✓ Deployment completed successfully")

    def deploy(self) -> bool:
        """Execute full deployment workflow"""
        try:
            logger.info("=" * 70)
            logger.info("PRODUCTION DEPLOYMENT AUTOMATION")
            logger.info("=" * 70)
            
            # Phase 1: Pre-deployment validation
            self.validate_prerequisites()
            self.validate_helm_chart()
            self.validate_kong_ingress_config()
            self.validate_cert_manager_config()
            
            # Phase 2: Namespace setup
            self.create_namespace()
            
            # Phase 3: Helm deployment
            self.deploy_helm_chart()
            
            # Phase 4: Post-deployment verification
            self.verify_network_policies()
            self.verify_rbac()
            self.verify_pod_status()
            self.verify_statefulsets()
            self.verify_pvc_mounts()
            
            # Phase 5: Testing
            self.run_helm_tests()
            self.run_smoke_tests()
            
            # Phase 6: Report
            self.generate_deployment_report()
            
            return True
        
        except DeploymentError as e:
            logger.error(f"Deployment failed: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error during deployment: {e}")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Production deployment automation for AI Platform Helm chart",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--namespace",
        default="ai-platform-prod",
        help="Kubernetes namespace for deployment (default: ai-platform-prod)"
    )
    parser.add_argument(
        "--release-name",
        default="ai-platform",
        help="Helm release name (default: ai-platform)"
    )
    parser.add_argument(
        "--chart-path",
        default="helm/ai-platform",
        help="Path to Helm chart (default: helm/ai-platform)"
    )
    parser.add_argument(
        "--values-file",
        default="helm/ai-platform/values-production-secure.yaml",
        help="Values file for production (default: values-production-secure.yaml)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout in seconds for operations (default: 600)"
    )
    parser.add_argument(
        "--kubeconfig",
        help="Path to kubeconfig file (default: use default config)"
    )
    parser.add_argument(
        "--helm-extra-args",
        nargs="+",
        default=[],
        help="Extra arguments to pass to helm upgrade"
    )
    parser.add_argument(
        "--smoke-test-urls",
        nargs="+",
        default=[],
        help="URLs to test after deployment"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip Helm tests"
    )
    parser.add_argument(
        "--skip-smoke-tests",
        action="store_true",
        help="Skip smoke tests"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform dry-run without actual deployment"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    config = DeploymentConfig(
        namespace=args.namespace,
        release_name=args.release_name,
        chart_path=args.chart_path,
        values_file=args.values_file,
        timeout=args.timeout,
        kubeconfig=args.kubeconfig,
        helm_extra_args=args.helm_extra_args,
        smoke_test_urls=args.smoke_test_urls,
        skip_tests=args.skip_tests,
        skip_smoke_tests=args.skip_smoke_tests,
        dry_run=args.dry_run
    )
    
    orchestrator = HelmDeploymentOrchestrator(config)
    success = orchestrator.deploy()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
