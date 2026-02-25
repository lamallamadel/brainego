.PHONY: help install download build start stop restart logs health test load-test monitor clean

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
