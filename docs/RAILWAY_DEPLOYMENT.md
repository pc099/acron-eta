# Deploying Asahi to Railway

This guide covers deploying the Asahi API to [Railway](https://railway.app) with **managed Redis** and **managed PostgreSQL**. Railway provides both as add-ons with connection URLs injected via environment variables.

---

## 1. Prerequisites

- A [Railway](https://railway.app) account (GitHub login)
- This repo pushed to GitHub (or use Railway CLI)

---

## 2. Create a New Project

1. Go to [railway.app](https://railway.app) and create a new project.
2. Choose **Deploy from GitHub repo** and select this repository (or connect later and use `railway up`).

---

## 3. Add Redis and PostgreSQL

1. In the project, click **+ New** and add **Database**.
2. Add **Redis** (e.g. “Add Redis” from the database list).
3. Add **PostgreSQL** (e.g. “Add PostgreSQL”).
4. Railway will create each service and expose **variables** (e.g. `REDIS_URL`, `DATABASE_URL`). You will reference these in the Asahi service.

---

## 4. Add the Asahi Service

1. Click **+ New** → **GitHub Repo** (or **Empty Service** and deploy with CLI).
2. Select this repository.
3. Railway will detect the app (Python/Nixpacks or Dockerfile).

**Build / start behaviour:**

- If you use the **Dockerfile**: Railway builds the image and runs the container. The Dockerfile uses `$PORT` (default 8000).
- If you use **Nixpacks** (no Dockerfile): Railway uses `Procfile` or `railway.toml`; the start command runs `uvicorn` on `$PORT`.

---

## 5. Link Redis and PostgreSQL to Asahi

1. Open the **Asahi service** (your API).
2. Go to **Variables**.
3. **Reference** the variables from the Redis and Postgres services:
   - From the Redis service: add **Variable Reference** → `REDIS_URL`.
   - From the PostgreSQL service: add **Variable Reference** → `DATABASE_URL`.

So the Asahi service gets:

- `REDIS_URL` – from Railway Redis (e.g. `redis://default:...@...railway.app:...`)
- `DATABASE_URL` – from Railway Postgres (e.g. `postgresql://postgres:...@...railway.app:...`)

---

## 6. Required Environment Variables

Set (or reference) these in the Asahi service:

| Variable | Required | Description |
|----------|----------|-------------|
| `REDIS_URL` | Yes (for Tier 1 cache) | From Railway Redis add-on |
| `DATABASE_URL` | Yes (for API key storage) | From Railway Postgres add-on |
| `OPENAI_API_KEY` | Yes (for inference) | Your OpenAI API key |
| `ANTHROPIC_API_KEY` | Yes (for inference) | Your Anthropic API key |
| `COHERE_API_KEY` | Yes (for Tier 2 semantic cache) | Your Cohere API key |
| `ASAHI_ENCRYPTION_KEY` | Recommended | 64-char hex (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `PORT` | Set by Railway | Do not override; Railway sets this |

Optional:

- `ASAHI_API_PORT` – overridden by Railway’s `PORT` in production.
- `ASAHI_AUTH_API_KEY_REQUIRED` – set to `true` to enforce API key auth.

---

## 7. Enable API Key Auth (Optional)

To require API keys for all non-health requests:

1. In **Variables**, add or override:
   - `ASAHI_AUTH_API_KEY_REQUIRED` = `true`
2. Create API keys via the auth middleware (e.g. an admin endpoint or script that calls `AuthMiddleware.generate_api_key` and stores in DB). With `DATABASE_URL` set, keys are stored in PostgreSQL and validated on each request.

---

## 8. Generate a Public URL

1. Open the Asahi service.
2. Go to **Settings** → **Networking** (or **Deploy**).
3. Click **Generate Domain**.
4. Use the generated URL (e.g. `https://asahi-production.up.railway.app`) for API calls and docs.

---

## 9. Deploy and Verify

1. Trigger a deploy (push to the linked branch or use **Deploy** in the dashboard).
2. After the build finishes, open:
   - `https://<your-domain>/health` – should return `{"status":"healthy",...}`.
   - `https://<your-domain>/docs` – Swagger UI.
3. Call `POST /infer` or `POST /v1/chat/completions` with your API key (if auth is enabled) and verify responses.

---

## 10. Database Schema (PostgreSQL)

On first run, when `DATABASE_URL` is set, the app creates the required tables if they do not exist:

- **orgs** – organisation/tenant records.
- **api_keys** – API key hashes and metadata (prefix, org_id, scopes, expiry, revoked).

No manual migration is required for the initial deploy; tables are created via `init_db(engine)` at startup.

---

## 11. Troubleshooting

- **App won’t start:** Check that the start command listens on `0.0.0.0` and uses `$PORT`. The provided Dockerfile and Procfile do this.
- **Redis/Postgres connection errors:** Ensure `REDIS_URL` and `DATABASE_URL` are **variable references** to the Redis and Postgres services (not pasted from another environment).
- **401 Unauthorized:** If `ASAHI_AUTH_API_KEY_REQUIRED` is true, send `Authorization: Bearer <your-api-key>`.
- **Cohere/OpenAI/Anthropic errors:** Verify the corresponding `*_API_KEY` variables are set in the Asahi service.

---

## 12. Cost Notes

- Railway charges for usage (services, bandwidth). Redis and PostgreSQL add-ons each have their own cost.
- Check [Railway pricing](https://railway.app/pricing) and set billing limits if needed.

---

**Summary:** Add Redis and Postgres in Railway, link `REDIS_URL` and `DATABASE_URL` to the Asahi service, set LLM and Cohere keys (and optionally `ASAHI_ENCRYPTION_KEY` and auth), then deploy. Tables are created automatically; use the generated domain for the API and docs.
