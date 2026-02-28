# ASAHI Backend (SaaS API)

This is the production backend for the ASAHI platform. It uses FastAPI + PostgreSQL + Redis.

> **Important:** Do NOT run `python main.py api` from the project root — that starts the old prototype backend. Always use this directory.

## Prerequisites

- Python 3.12+
- Docker (for PostgreSQL + Redis)

## Quick Start

### 1. Start database services

From the **project root**:

```bash
docker compose up -d db redis
```

This starts PostgreSQL (port 5432) and Redis (port 6379).

### 2. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure environment

A `.env` file should exist in `backend/` with:

```
DATABASE_URL=postgresql+asyncpg://asahi:asahi_dev_password@localhost:5432/asahi
REDIS_URL=redis://localhost:6379
CLERK_SECRET_KEY=<your-clerk-secret-key>
CORS_ORIGINS=["http://localhost:3000"]
DEBUG=true
```

### 4. Start the API server

```bash
cd backend
uvicorn app.main:app --reload
```

The API runs at **http://localhost:8000**. Docs at http://localhost:8000/docs (debug mode only).

### 5. Start the frontend

In a separate terminal:

```bash
cd frontend
npm run dev
```

Frontend runs at **http://localhost:3000**.

## Verify

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"1.0.0","redis":"connected"}
```

## Running Tests

```bash
cd backend
pytest tests/ -v
```

Tests use SQLite in-memory — no Docker needed.
