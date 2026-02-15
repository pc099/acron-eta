# Accounts and Tokens Guide

This guide covers: why Postgres and Redis start empty, how to connect Pinecone, and **every account and token** you need to create or generate for Asahi.

---

## 1. Why Postgres and Redis Are “Empty”

### Postgres

- **Tables** are created automatically on app startup (`init_db`). You should see `orgs` and `api_keys` (and any others from `src/db/models.py`).
- **Data** stays empty until:
  - **Sign up:** A user hits `POST /signup` (from the frontend or API). That creates one row in `orgs` and one in `api_keys` (with the new API key).
  - **Admin creates a key:** Someone calls `POST /governance/api-keys` (with `X-Admin-Secret` or an admin-scoped API key). That inserts a row into `api_keys` (and optionally you can create orgs manually in DB if you add that flow).
- So “empty” at the beginning is normal. After the first signup or first admin-created key, Postgres will have data.

**Quick check:** Sign up once from your frontend (or curl `POST /signup`), then inspect the `orgs` and `api_keys` tables in Railway Postgres (or any SQL client).

### Redis

- Redis is used as **Tier 1 (exact-match) cache** for inference.
- It is **empty** until the app handles inference requests. Each cacheable request stores an entry; repeated identical prompts then hit the cache.
- So “empty” at the beginning is also normal. Run a few inference requests (e.g. from the Inference page or `POST /infer`), then run the same prompt again — the second time should be a cache hit and Redis will hold that key.

**Redis URL set but Redis still looks empty?**

1. **Confirm the app is using Redis:** Call `GET /health` and check the response for `cache_backend`. If it is `"redis"`, the app connected at startup. If it is `"memory"`, Redis init or ping failed — check deploy logs for “Redis cache init or ping failed” and fix `REDIS_URL` (e.g. use `rediss://` for TLS, correct password, correct host).
2. **Keys appear only after a cache miss + successful inference:** The app writes to Redis only when it **stores** a new result (after running the LLM). So you must run at least one **successful** inference (valid API key, prompt, and LLM provider keys set). If inference fails before the result is cached, no key is written.
3. **Key pattern:** In Redis you should see keys like `asahi:t1:hits`, `asahi:t1:misses`, and `asahi:t1:<org_id>:<md5>` or `asahi:t1:<md5>` for each cached prompt. Use `SCAN 0 MATCH asahi:t1:*` to list them.

**Summary:** Postgres fills when you sign up or create API keys; Redis fills when you run inference. Both can start empty.

---

## 2. Connecting Pinecone (Tier 2 Semantic Cache)

Pinecone is **optional**. Without it, Asahi uses an in-memory vector store for Tier 2 (works for one instance; lost on restart). With Pinecone, Tier 2 is persistent and can be shared across instances.

### Step 1: Create a Pinecone account

1. Go to [pinecone.io](https://www.pinecone.io/) and sign up.
2. Create a project if prompted (free tier is enough to start).

### Step 2: Create an API key

1. In the Pinecone console, open **API Keys** (or **Project** → API Keys).
2. Click **Create API Key**.
3. Copy the key (you won’t see it again). This is your **PINECONE_API_KEY**.

### Step 3: Create an index

1. In the console, go to **Indexes** → **Create Index**.
2. Set:
   - **Name:** `asahi-vectors` (or any name; then set `PINECONE_INDEX` to that name).
   - **Dimensions:** **1024** (must match Asahi’s embedding dimension from `config/config.yaml`: `embeddings.dimension: 1024`).
   - **Metric:** **cosine**.
   - **Cloud/region:** Any (e.g. same as Railway for lower latency).
3. Create the index and wait until it’s ready.

### Step 4: Set environment variables (e.g. on Railway)

In your **asahi** service variables, add:

| Variable | Value |
|----------|--------|
| `PINECONE_API_KEY` | The API key from Step 2. |
| `PINECONE_INDEX` | Index name (default is `asahi-vectors`; only set if you used a different name). |

**Optional (if your Pinecone host is not the default):**

- Some Pinecone setups use a host like `https://....pinecone.io`. The current code uses the Pinecone client’s default (index is inferred from the index name). If you need a specific environment, check Pinecone’s docs for the correct env var (e.g. `PINECONE_ENVIRONMENT` or host override); the code may need a small change to pass that through.

After redeploy, logs should show: **“Tier 2 using Pinecone vector DB”**. If Pinecone init fails, the app falls back to in-memory Tier 2 and logs a warning.

---

## 3. All Accounts and Tokens You Need

### 3.1 Required for inference (LLM providers)

| Account | Purpose | Where to get the token | Env var |
|--------|---------|------------------------|--------|
| **OpenAI** | GPT models (routing + inference) | [platform.openai.com](https://platform.openai.com) → API Keys → Create | `OPENAI_API_KEY` |
| **Anthropic** | Claude models (inference) | [console.anthropic.com](https://console.anthropic.com) → API Keys | `ANTHROPIC_API_KEY` |
| **Cohere** | Embeddings for Tier 2 semantic cache | [dashboard.cohere.com](https://dashboard.cohere.com) → API Keys (free tier available) | `COHERE_API_KEY` |

### 3.2 From Railway (no extra account)

| Resource | Purpose | Env var | How you get it |
|----------|---------|--------|----------------|
| **PostgreSQL** | Orgs, API keys | `DATABASE_URL` | Add Postgres to the project → reference `DATABASE_URL` in the asahi service. |
| **Redis** | Tier 1 cache | `REDIS_URL` | Add Redis to the project → reference `REDIS_URL` in the asahi service. |

You don’t “create” these tokens; Railway gives you the URLs when you add the services and you reference them in the asahi service variables.

### 3.3 Optional: Pinecone (Tier 2 vector store)

| Account | Purpose | Where to get the token | Env var |
|--------|---------|------------------------|--------|
| **Pinecone** | Tier 2 semantic cache (persistent) | [pinecone.io](https://www.pinecone.io) → API Keys + create index (dimension 1024, cosine) | `PINECONE_API_KEY`, `PINECONE_INDEX` (optional, default `asahi-vectors`) |

### 3.4 Generated by you (no account)

| Token / secret | Purpose | How to generate | Env var |
|----------------|--------|------------------|--------|
| **ASAHI_ENCRYPTION_KEY** | Encrypting sensitive data (e.g. policies) | 64-char hex | `ASAHI_ENCRYPTION_KEY` |
| **ASAHI_ADMIN_SECRET** | Protecting `POST /governance/api-keys` (optional) | Any long random string | `ASAHI_ADMIN_SECRET` |

**Generate ASAHI_ENCRYPTION_KEY (64-char hex):**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and set it as `ASAHI_ENCRYPTION_KEY` in Railway (and never commit it).

**ASAHI_ADMIN_SECRET:** Pick a long random string (e.g. `openssl rand -hex 24`) and set it in Railway. Clients that create API keys must send it as `X-Admin-Secret`.

### 3.5 Optional: Welcome email (signup)

| Account | Purpose | Where to get the token | Env var |
|--------|---------|------------------------|--------|
| **SendGrid** | Welcome email after signup | [sendgrid.com](https://sendgrid.com) → API Keys | `SENDGRID_API_KEY` |
| (optional) | From-address for emails | Your verified sender in SendGrid | `ASAHI_FROM_EMAIL` (e.g. `noreply@yourdomain.com`) |

If you don’t set these, signup still works; only the welcome email is skipped.

### 3.6 Frontend (Vercel)

| Item | Purpose | Where | Env var |
|------|---------|--------|--------|
| **Backend API URL** | So the dashboard can call the API | Your Railway asahi service URL (e.g. `https://asahi-production.up.railway.app`) | `NEXT_PUBLIC_API_URL` |

No “token” for the frontend itself; users can also set the API URL in the dashboard Settings and store their API key there (from signup or admin-created).

---

## 4. Checklist: What to Create and Where to Set It

Use this as a quick checklist.

- [ ] **OpenAI** – Create API key → set `OPENAI_API_KEY` in Railway (asahi service).
- [ ] **Anthropic** – Create API key → set `ANTHROPIC_API_KEY` in Railway.
- [ ] **Cohere** – Create API key → set `COHERE_API_KEY` in Railway.
- [ ] **Railway Postgres** – Add Postgres, reference `DATABASE_URL` in asahi service.
- [ ] **Railway Redis** – Add Redis, reference `REDIS_URL` in asahi service.
- [ ] **ASAHI_ENCRYPTION_KEY** – Run `python -c "import secrets; print(secrets.token_hex(32))"` → set in Railway.
- [ ] **ASAHI_ADMIN_SECRET** (optional) – Generate a secret → set in Railway; use as `X-Admin-Secret` when creating keys.
- [ ] **Pinecone** (optional) – Sign up → Create API key → Create index (name `asahi-vectors`, dimension **1024**, metric **cosine**) → set `PINECONE_API_KEY` (and `PINECONE_INDEX` if different name) in Railway.
- [ ] **SendGrid** (optional) – Sign up → Create API key → set `SENDGRID_API_KEY` (and optionally `ASAHI_FROM_EMAIL`) in Railway.
- [ ] **Vercel** – Set `NEXT_PUBLIC_API_URL` to your Railway asahi URL.

After that, Postgres will fill when users sign up or you create keys; Redis will fill when you run inference; Pinecone will fill when Tier 2 semantic cache is used (and `PINECONE_API_KEY` is set).
