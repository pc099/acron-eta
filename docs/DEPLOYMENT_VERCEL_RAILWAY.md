# Deploy Asahi: Backend (Railway) + Frontend (Vercel)

Deploy the Asahi API to **Railway** and the dashboard to **Vercel**, then connect them.

---

## 1. Deploy Backend to Railway

Follow [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md) to:

1. Create a Railway project and add **Redis** and **PostgreSQL**.
2. Add a service from this repo (backend: `Procfile` runs `uvicorn`).
3. Reference `REDIS_URL` and `DATABASE_URL` from the DB services.
4. Set required env vars: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `COHERE_API_KEY`, `DATABASE_URL`, `REDIS_URL`, and optionally `ASAHI_ENCRYPTION_KEY`, `ASAHI_AUTH_API_KEY_REQUIRED=true`.

After deploy, Railway gives you a public URL for the API (e.g. `https://asahi-api-production.up.railway.app`). **Copy this URL** — the frontend will use it.

### CORS (optional)

To restrict origins to your Vercel app, set in Railway:

- `ASAHI_API_CORS_ORIGINS` = `https://your-app.vercel.app` (comma-separated for multiple).

If unset, the API uses `["*"]`, which works for any frontend origin.

---

## 2. Deploy Frontend to Vercel

1. Push the repo (including the `frontend/` folder) to GitHub.
2. Go to [vercel.com](https://vercel.com) and **Add New Project**.
3. Import the **same repository**.
4. Set the **Root Directory** to `frontend` (so Vercel builds the Next.js app).
5. **Environment variables** (Vercel project → Settings → Environment Variables):

   | Name | Value | Notes |
   |------|--------|--------|
   | `NEXT_PUBLIC_API_URL` | `https://your-railway-api-url.up.railway.app` | Your Railway API URL (no trailing slash). |

   Users can also set the API URL in the dashboard **Settings** page (stored in browser).

6. Deploy. Vercel will build (`npm run build`) and serve the Next.js app.

---

## 3. Connect Services

- **Frontend → Backend:** Every API request uses `NEXT_PUBLIC_API_URL` (or the URL saved in Settings). The frontend sends the user’s API key in the `Authorization: Bearer <key>` header for `/infer`, `/metrics`, and `/analytics/*`.
- **API key:** Users get a key via **Sign Up** (if `DATABASE_URL` is set on the backend) or an admin creates one via `POST /governance/api-keys`. They paste the key in **Settings** in the dashboard (or it’s stored after signup in the same browser).

---

## 4. Checklist

- [ ] Railway: API service running; Redis + Postgres linked; env vars set.
- [ ] Railway: Public URL copied (e.g. `https://asahi-api.up.railway.app`).
- [ ] Vercel: Root directory = `frontend`; `NEXT_PUBLIC_API_URL` = Railway URL.
- [ ] Optional: `ASAHI_API_CORS_ORIGINS` on Railway = your Vercel domain.
- [ ] Test: Open Vercel app → Sign up or set API key in Settings → Run an inference from the Inference page; check Dashboard for metrics.

---

## 5. Optional: Monorepo / Single Repo

If the repo root is the backend and `frontend/` is a subfolder:

- **Railway:** Set **Root Directory** to `.` (or leave empty) and use the existing `Procfile` / `Dockerfile` at repo root so only the API is built and run.
- **Vercel:** Set **Root Directory** to `frontend` so only the Next.js app is built.

No code changes needed; each platform uses its own root.
