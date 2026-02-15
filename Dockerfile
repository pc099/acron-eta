# Asahi API - production image
# Build: docker build -t asahi .
# Run:   docker run -p 8000:8000 -e REDIS_URL=redis://... asahi

FROM python:3.12-slim

WORKDIR /app

# Install system deps only if needed (e.g. for build)
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY config/ config/
COPY main.py .

# Data dirs for logs and audit
RUN mkdir -p data/logs data/audit

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Railway sets PORT; default 8000 for local/docker-compose
CMD ["sh", "-c", "python -m uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
