# Dockerfile.dev
# Development Dockerfile for Phase 1

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY migrations/ ./migrations/

# Create upload directory
RUN mkdir -p /app/uploads

# Set Python path
ENV PYTHONPATH=/app

EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]