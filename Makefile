.PHONY: help install dev test migrate run docker-up docker-down clean ai-test

help:
	@echo "Available commands:"
	@echo "  install       - Install all dependencies (Phase 1 & 2)"
	@echo "  install-dev   - Install with development dependencies"
	@echo "  dev          - Run development server"
	@echo "  test         - Run tests"
	@echo "  migrate      - Run database migrations"
	@echo "  docker-up    - Start Docker containers"
	@echo "  docker-down  - Stop Docker containers"
	@echo "  clean        - Clean temporary files"
	@echo "  ai-test      - Test AI services connectivity"
	@echo "  process-docs - Process all pending documents"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

dev:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

migrate:
	alembic upgrade head

docker-up:
	docker-compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@echo "Services started. Access the app at http://localhost:8000"

docker-down:
	docker-compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage

# Phase 2 specific commands
ai-test:
	@echo "Testing AI services connectivity..."
	@curl -s http://localhost:8000/api/ai/stats | python -m json.tool

process-docs:
	@echo "Processing all pending documents..."
	@python scripts/process_pending_docs.py

# Development helpers
redis-cli:
	docker-compose exec redis redis-cli

db-shell:
	docker-compose exec postgres psql -U postgres -d jahresabschluss

logs:
	docker-compose logs -f app

logs-all:
	docker-compose logs -f

# Setup commands
setup: install migrate
	@echo "Setup complete. Run 'make dev' to start the server."

setup-docker: docker-up
	@echo "Docker setup complete. Checking health..."
	@sleep 3
	@curl -s http://localhost:8000/health | python -m json.tool