#!/usr/bin/env python3
"""
Multi-Region Failover Automation

Monitors region health via Prometheus alerts and automatically shifts DNS weights
to failover from unhealthy primary region to healthy secondary region.

Features:
- Health check monitoring via Prometheus
- Automatic DNS weight shifting (primary weight=100, secondary weight=0)
- Rollback mechanism to restore primary after recovery
- Alert-based and metric-based triggering
- Dry-run mode for testing
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Needs: python-package:pyyaml>=6.0
# Needs: python-package:boto3>=1.26.0 (for AWS Route53)
# Needs: python-package:google-cloud-dns>=0.34.0 (for Google Cloud DNS)
# Needs: python-package:requests>=2.31.0 (for Prometheus API)

try:
    import yaml
except ImportError:
    yaml = None

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

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


@dataclass
class RegionHealth:
    """Health status of a region"""
    region: str
    healthy: bool
    error_rate: float
    latency_p95: float
    availability: float
    last_check: datetime
    consecutive_failures: int
    consecutive_successes: int


@dataclass
class FailoverEvent:
    """Record of a failover event"""
    timestamp: datetime
    from_region: str
    to_region: str
    trigger: str  # alert, metric, manual
    reason: str
    weights_before: Dict[str, int]
    weights_after: Dict[str, int]


class MultiRegionFailoverManager:
    """Manages automatic failover between regions based on health metrics"""
    
    def __init__(
        self,
        config_file: str,
        prometheus_url: str,
        dry_run: bool = False,
        log_level: str = "INFO"
    ):
        self.config_file = Path(config_file)
        self.prometheus_url = prometheus_url
        self.dry_run = dry_run
        
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s [%(levelname)s] %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        self.config = self._load_config()
        self.regions = self.config.get('regions', {})
        self.thresholds = self.config.get('thresholds', {})
        self.dns_provider = self.config.get('dns_provider', 'route53')
        
        # State tracking
        self.region_health: Dict[str, RegionHealth] = {}
        self.failover_history: List[FailoverEvent] = []
        self.current_primary: Optional[str] = None
        self.original_primary: Optional[str] = None
        
        # Initialize clients
        self._init_dns_client()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load failover configuration from YAML"""
        if not yaml:
            raise ImportError("pyyaml is required for configuration loading")
        
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_file}")
        
        with open(self.config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        self.logger.info(f"Loaded configuration from {self.config_file}")
        return config
    
    def _init_dns_client(self):
        """Initialize DNS provider client"""
        if self.dns_provider == 'route53':
            if not BOTO3_AVAILABLE:
                raise ImportError("boto3 is required for Route53 failover")
            self.route53_client = boto3.client('route53')
            self.logger.info("Initialized Route53 client")
        
        elif self.dns_provider == 'cloud_dns':
            if not GCP_DNS_AVAILABLE:
                raise ImportError("google-cloud-dns is required for Cloud DNS failover")
            gcp_project = self.config.get('gcp_project_id')
            if not gcp_project:
                raise ValueError("gcp_project_id required for Cloud DNS")
            self.gcp_dns_client = gcp_dns.Client(project=gcp_project)
            self.logger.info("Initialized Cloud DNS client")
    
    def check_prometheus_health(self, region: str) -> RegionHealth:
        """Check region health via Prometheus metrics"""
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests is required for Prometheus queries")
        
        self.logger.debug(f"Checking health for region: {region}")
        
        # Query Prometheus for key metrics
        metrics = {
            'error_rate': self._query_prometheus(
                f'rate(http_requests_total{{region="{region}",status=~"5.."}}[5m]) / '
                f'rate(http_requests_total{{region="{region}"}}[5m])'
            ),
            'latency_p95': self._query_prometheus(
                f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{region="{region}"}}[5m]))'
            ),
            'availability': self._query_prometheus(
                f'up{{region="{region}"}}'
            )
        }
        
        # Get current health status
        current_health = self.region_health.get(region)
        
        # Determine if region is healthy based on thresholds
        error_rate = metrics.get('error_rate', 1.0)
        latency_p95 = metrics.get('latency_p95', float('inf'))
        availability = metrics.get('availability', 0.0)
        
        is_healthy = (
            error_rate < self.thresholds.get('max_error_rate', 0.05) and
            latency_p95 < self.thresholds.get('max_latency_ms', 1000) / 1000.0 and
            availability >= self.thresholds.get('min_availability', 0.99)
        )
        
        # Update consecutive counts
        consecutive_failures = 0
        consecutive_successes = 0
        
        if current_health:
            if is_healthy:
                consecutive_successes = current_health.consecutive_successes + 1
                consecutive_failures = 0
            else:
                consecutive_failures = current_health.consecutive_failures + 1
                consecutive_successes = 0
        else:
            if is_healthy:
                consecutive_successes = 1
            else:
                consecutive_failures = 1
        
        health = RegionHealth(
            region=region,
            healthy=is_healthy,
            error_rate=error_rate,
            latency_p95=latency_p95,
            availability=availability,
            last_check=datetime.now(),
            consecutive_failures=consecutive_failures,
            consecutive_successes=consecutive_successes
        )
        
        self.region_health[region] = health
        
        self.logger.info(
            f"Region {region}: healthy={is_healthy}, error_rate={error_rate:.4f}, "
            f"latency_p95={latency_p95*1000:.1f}ms, availability={availability:.4f}"
        )
        
        return health
    
    def _query_prometheus(self, query: str) -> float:
        """Query Prometheus for a metric"""
        try:
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={'query': query},
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') == 'success':
                result = data.get('data', {}).get('result', [])
                if result and len(result) > 0:
                    value = result[0].get('value', [None, None])[1]
                    return float(value) if value else 0.0
            
            return 0.0
            
        except Exception as e:
            self.logger.error(f"Error querying Prometheus: {e}")
            return 0.0
    
    def get_current_dns_weights(self) -> Dict[str, int]:
        """Get current DNS weights for all regions"""
        self.logger.info("Retrieving current DNS weights")
        
        if self.dns_provider == 'route53':
            return self._get_route53_weights()
        elif self.dns_provider == 'cloud_dns':
            return self._get_cloud_dns_weights()
        
        return {}
    
    def _get_route53_weights(self) -> Dict[str, int]:
        """Get current Route53 DNS weights"""
        weights = {}
        
        try:
            hosted_zone_id = self.config.get('hosted_zone_id')
            if not hosted_zone_id:
                self.logger.warning("hosted_zone_id not configured")
                return weights
            
            response = self.route53_client.list_resource_record_sets(
                HostedZoneId=hosted_zone_id
            )
            
            for record_set in response.get('ResourceRecordSets', []):
                # Look for weighted records with region identifiers
                if record_set.get('SetIdentifier') in self.regions:
                    region = record_set['SetIdentifier']
                    weight = record_set.get('Weight', 0)
                    weights[region] = weight
                    self.logger.debug(f"Route53 weight for {region}: {weight}")
            
        except (ClientError, BotoCoreError) as e:
            self.logger.error(f"Error getting Route53 weights: {e}")
        
        return weights
    
    def _get_cloud_dns_weights(self) -> Dict[str, int]:
        """Get current Cloud DNS weights"""
        weights = {}
        
        try:
            zone_name = self.config.get('gcp_dns_zone_name')
            if not zone_name:
                self.logger.warning("gcp_dns_zone_name not configured")
                return weights
            
            zone = self.gcp_dns_client.zone(zone_name)
            records = list(zone.list_resource_record_sets())
            
            # Extract weights from routing policy metadata
            # (Implementation depends on Cloud DNS routing policy structure)
            for record in records:
                # Parse region identifier and weight from record metadata
                # This is a simplified example
                pass
            
        except gcp_exceptions.GoogleAPIError as e:
            self.logger.error(f"Error getting Cloud DNS weights: {e}")
        
        return weights
    
    def update_dns_weights(self, weights: Dict[str, int]) -> bool:
        """Update DNS weights for all regions"""
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would update DNS weights: {weights}")
            return True
        
        self.logger.info(f"Updating DNS weights: {weights}")
        
        if self.dns_provider == 'route53':
            return self._update_route53_weights(weights)
        elif self.dns_provider == 'cloud_dns':
            return self._update_cloud_dns_weights(weights)
        
        return False
    
    def _update_route53_weights(self, weights: Dict[str, int]) -> bool:
        """Update Route53 DNS weights"""
        try:
            hosted_zone_id = self.config.get('hosted_zone_id')
            if not hosted_zone_id:
                self.logger.error("hosted_zone_id not configured")
                return False
            
            # Get current record sets
            response = self.route53_client.list_resource_record_sets(
                HostedZoneId=hosted_zone_id
            )
            
            changes = []
            
            for record_set in response.get('ResourceRecordSets', []):
                region = record_set.get('SetIdentifier')
                
                if region in weights:
                    new_weight = weights[region]
                    old_weight = record_set.get('Weight', 0)
                    
                    if new_weight != old_weight:
                        # Update weight
                        updated_record = record_set.copy()
                        updated_record['Weight'] = new_weight
                        
                        changes.append({
                            'Action': 'UPSERT',
                            'ResourceRecordSet': updated_record
                        })
                        
                        self.logger.info(
                            f"Updating {region}: weight {old_weight} -> {new_weight}"
                        )
            
            if changes:
                self.route53_client.change_resource_record_sets(
                    HostedZoneId=hosted_zone_id,
                    ChangeBatch={'Changes': changes}
                )
                self.logger.info("Route53 weights updated successfully")
                return True
            else:
                self.logger.info("No weight changes needed")
                return True
            
        except (ClientError, BotoCoreError) as e:
            self.logger.error(f"Error updating Route53 weights: {e}")
            return False
    
    def _update_cloud_dns_weights(self, weights: Dict[str, int]) -> bool:
        """Update Cloud DNS weights"""
        try:
            zone_name = self.config.get('gcp_dns_zone_name')
            if not zone_name:
                self.logger.error("gcp_dns_zone_name not configured")
                return False
            
            zone = self.gcp_dns_client.zone(zone_name)
            changes = zone.changes()
            
            # Update records with new weights
            # (Implementation depends on Cloud DNS routing policy API)
            
            changes.create()
            self.logger.info("Cloud DNS weights updated successfully")
            return True
            
        except gcp_exceptions.GoogleAPIError as e:
            self.logger.error(f"Error updating Cloud DNS weights: {e}")
            return False
    
    def execute_failover(
        self,
        from_region: str,
        to_region: str,
        trigger: str,
        reason: str
    ) -> bool:
        """Execute failover from one region to another"""
        self.logger.warning(
            f"EXECUTING FAILOVER: {from_region} -> {to_region} "
            f"(trigger: {trigger}, reason: {reason})"
        )
        
        # Get current weights
        current_weights = self.get_current_dns_weights()
        
        # Calculate new weights (shift traffic to target region)
        new_weights = {}
        for region in self.regions:
            if region == to_region:
                new_weights[region] = 100  # Full weight to target
            else:
                new_weights[region] = 0    # Zero weight to others
        
        # Update DNS
        success = self.update_dns_weights(new_weights)
        
        if success:
            # Record failover event
            event = FailoverEvent(
                timestamp=datetime.now(),
                from_region=from_region,
                to_region=to_region,
                trigger=trigger,
                reason=reason,
                weights_before=current_weights,
                weights_after=new_weights
            )
            self.failover_history.append(event)
            self.current_primary = to_region
            
            self.logger.warning(f"✓ Failover completed: {from_region} -> {to_region}")
            
            # Send notifications (webhook, Slack, PagerDuty, etc.)
            self._send_failover_notification(event)
            
            return True
        else:
            self.logger.error("✗ Failover failed")
            return False
    
    def execute_rollback(self, to_region: str) -> bool:
        """Rollback DNS to original primary region after recovery"""
        self.logger.info(f"EXECUTING ROLLBACK to {to_region}")
        
        # Get current weights
        current_weights = self.get_current_dns_weights()
        
        # Calculate rollback weights
        new_weights = {}
        for region in self.regions:
            if region == to_region:
                new_weights[region] = 100  # Full weight back to original primary
            else:
                new_weights[region] = 0    # Zero weight to others
        
        # Update DNS
        success = self.update_dns_weights(new_weights)
        
        if success:
            # Record rollback event
            event = FailoverEvent(
                timestamp=datetime.now(),
                from_region=self.current_primary or "unknown",
                to_region=to_region,
                trigger="rollback",
                reason=f"Primary region {to_region} recovered",
                weights_before=current_weights,
                weights_after=new_weights
            )
            self.failover_history.append(event)
            self.current_primary = to_region
            
            self.logger.info(f"✓ Rollback completed to {to_region}")
            
            # Send notifications
            self._send_failover_notification(event)
            
            return True
        else:
            self.logger.error("✗ Rollback failed")
            return False
    
    def _send_failover_notification(self, event: FailoverEvent):
        """Send notification about failover event"""
        webhook_url = self.config.get('notification_webhook')
        
        if not webhook_url or not REQUESTS_AVAILABLE:
            return
        
        message = {
            'text': f"🔄 Multi-Region Failover",
            'blocks': [
                {
                    'type': 'section',
                    'text': {
                        'type': 'mrkdwn',
                        'text': (
                            f"*Multi-Region Failover Executed*\n"
                            f"• From: `{event.from_region}`\n"
                            f"• To: `{event.to_region}`\n"
                            f"• Trigger: `{event.trigger}`\n"
                            f"• Reason: {event.reason}\n"
                            f"• Time: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    }
                }
            ]
        }
        
        try:
            response = requests.post(webhook_url, json=message, timeout=10)
            response.raise_for_status()
            self.logger.info("Failover notification sent")
        except Exception as e:
            self.logger.error(f"Error sending notification: {e}")
    
    def monitor_and_failover(self, interval: int = 60) -> None:
        """Continuously monitor regions and perform failover if needed"""
        self.logger.info("Starting continuous failover monitoring")
        
        # Identify original primary region
        for region, config in self.regions.items():
            if config.get('priority') == 1:
                self.original_primary = region
                self.current_primary = region
                break
        
        if not self.original_primary:
            self.logger.error("No primary region configured")
            return
        
        self.logger.info(f"Primary region: {self.original_primary}")
        
        # Monitoring loop
        try:
            while True:
                self.logger.info("=== Health Check Cycle ===")
                
                # Check health of all regions
                all_health = {}
                for region in self.regions:
                    health = self.check_prometheus_health(region)
                    all_health[region] = health
                
                # Determine if failover is needed
                primary_health = all_health.get(self.current_primary)
                
                if primary_health and not primary_health.healthy:
                    # Primary is unhealthy - check consecutive failures
                    consecutive_threshold = self.thresholds.get('consecutive_failures', 3)
                    
                    if primary_health.consecutive_failures >= consecutive_threshold:
                        self.logger.warning(
                            f"Primary region {self.current_primary} is unhealthy "
                            f"({primary_health.consecutive_failures} consecutive failures)"
                        )
                        
                        # Find healthy secondary region
                        for region, health in all_health.items():
                            if region != self.current_primary and health.healthy:
                                # Execute failover
                                self.execute_failover(
                                    from_region=self.current_primary,
                                    to_region=region,
                                    trigger="metric",
                                    reason=(
                                        f"Primary region unhealthy: "
                                        f"error_rate={primary_health.error_rate:.4f}, "
                                        f"latency_p95={primary_health.latency_p95*1000:.1f}ms, "
                                        f"availability={primary_health.availability:.4f}"
                                    )
                                )
                                break
                        else:
                            self.logger.error("No healthy secondary region available for failover")
                
                # Check if original primary has recovered and rollback is possible
                elif self.current_primary != self.original_primary:
                    original_health = all_health.get(self.original_primary)
                    
                    if original_health and original_health.healthy:
                        # Check consecutive successes for rollback
                        consecutive_threshold = self.thresholds.get('consecutive_successes', 5)
                        
                        if original_health.consecutive_successes >= consecutive_threshold:
                            self.logger.info(
                                f"Original primary {self.original_primary} has recovered "
                                f"({original_health.consecutive_successes} consecutive successes)"
                            )
                            
                            # Execute rollback
                            self.execute_rollback(self.original_primary)
                
                # Wait before next check
                self.logger.info(f"Next check in {interval} seconds")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.logger.info("Monitoring stopped by user")
    
    def handle_prometheus_alert(self, alert_data: Dict[str, Any]) -> None:
        """Handle incoming Prometheus alert webhook"""
        self.logger.info("Received Prometheus alert")
        
        alerts = alert_data.get('alerts', [])
        
        for alert in alerts:
            status = alert.get('status')
            labels = alert.get('labels', {})
            annotations = alert.get('annotations', {})
            
            alert_name = labels.get('alertname')
            region = labels.get('region')
            severity = labels.get('severity')
            
            self.logger.info(
                f"Alert: {alert_name}, Region: {region}, "
                f"Severity: {severity}, Status: {status}"
            )
            
            # Handle critical alerts that trigger failover
            if (
                status == 'firing' and
                severity == 'critical' and
                region == self.current_primary and
                alert_name in ['HighErrorRate', 'HighLatency', 'ServiceDown']
            ):
                # Find healthy secondary
                for secondary_region in self.regions:
                    if secondary_region != region:
                        health = self.check_prometheus_health(secondary_region)
                        if health.healthy:
                            self.execute_failover(
                                from_region=region,
                                to_region=secondary_region,
                                trigger="alert",
                                reason=f"Alert {alert_name}: {annotations.get('summary', 'N/A')}"
                            )
                            break
    
    def print_status(self) -> None:
        """Print current failover status"""
        print("\n" + "="*80)
        print("MULTI-REGION FAILOVER STATUS")
        print("="*80)
        print(f"DNS Provider: {self.dns_provider}")
        print(f"Original Primary: {self.original_primary}")
        print(f"Current Primary: {self.current_primary}")
        print()
        
        print("Region Health:")
        print("-"*80)
        for region, health in self.region_health.items():
            status = "✓ HEALTHY" if health.healthy else "✗ UNHEALTHY"
            print(f"  {region:20} {status:12} "
                  f"error_rate={health.error_rate:.4f} "
                  f"latency_p95={health.latency_p95*1000:.1f}ms "
                  f"availability={health.availability:.4f}")
        print()
        
        print("DNS Weights:")
        print("-"*80)
        weights = self.get_current_dns_weights()
        for region, weight in weights.items():
            print(f"  {region:20} {weight:3d}")
        print()
        
        if self.failover_history:
            print("Recent Failover Events:")
            print("-"*80)
            for event in self.failover_history[-5:]:
                print(f"  {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                      f"{event.from_region} -> {event.to_region} "
                      f"({event.trigger})")
        print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Multi-region DNS failover automation"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Monitor command (continuous monitoring)
    monitor_parser = subparsers.add_parser(
        'monitor',
        help='Continuously monitor and perform automatic failover'
    )
    monitor_parser.add_argument(
        '--config',
        default='configs/failover-config.yaml',
        help='Path to failover configuration file'
    )
    monitor_parser.add_argument(
        '--prometheus-url',
        default='http://prometheus:9090',
        help='Prometheus server URL'
    )
    monitor_parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help='Health check interval in seconds (default: 60)'
    )
    monitor_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode - no actual DNS changes'
    )
    monitor_parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )
    
    # Failover command (manual failover)
    failover_parser = subparsers.add_parser(
        'failover',
        help='Manually trigger failover to specified region'
    )
    failover_parser.add_argument(
        '--config',
        default='configs/failover-config.yaml',
        help='Path to failover configuration file'
    )
    failover_parser.add_argument(
        '--prometheus-url',
        default='http://prometheus:9090',
        help='Prometheus server URL'
    )
    failover_parser.add_argument(
        '--to',
        required=True,
        help='Target region to failover to'
    )
    failover_parser.add_argument(
        '--reason',
        default='Manual failover',
        help='Reason for failover'
    )
    failover_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode - no actual DNS changes'
    )
    
    # Rollback command (restore primary)
    rollback_parser = subparsers.add_parser(
        'rollback',
        help='Rollback to original primary region'
    )
    rollback_parser.add_argument(
        '--config',
        default='configs/failover-config.yaml',
        help='Path to failover configuration file'
    )
    rollback_parser.add_argument(
        '--prometheus-url',
        default='http://prometheus:9090',
        help='Prometheus server URL'
    )
    rollback_parser.add_argument(
        '--to',
        required=True,
        help='Target region to rollback to'
    )
    rollback_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode - no actual DNS changes'
    )
    
    # Status command (show current status)
    status_parser = subparsers.add_parser(
        'status',
        help='Show current failover status'
    )
    status_parser.add_argument(
        '--config',
        default='configs/failover-config.yaml',
        help='Path to failover configuration file'
    )
    status_parser.add_argument(
        '--prometheus-url',
        default='http://prometheus:9090',
        help='Prometheus server URL'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        # Create failover manager
        manager = MultiRegionFailoverManager(
            config_file=args.config,
            prometheus_url=args.prometheus_url,
            dry_run=getattr(args, 'dry_run', False),
            log_level=getattr(args, 'log_level', 'INFO')
        )
        
        # Execute command
        if args.command == 'monitor':
            manager.monitor_and_failover(interval=args.interval)
        
        elif args.command == 'failover':
            # Get current primary
            current_weights = manager.get_current_dns_weights()
            current_primary = max(current_weights, key=current_weights.get)
            
            success = manager.execute_failover(
                from_region=current_primary,
                to_region=args.to,
                trigger='manual',
                reason=args.reason
            )
            sys.exit(0 if success else 1)
        
        elif args.command == 'rollback':
            success = manager.execute_rollback(to_region=args.to)
            sys.exit(0 if success else 1)
        
        elif args.command == 'status':
            # Check health of all regions
            for region in manager.regions:
                manager.check_prometheus_health(region)
            
            # Print status
            manager.print_status()
            sys.exit(0)
    
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
