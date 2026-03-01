.PHONY: help install install-modular download build start stop restart logs health test load-test monitor clean gateway gateway-build gateway-start gateway-stop gateway-test gateway-demo mcpjungle mcpjungle-build mcpjungle-start mcpjungle-stop mcpjungle-logs mcpjungle-test mcpjungle-health jaeger-ui graph-test graph-example graph-init-schema graph-ui neo4j-logs learning learning-start learning-stop learning-logs learning-test learning-train learning-status grafana grafana-start grafana-stop grafana-ui drift drift-start drift-stop drift-logs drift-check drift-metrics test-unit test-integration test-all codex-help pilot-preflight pilot-demo-rbac pilot-demo-index pilot-demo-incident pilot-demo

help:
	@echo "MAX Serve + Llama 3.3 8B Infrastructure"
	@echo ""
	@echo "Available commands:"
	@echo "  make install      - Install Python dependencies"
	@echo "  make install-modular - Install Modular Python package and verify MAX CLI"
	@echo "  make download     - Download Llama 3.3 8B model"
	@echo "  make build        - Build Docker images"
	@echo "  make start        - Start all services"
	@echo "  make stop         - Stop all services"
	@echo "  make restart      - Restart all services"
	@echo "  make logs         - View logs (all services)"
	@echo "  make logs-max     - View MAX Serve logs"
	@echo "  make logs-api     - View API server logs"
	@echo "  make health       - Check service health"
	@echo "  make test         - Run basic API tests"
	@echo "  make load-test    - Run load tests (quick)"
	@echo "  make stress-test  - Run stress tests (intensive)"
	@echo "  make monitor      - Start real-time monitoring"
	@echo "  make clean        - Stop and remove all containers/volumes"
	@echo ""
	@echo "Gateway commands:"
	@echo "  make gateway         - Build and start gateway service"
	@echo "  make gateway-build   - Build gateway Docker image"
	@echo "  make gateway-start   - Start gateway service"
	@echo "  make gateway-stop    - Stop gateway service"
	@echo "  make gateway-test    - Run gateway end-to-end tests"
	@echo "  make gateway-demo    - Run gateway demo"
	@echo ""
	@echo "MCPJungle Gateway commands:"
	@echo "  make mcpjungle       - Build and start MCPJungle gateway"
	@echo "  make mcpjungle-build - Build MCPJungle Docker image"
	@echo "  make mcpjungle-start - Start MCPJungle gateway"
	@echo "  make mcpjungle-stop  - Stop MCPJungle gateway"
	@echo "  make mcpjungle-logs  - View MCPJungle logs"
	@echo "  make mcpjungle-test  - Run MCPJungle tests"
	@echo "  make mcpjungle-health- Check MCPJungle health"
	@echo "  make jaeger-ui       - Open Jaeger UI for tracing"
	@echo ""
	@echo "Knowledge Graph commands:"
	@echo "  make graph-test      - Run knowledge graph tests"
	@echo "  make graph-example   - Run graph usage examples"
	@echo "  make graph-ui        - Open Neo4j Browser UI"
	@echo "  make neo4j-logs      - View Neo4j logs"
	@echo ""
	@echo "Data Collection Pipeline commands:"
	@echo "  make datacollection       - Build and start data collection service"
	@echo "  make datacollection-start - Start data collection and workers"
	@echo "  make datacollection-stop  - Stop data collection services"
	@echo "  make datacollection-logs  - View data collection logs"
	@echo "  make datacollection-test  - Run data collection tests"
	@echo "  make datacollection-stats - Get collection statistics"
	@echo ""
	@echo "Learning Engine commands:"
	@echo "  make learning         - Build and start learning engine"
	@echo "  make learning-start   - Start learning engine"
	@echo "  make learning-stop    - Stop learning engine"
	@echo "  make learning-logs    - View learning engine logs"
	@echo "  make learning-test    - Run learning engine tests"
	@echo "  make learning-train   - Trigger training job"
	@echo "  make learning-status  - Check training status"
	@echo "  make learning-adapters- List all adapters"
	@echo ""
	@echo "Grafana & Monitoring commands:"
	@echo "  make grafana          - Start Prometheus and Grafana"
	@echo "  make grafana-start    - Start Grafana and Prometheus"
	@echo "  make grafana-stop     - Stop Grafana and Prometheus"
	@echo "  make grafana-ui       - Open Grafana dashboards"
	@echo ""
	@echo "Drift Monitor commands:"
	@echo "  make drift            - Start drift monitor service"
	@echo "  make drift-start      - Start drift monitor"
	@echo "  make drift-stop       - Stop drift monitor"
	@echo "  make drift-logs       - View drift monitor logs"
	@echo "  make drift-check      - Trigger manual drift check"
	@echo "  make drift-metrics    - View drift metrics"

install:
	pip install -r requirements.txt

install-modular:
	chmod +x install_modular_max.sh
	./install_modular_max.sh

download:
	chmod +x download_model.sh
	./download_model.sh

build:
	docker compose build

start:
	chmod +x init.sh
	./init.sh

stop:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

logs-max:
	docker compose logs -f max-serve

logs-api:
	docker compose logs -f api-server

health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/health | python -m json.tool || echo "API server not responding"
	@echo ""
	@curl -s http://localhost:8080/health | python -m json.tool || echo "MAX Serve not responding"

test:
	python test_api.py

load-test:
	python load_test.py --requests 100 --concurrency 10 --scenario medium

stress-test:
	python load_test.py --requests 1000 --concurrency 32 --scenario all

monitor:
	python monitor.py

clean:
	docker compose down -v
	rm -rf logs/*

gateway:
	@echo "Building and starting gateway service..."
	@docker compose build gateway
	@docker compose up -d gateway
	@echo "Gateway started on http://localhost:9000"

gateway-build:
	@echo "Building gateway Docker image..."
	@docker compose build gateway

gateway-start:
	@echo "Starting gateway service..."
	@docker compose up -d gateway
	@echo "Gateway started on http://localhost:9000"

gateway-stop:
	@echo "Stopping gateway service..."
	@docker compose stop gateway

gateway-test:
	@echo "Running gateway end-to-end tests..."
	@python test_gateway.py

gateway-demo:
	@echo "Running gateway demo..."
	@python examples/gateway_demo.py

mcpjungle:
	@echo "Building and starting MCPJungle gateway..."
	@docker compose build mcpjungle-gateway jaeger
	@docker compose up -d mcpjungle-gateway jaeger
	@echo ""
	@echo "MCPJungle Gateway started on http://localhost:9100"
	@echo "Jaeger UI available at http://localhost:16686"
	@echo ""
	@echo "Test with: make mcpjungle-test"
	@echo "View logs: make mcpjungle-logs"

mcpjungle-build:
	@echo "Building MCPJungle Docker image..."
	@docker compose build mcpjungle-gateway

mcpjungle-start:
	@echo "Starting MCPJungle gateway and Jaeger..."
	@docker compose up -d mcpjungle-gateway jaeger
	@echo "MCPJungle Gateway started on http://localhost:9100"
	@echo "Jaeger UI available at http://localhost:16686"

mcpjungle-stop:
	@echo "Stopping MCPJungle gateway..."
	@docker compose stop mcpjungle-gateway jaeger

mcpjungle-logs:
	@echo "Viewing MCPJungle gateway logs..."
	@docker compose logs -f mcpjungle-gateway

mcpjungle-test:
	@echo "Running MCPJungle tests..."
	@python test_mcpjungle.py

mcpjungle-health:
	@echo "Checking MCPJungle health..."
	@curl -s http://localhost:9100/health | python -m json.tool || echo "MCPJungle gateway not responding"

jaeger-ui:
	@echo "Opening Jaeger UI..."
	@echo "Jaeger UI: http://localhost:16686"
	@command -v open >/dev/null 2>&1 && open http://localhost:16686 || echo "Open http://localhost:16686 in your browser"

graph-test:
	@echo "Running knowledge graph tests..."
	@python test_graph.py

graph-example:
	@echo "Running graph usage examples..."
	@python examples/graph_example.py


graph-init-schema:
	@echo "Applying base Neo4j schema from configs/neo4j/base_schema.cypher..."
	@cat configs/neo4j/base_schema.cypher | docker exec -i neo4j cypher-shell -u neo4j -p neo4j_password
	@echo "Schema applied successfully."

graph-ui:
	@echo "Opening Neo4j Browser..."
	@echo "Neo4j Browser: http://localhost:7474"
	@echo "Username: neo4j"
	@echo "Password: neo4j_password"
	@command -v open >/dev/null 2>&1 && open http://localhost:7474 || echo "Open http://localhost:7474 in your browser"

neo4j-logs:
	@echo "Viewing Neo4j logs..."
	@docker compose logs -f neo4j

datacollection:
	@echo "Building and starting data collection service..."
	@docker compose build data-collection ingestion-worker
	@docker compose up -d data-collection ingestion-worker
	@echo ""
	@echo "Data Collection Service started on http://localhost:8002"
	@echo ""
	@echo "Test with: make datacollection-test"
	@echo "View stats: make datacollection-stats"

datacollection-start:
	@echo "Starting data collection and workers..."
	@docker compose up -d data-collection ingestion-worker
	@echo "Data Collection Service started on http://localhost:8002"

datacollection-stop:
	@echo "Stopping data collection services..."
	@docker compose stop data-collection ingestion-worker

datacollection-logs:
	@echo "Viewing data collection logs..."
	@docker compose logs -f data-collection ingestion-worker

datacollection-test:
	@echo "Running data collection tests..."
	@python test_data_collection.py

datacollection-stats:
	@echo "Fetching collection statistics..."
	@curl -s http://localhost:8002/stats | python -m json.tool || echo "Data collection service not responding"

learning:
	@echo "Building and starting learning engine..."
	@docker compose build learning-engine
	@docker compose up -d learning-engine postgres minio
	@echo ""
	@echo "Learning Engine started on http://localhost:8003"
	@echo ""
	@echo "Test with: make learning-test"
	@echo "View logs: make learning-logs"

learning-start:
	@echo "Starting learning engine..."
	@docker compose up -d learning-engine
	@echo "Learning Engine started on http://localhost:8003"

learning-stop:
	@echo "Stopping learning engine..."
	@docker compose stop learning-engine

learning-logs:
	@echo "Viewing learning engine logs..."
	@docker compose logs -f learning-engine

learning-test:
	@echo "Running learning engine tests..."
	@python test_learning_engine.py

learning-train:
	@echo "Triggering training job..."
	@python learning_engine_cli.py train --days 7 --force

learning-status:
	@echo "Checking training status..."
	@python learning_engine_cli.py status

learning-adapters:
	@echo "Listing adapters..."
	@python learning_engine_cli.py list-adapters

grafana:
	@echo "Starting Prometheus and Grafana..."
	@docker compose up -d prometheus grafana
	@echo ""
	@echo "Grafana started on http://localhost:3000"
	@echo "Prometheus started on http://localhost:9090"
	@echo ""
	@echo "Default login: admin / admin"
	@echo "Dashboards: make grafana-ui"

grafana-start:
	@echo "Starting Grafana and Prometheus..."
	@docker compose up -d prometheus grafana
	@echo "Grafana: http://localhost:3000"
	@echo "Prometheus: http://localhost:9090"

grafana-stop:
	@echo "Stopping Grafana and Prometheus..."
	@docker compose stop prometheus grafana

grafana-ui:
	@echo "Opening Grafana dashboards..."
	@echo ""
	@echo "Grafana UI: http://localhost:3000"
	@echo "Default login: admin / admin"
	@echo ""
	@echo "Available dashboards:"
	@echo "  - Drift Overview:        http://localhost:3000/d/drift-overview"
	@echo "  - KL Divergence:         http://localhost:3000/d/drift-kl-divergence"
	@echo "  - PSI Trends:            http://localhost:3000/d/drift-psi-trends"
	@echo "  - Accuracy Tracking:     http://localhost:3000/d/drift-accuracy-tracking"
	@echo "  - LoRA Version Tracking: http://localhost:3000/d/lora-version-tracking"
	@echo ""
	@command -v open >/dev/null 2>&1 && open http://localhost:3000/d/drift-overview || echo "Open http://localhost:3000 in your browser"

drift:
	@echo "Starting drift monitor..."
	@docker compose up -d drift-monitor postgres
	@echo ""
	@echo "Drift Monitor started on http://localhost:8004"
	@echo ""
	@echo "Check drift: make drift-check"
	@echo "View logs: make drift-logs"

drift-start:
	@echo "Starting drift monitor..."
	@docker compose up -d drift-monitor
	@echo "Drift Monitor: http://localhost:8004"

drift-stop:
	@echo "Stopping drift monitor..."
	@docker compose stop drift-monitor

drift-logs:
	@echo "Viewing drift monitor logs..."
	@docker compose logs -f drift-monitor

drift-check:
	@echo "Triggering manual drift check..."
	@curl -s -X POST http://localhost:8004/drift/check | python -m json.tool || echo "Drift monitor not responding"

drift-metrics:
	@echo "Fetching drift metrics..."
	@curl -s http://localhost:8004/drift/metrics?days=7 | python -m json.tool || echo "Drift monitor not responding"

# ============================================================================
# Docker Build Cloud + Testcontainers Cloud Commands
# ============================================================================

test-unit:
	@echo "Running unit tests..."
	@pip install -q pytest pytest-asyncio pytest-cov 2>/dev/null || true
	@pytest tests/unit/ -v --tb=short --cov=. --cov-report=term-missing

test-integration:
	@echo "Running integration tests (requires Testcontainers Cloud)..."
	@echo "Set TESTCONTAINERS_CLOUD_TOKEN environment variable"
	@pip install -q pytest pytest-asyncio testcontainers 2>/dev/null || true
	@pytest tests/integration/ -v --tb=short -s

test-lora-regression:
	@echo "Running LoRA non-regression gate..."
	@python scripts/lora_non_regression.py \
		--suite tests/contract/fixtures/lora_regression_prompts.ndjson \
		--baseline-output tests/contract/fixtures/lora_baseline_outputs.ndjson \
		--candidate-output tests/contract/fixtures/lora_candidate_outputs_good.ndjson

test-all: test-unit test-integration test-lora-regression
	@echo ""
	@echo "✅ All tests completed"

codex-help:
	@echo "=============================================================================="
	@echo "Codex: Docker Build Cloud + Testcontainers Cloud Setup"
	@echo "=============================================================================="
	@echo ""
	@echo "📚 Documentation:"
	@echo "  - QUICKSTART.md           Quick setup (5 min)"
	@echo "  - CODEX_INSTRUCTIONS.md   How to generate code"
	@echo "  - GITHUB_ACTIONS_SETUP.md Technical details"
	@echo "  - CI_CD_SUMMARY.md        Complete overview"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  1. Add GitHub Secret: TESTCONTAINERS_CLOUD_TOKEN"
	@echo "     → https://cloud.testcontainers.com/ → Settings → API Tokens"
	@echo ""
	@echo "  2. Test the pipeline:"
	@echo "     make test-unit"
	@echo "     make test-integration"
	@echo ""
	@echo "  3. Push to feature/codex/* branch"
	@echo "     → GitHub Actions runs automatically"
	@echo ""
	@echo "  4. Check PR comments for results"
	@echo ""
	@echo "🛠️  Local Testing:"
	@echo "  make test-unit        Run unit tests (fast, ~2s)"
	@echo "  make test-integration Run integration tests (slow, ~45s)"
	@echo "  make test-all         Run all tests"
	@echo ""
	@echo "📊 What Happens:"
	@echo "  - Builds 3 images (API, gateway, MCPJungle) via Docker Build Cloud"
	@echo "  - Runs unit tests (local)"
	@echo "  - Runs integration tests with Testcontainers Cloud"
	@echo "  - Security scan (Trivy)"
	@echo "  - Posts results to PR"
	@echo ""
	@echo "📁 Workflow File: .github/workflows/codex-build.yml"
	@echo ""
	@echo "For more info: cat QUICKSTART.md"

# ============================================================================
# Pilot Readiness Demo (AFR-96)
# ============================================================================

pilot-preflight:
	@bash scripts/pilot/pilot_preflight.sh

pilot-demo-rbac:
	@python3 scripts/pilot/demo_mcp_rbac_policy.py

pilot-demo-index:
	@python3 scripts/pilot/demo_repo_index.py

pilot-demo-incident:
	@bash scripts/pilot/demo_incident_drill.sh

pilot-demo:
	@bash scripts/pilot/run_pilot_demo.sh

