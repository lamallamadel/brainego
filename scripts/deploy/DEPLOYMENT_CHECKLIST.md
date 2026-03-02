# Production Deployment Checklist

Use this checklist to ensure all steps are completed before, during, and after production deployment.

## Pre-Deployment

### Environment Setup
- [ ] Kubernetes cluster is accessible
- [ ] `helm` v3.x is installed
- [ ] `kubectl` is installed and configured
- [ ] Python 3.8+ is installed
- [ ] Required Python packages installed (`pyyaml`, `kubernetes`, `requests`)

### Configuration
- [ ] Production values file is up-to-date (`values-production-secure.yaml`)
- [ ] Domain names are configured correctly
- [ ] TLS certificates are ready (cert-manager configured)
- [ ] Secrets are created in the cluster (database passwords, API keys, etc.)
- [ ] Storage classes are available for PVCs
- [ ] Resource limits are set appropriately
- [ ] Kong plugins are configured
- [ ] Network policies are enabled
- [ ] RBAC is enabled

### Infrastructure
- [ ] Sufficient cluster resources (CPU, Memory, Storage)
- [ ] Load balancer is provisioned (if using LoadBalancer service type)
- [ ] DNS records are configured (point to load balancer)
- [ ] Firewall rules allow required traffic
- [ ] Monitoring stack is ready (Prometheus, Grafana)
- [ ] Backup system is configured

### Testing
- [ ] Helm chart passes `helm lint`
- [ ] Helm chart templates render correctly (`helm template`)
- [ ] Dry-run deployment succeeds (`--dry-run`)
- [ ] Staging environment deployment tested
- [ ] Load tests completed on staging
- [ ] Security scan completed (trivy, kubesec, etc.)

### Documentation
- [ ] Deployment runbook is updated
- [ ] Rollback procedure is documented
- [ ] On-call team is notified
- [ ] Change management ticket created
- [ ] Maintenance window scheduled (if required)

## During Deployment

### Execution
- [ ] Start deployment using `prod_deploy.py`
- [ ] Monitor deployment logs
- [ ] Watch pod status: `kubectl get pods -n <namespace> -w`
- [ ] Monitor cluster events: `kubectl get events -n <namespace> --watch`

### Validation
- [ ] All pods reach Running state
- [ ] StatefulSets are ready (Postgres, Qdrant, Neo4j, Redis)
- [ ] PVCs are bound
- [ ] Network policies are applied
- [ ] RBAC resources are created
- [ ] Helm tests pass (`helm test`)
- [ ] Smoke tests pass

### Monitoring
- [ ] Prometheus is scraping metrics
- [ ] Grafana dashboards are displaying data
- [ ] Logs are flowing to centralized logging (if configured)
- [ ] Alerts are not firing

## Post-Deployment

### Verification
- [ ] Health check endpoints respond correctly
- [ ] API endpoints are accessible
- [ ] Authentication/authorization works
- [ ] Database connections are established
- [ ] Vector database (Qdrant) is accessible
- [ ] Graph database (Neo4j) is accessible
- [ ] Cache (Redis) is working
- [ ] Gateway routes traffic correctly
- [ ] TLS certificates are valid
- [ ] Kong rate limiting is working

### Performance
- [ ] Response times are acceptable
- [ ] Throughput meets requirements
- [ ] Resource utilization is normal (CPU, Memory)
- [ ] No memory leaks detected
- [ ] Database query performance is good

### Functional Tests
- [ ] Chat completions endpoint works
- [ ] Embeddings endpoint works
- [ ] Memory storage/retrieval works
- [ ] RAG queries work
- [ ] Graph queries work
- [ ] Learning engine responds correctly
- [ ] MCP tools are accessible

### Security
- [ ] TLS is enforced (HTTP redirects to HTTPS)
- [ ] Authentication is required for protected endpoints
- [ ] Rate limiting is active
- [ ] Network policies are enforced
- [ ] RBAC permissions are correct
- [ ] Secrets are not exposed in logs
- [ ] Pod security policies/standards are applied

### Documentation
- [ ] Deployment notes recorded
- [ ] Git tag created for release
- [ ] Change log updated
- [ ] Team notified of successful deployment
- [ ] Handoff to operations team completed

## Rollback (If Needed)

### Decision Criteria
- [ ] Critical bug detected
- [ ] Performance degradation
- [ ] Data corruption risk
- [ ] Security vulnerability
- [ ] Excessive error rate

### Rollback Execution
- [ ] Run: `scripts/deploy/rollback.sh` or `helm rollback <release> -n <namespace>`
- [ ] Verify rollback completed
- [ ] Monitor system stability
- [ ] Notify team of rollback
- [ ] Document rollback reason
- [ ] Plan fix for next deployment

## Monitoring & Alerts

### Metrics to Watch (First 24 Hours)
- [ ] Request rate
- [ ] Error rate
- [ ] Response time (p50, p95, p99)
- [ ] CPU utilization
- [ ] Memory utilization
- [ ] Disk I/O
- [ ] Database connections
- [ ] Cache hit rate
- [ ] Queue depths (if applicable)

### Alerts to Configure
- [ ] Pod crash loop
- [ ] High error rate
- [ ] High latency
- [ ] Resource exhaustion
- [ ] Certificate expiration warning
- [ ] Database connection failures
- [ ] Disk space warning

## Sign-Off

### Deployment Team
- [ ] DevOps Engineer: _______________  Date: _______________
- [ ] SRE: _______________  Date: _______________
- [ ] Platform Engineer: _______________  Date: _______________

### Verification Team
- [ ] QA Engineer: _______________  Date: _______________
- [ ] Security Engineer: _______________  Date: _______________

### Approvals
- [ ] Tech Lead: _______________  Date: _______________
- [ ] Product Owner: _______________  Date: _______________

## Notes

_Use this section to record any deployment-specific notes, issues encountered, or deviations from the standard process._

---

**Date:** _______________

**Deployment Version:** _______________

**Chart Version:** _______________

**Namespace:** _______________

**Release Name:** _______________
