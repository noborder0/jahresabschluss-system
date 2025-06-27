# Makefile for Jahresabschluss-System Phase 1

.PHONY: help install init-db run clean test

help:
	@echo "Available commands:"
	@echo "  make install    - Install Python dependencies"
	@echo "  make init-db    - Initialize database"
	@echo "  make run        - Start the application"
	@echo "  make clean      - Clean temporary files"
	@echo "  make test       - Run tests (when available)"

install:
	pip install -r requirements.txt

init-db:
	python init_db.py

run:
	python run.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".DS_Store" -delete

test:
	@echo "Tests will be added in future phases"
	# pytest tests/