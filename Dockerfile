# Asahi API - production image (NEW backend)
# Build: docker build -t asahi .
# Run:   docker run -p 8000:8000 -e DATABASE_URL=... -e REDIS_URL=... asahi

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the new backend
COPY backend/ backend/

# Copy src/ and config/ — needed by backend/app/core/optimizer.py bridge
COPY src/ src/
COPY config/ config/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Railway sets PORT; default 8000 for local/docker-compose
CMD ["sh", "-c", "cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
