.PHONY: help install download build start stop restart logs health test load-test monitor clean gateway gateway-build gateway-start gateway-stop gateway-test gateway-demo mcpjungle mcpjungle-build mcpjungle-start mcpjungle-stop mcpjungle-logs mcpjungle-test mcpjungle-health jaeger-ui graph-test graph-example graph-ui neo4j-logs

help:
	@echo "MAX Serve + Llama 3.3 8B Infrastructure"
	@echo ""
	@echo "Available commands:"
	@echo "  make install      - Install Python dependencies"
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

install:
	pip install -r requirements.txt

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

graph-ui:
	@echo "Opening Neo4j Browser..."
	@echo "Neo4j Browser: http://localhost:7474"
	@echo "Username: neo4j"
	@echo "Password: neo4j_password"
	@command -v open >/dev/null 2>&1 && open http://localhost:7474 || echo "Open http://localhost:7474 in your browser"

neo4j-logs:
	@echo "Viewing Neo4j logs..."
	@docker compose logs -f neo4j
