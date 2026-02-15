# Asahi Dashboard (Frontend)

Next.js dashboard for the Asahi inference cost optimizer. Matches the [wireframes](docs/ASAHI_FRONTEND_WIREFRAMES.md) and [design system](docs/ASAHI_FRONTEND_DESIGN_SYSTEM.md).

## Setup

```bash
cd frontend
npm install
```

## Run locally

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Set **Settings → API Base URL** to your backend (e.g. `http://localhost:8000`) and add an API key (from Sign Up or admin).

## Build

```bash
npm run build
npm start
```

## Deploy (Vercel)

Set **Root Directory** to `frontend` and add env var `NEXT_PUBLIC_API_URL` to your Railway backend URL. See [DEPLOYMENT_VERCEL_RAILWAY.md](../docs/DEPLOYMENT_VERCEL_RAILWAY.md).

## Pages

- **/** – Landing (hero, features, metrics, CTA, footer)
- **/signup** – Self-serve signup (creates org + API key)
- **/dashboard** – Metrics cards, cache chart, recent inferences
- **/inference** – Run inference (prompt, routing mode, response)
- **/cache** – Cache stats and recent activity
- **/analytics** – Cost breakdown, trends, insights
- **/settings** – API URL and API key

Design: Asahi orange (#FF6B35), Inter font, 8px spacing grid.
