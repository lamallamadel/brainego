# Multi-Region Deployment Guide

Complete guide for deploying the AI Platform across multiple regions with automatic failover and geo-routing.

## Overview

The multi-region deployment provides:

- **Geographic Distribution**: Deploy to multiple AWS/GCP/Azure regions
- **Low Latency**: Route users to nearest region based on geo-location
- **High Availability**: Automatic failover if a region goes down
- **Data Replication**: Cross-region replication for PostgreSQL and Qdrant
- **Monitoring**: Real-time dashboards for latency and replication lag

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Global Load Balancer                      │
│              (Route53 / Cloud DNS / Traffic Manager)         │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬─────────────┐
        │             │             │             │
┌───────▼──────┐ ┌────▼──────┐ ┌───▼──────┐ ┌───▼──────┐
│  us-west-1   │ │ us-east-1 │ │eu-west-1 │ │ap-se-1   │
│              │ │           │ │          │ │          │
│ ┌──────────┐ │ │┌─────────┐│ │┌────────┐│ │┌────────┐│
│ │ MAX Serve│ │ ││MAX Serve││ ││MAX     ││ ││MAX     ││
│ │ (GPU)    │ │ ││ (GPU)   ││ ││Serve   ││ ││Serve   ││
│ └──────────┘ │ │└─────────┘│ │└────────┘│ │└────────┘│
│              │ │           │ │          │ │          │
│ ┌──────────┐ │ │┌─────────┐│ │┌────────┐│ │┌────────┐│
│ │ Qdrant   │◄┼─┼│ Qdrant  │◄┼─┼│Qdrant  │◄┼─┼│Qdrant  ││
│ │ Cluster  │─┼►││ Cluster │─┼►││Cluster │─┼►││Cluster ││
│ └──────────┘ │ │└─────────┘│ │└────────┘│ │└────────┘│
│              │ │           │ │          │ │          │
│ ┌──────────┐ │ │┌─────────┐│ │┌────────┐│ │┌────────┐│
│ │PostgreSQL│◄┼─┼│Postgres │◄┼─┼│Postgres│◄┼─┼│Postgres││
│ │ Primary  │─┼►││ Replica │─┼►││Replica │─┼►││Replica ││
│ └──────────┘ │ │└─────────┘│ │└────────┘│ │└────────┘│
└──────────────┘ └───────────┘ └──────────┘ └──────────┘
```

## Supported Regions

| Region | Location | Cloud Provider | Purpose |
|--------|----------|----------------|---------|
| `us-west-1` | Oregon, USA | AWS/GCP | Primary, North America West |
| `us-east-1` | Virginia, USA | AWS/GCP | North America East |
| `eu-west-1` | Ireland | AWS/GCP | Europe |
| `ap-southeast-1` | Singapore | AWS/GCP | Asia Pacific |

## Prerequisites

### Tools Required

- `kubectl` (v1.27+)
- `helm` (v3.12+)
- Python 3.11+
- Cloud provider CLI (AWS CLI, gcloud, or az)

### Cloud Resources

For each region, provision:

- Kubernetes cluster (3+ nodes)
- GPU nodes (for MAX Serve)
- Regional persistent disks
- VPC peering between regions (optional, for lower latency)
- DNS hosted zone

## Quick Start

### 1. Deploy to First Region (Primary)

```bash
# Set region
export REGION=us-west-1
export CLUSTER_NAME=ai-platform-us-west-1

# Configure kubectl
kubectl config use-context ${CLUSTER_NAME}

# Deploy using the multi-region deployment script
python scripts/deploy/deploy_region.py \
  --region ${REGION} \
  --cluster ${CLUSTER_NAME} \
  --values-file helm/ai-platform/values-multi-region.yaml
```

### 2. Deploy to Additional Regions

```bash
# Deploy to us-east-1
python scripts/deploy/deploy_region.py \
  --region us-east-1 \
  --cluster ai-platform-us-east-1 \
  --values-file helm/ai-platform/values-multi-region.yaml

# Deploy to eu-west-1
python scripts/deploy/deploy_region.py \
  --region eu-west-1 \
  --cluster ai-platform-eu-west-1 \
  --values-file helm/ai-platform/values-multi-region.yaml

# Deploy to ap-southeast-1
python scripts/deploy/deploy_region.py \
  --region ap-southeast-1 \
  --cluster ai-platform-ap-southeast-1 \
  --values-file helm/ai-platform/values-multi-region.yaml
```

### 3. Setup Cross-Region Replication

#### PostgreSQL Replication (pglogical)

```bash
# On primary region (us-west-1)
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform \
  -f /docker-entrypoint-initdb.d/postgres-replication-setup.sql

# Setup replication node
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT setup_replication_node('us-west-1', 'host=postgres.us-west-1.ai-platform.svc.cluster.local port=5432 dbname=ai_platform user=replication_user password=replication_password');"

# Setup replication set
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT setup_replication_set('ai_platform_set');"

# On replica regions (us-east-1, eu-west-1, ap-southeast-1)
# Switch context to each region and run:
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT setup_replication_subscription('sub_from_us_west_1', 'host=postgres.us-west-1.ai-platform.svc.cluster.local port=5432 dbname=ai_platform user=replication_user password=replication_password');"
```

#### Qdrant Replication (Cluster Mode)

```bash
# Setup Qdrant cluster across all regions
python scripts/deploy/setup_qdrant_replication.py \
  --regions us-west-1 us-east-1 eu-west-1 ap-southeast-1 \
  --cluster-name ai-platform
```

### 4. Configure Geo-Routing

The geo-routing configuration is automatically deployed with Kong Ingress. To customize:

```bash
# Edit geo-routing configuration
vim configs/geo-routing.yaml

# Apply updated configuration
kubectl apply -n ai-platform -f configs/geo-routing.yaml
```

### 5. Setup DNS Failover

#### AWS Route53

```bash
# Create health checks for each region
aws route53 create-health-check \
  --type HTTPS \
  --resource-path /health \
  --fully-qualified-domain-name us-west-1.ai-platform.example.com \
  --port 443 \
  --request-interval 30 \
  --failure-threshold 3

# Create failover routing policy
aws route53 change-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --change-batch file://dns-failover-config.json
```

#### Google Cloud DNS

```bash
# Create health check
gcloud compute health-checks create https ai-platform-us-west-1 \
  --request-path=/health \
  --port=443 \
  --check-interval=30s \
  --timeout=5s \
  --unhealthy-threshold=3 \
  --healthy-threshold=2

# Create managed zone with routing policy
gcloud dns managed-zones create ai-platform \
  --description="AI Platform multi-region DNS" \
  --dns-name=ai-platform.example.com \
  --routing-policy-type=WEIGHTED
```

## Configuration

### Helm Values

Key configuration options in `helm/ai-platform/values-multi-region.yaml`:

```yaml
global:
  region: us-west-1  # Override per region
  multiRegion:
    enabled: true
    primaryRegion: us-west-1
    regions:
      - us-west-1
      - us-east-1
      - eu-west-1
      - ap-southeast-1
    replicationStrategy: async  # async or sync

# GPU node affinity for MAX Serve
maxServeLlama:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: node.kubernetes.io/instance-type
                operator: In
                values:
                  - gpu-accelerated
              - key: topology.kubernetes.io/region
                operator: In
                values:
                  - "{{ .Values.global.region }}"

# Regional persistent storage
postgres:
  persistence:
    storageClass: "regional-pd-ssd"
    size: 100Gi
  replication:
    enabled: true
    mode: pglogical
    primaryRegion: us-west-1
```

### Geo-Routing Rules

Configure in `configs/geo-routing.yaml`:

```yaml
regions:
  us-west-1:
    geolocation:
      countries: [US, CA]
      states: [CA, OR, WA, NV, AZ]
    weight: 100
    maxLatencyMs: 100

routing:
  strategy: geo-latency  # geo-latency, geo-proximity, latency-only
  latencyBased:
    enabled: true
    measurementInterval: 60
```

## Monitoring

### Grafana Dashboard

Access the cross-region monitoring dashboard:

```bash
# Port-forward Grafana
kubectl port-forward -n ai-platform svc/grafana 3000:3000

# Open browser
open http://localhost:3000/d/cross-region-monitoring
```

The dashboard shows:

- **Region Health**: Status of each region
- **Cross-Region Latency**: P50, P95, P99 latency between regions
- **Replication Lag**: PostgreSQL and Qdrant replication lag
- **Failover Events**: Count of regional failovers
- **Traffic Distribution**: Request distribution across regions

### Key Metrics

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `region_health_status` | Region health (1=healthy, 0=down) | < 1 |
| `geo_routing_latency_ms` | Cross-region request latency | > 250ms (P95) |
| `pg_replication_lag_seconds` | PostgreSQL replication lag | > 30s |
| `qdrant_replication_lag_seconds` | Qdrant replication lag | > 60s |
| `geo_routing_failovers_total` | Count of failover events | > 5/hour |

### Prometheus Queries

```promql
# Average cross-region latency
avg(rate(geo_routing_latency_ms_sum[5m]) / rate(geo_routing_latency_ms_count[5m])) by (source_region, target_region)

# Max replication lag
max(pg_replication_lag_seconds) by (region)

# Failover rate
rate(geo_routing_failovers_total[5m])

# Regional request distribution
sum(rate(geo_routing_requests_total[5m])) by (target_region)
```

## Replication Management

### Check Replication Status

#### PostgreSQL

```bash
# Check replication lag
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM replication_status;"

# Check replication health
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM check_replication_health();"

# Check alerts
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM check_replication_alerts();"
```

#### Qdrant

```bash
# Check cluster status
kubectl exec -n ai-platform qdrant-0 -- curl http://localhost:6333/cluster

# Check collection info
kubectl exec -n ai-platform qdrant-0 -- curl http://localhost:6333/collections/documents
```

### Pause/Resume Replication

```bash
# Pause PostgreSQL subscription
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT pglogical.alter_subscription_disable('sub_from_us_west_1');"

# Resume PostgreSQL subscription
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT pglogical.alter_subscription_enable('sub_from_us_west_1');"
```

## Failover Testing

### Manual Failover

```bash
# Simulate region failure by scaling down deployments
kubectl scale deployment -n ai-platform gateway --replicas=0

# Monitor failover in Grafana dashboard
# Requests should automatically route to healthy regions

# Restore region
kubectl scale deployment -n ai-platform gateway --replicas=3
```

### Chaos Testing

```bash
# Install chaos mesh (optional)
helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-testing

# Create network chaos to simulate latency
kubectl apply -f - <<EOF
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-delay-us-west-1
  namespace: ai-platform
spec:
  action: delay
  mode: all
  selector:
    namespaces:
      - ai-platform
    labelSelectors:
      region: us-west-1
  delay:
    latency: "100ms"
    correlation: "100"
    jitter: "0ms"
  duration: "5m"
EOF
```

## Disaster Recovery

### Backup Strategy

- **PostgreSQL**: Daily snapshots + continuous WAL archiving
- **Qdrant**: Snapshots every 6 hours
- **MinIO**: Cross-region replication enabled

### Recovery Procedures

#### Full Region Recovery

```bash
# 1. Provision new cluster in region
# 2. Deploy using deploy_region.py
# 3. Restore PostgreSQL from WAL archive
kubectl exec -n ai-platform postgres-0 -- pg_basebackup -D /var/lib/postgresql/data/restore

# 4. Restore Qdrant snapshots
kubectl exec -n ai-platform qdrant-0 -- curl -X POST \
  http://localhost:6333/collections/documents/snapshots/restore \
  -d '{"location": "s3://ai-platform-qdrant-snapshots/us-west-1/latest"}'

# 5. Re-enable DNS routing
# Update health check status
```

## Performance Tuning

### Reducing Cross-Region Latency

1. **VPC Peering**: Enable VPC peering between regions for faster internal communication
2. **Regional Caching**: Increase Redis cache size and TTL
3. **Read Replicas**: Direct read traffic to local replicas
4. **Edge Caching**: Use CDN for static assets

### Optimizing Replication

```yaml
# PostgreSQL - Adjust synchronous_commit for performance vs. durability
postgres:
  env:
    - name: POSTGRES_SYNCHRONOUS_COMMIT
      value: "local"  # off, local, remote_write, remote_apply, on

# Qdrant - Adjust write consistency
qdrant:
  collection:
    write_consistency_factor: 1  # Lower for performance, higher for consistency
```

## Troubleshooting

### High Replication Lag

```bash
# Check network connectivity between regions
kubectl run -n ai-platform test-pod --image=busybox --rm -it -- \
  ping postgres.us-west-1.ai-platform.svc.cluster.local

# Check PostgreSQL replication slots
kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
  "SELECT * FROM pg_replication_slots;"

# Check disk I/O
kubectl exec -n ai-platform postgres-0 -- iostat -x 1 5
```

### DNS Failover Not Working

```bash
# Check health check status (AWS)
aws route53 get-health-check-status --health-check-id abc123

# Test DNS resolution
dig +short us-west-1.ai-platform.example.com
nslookup us-west-1.ai-platform.example.com

# Check Kong geo-routing plugin
kubectl logs -n ai-platform -l app.kubernetes.io/name=kong
```

### Region Unreachable

```bash
# Check cluster connectivity
kubectl cluster-info

# Check node status
kubectl get nodes

# Check pod status
kubectl get pods -n ai-platform

# Check service endpoints
kubectl get endpoints -n ai-platform
```

## Cost Optimization

- **GPU Nodes**: Use spot/preemptible instances for non-critical regions
- **Storage**: Use standard SSDs for non-primary regions
- **Network**: Minimize cross-region traffic with regional caching
- **Auto-scaling**: Configure HPA to scale down during low traffic

## Security Considerations

- **Encryption in Transit**: All cross-region traffic uses TLS
- **VPC Peering**: Use private networking between regions
- **Secrets**: Use separate secrets per region
- **Access Control**: Implement region-specific RBAC policies

## References

- [PostgreSQL Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html)
- [pglogical Documentation](https://github.com/2ndQuadrant/pglogical)
- [Qdrant Clustering](https://qdrant.tech/documentation/guides/distributed_deployment/)
- [Kong Geo-Routing](https://docs.konghq.com/hub/kong-inc/route-by-header/)

## Support

For issues or questions:
- Open GitHub issue
- Contact: team@ai-platform.example.com
- Documentation: https://docs.ai-platform.example.com
