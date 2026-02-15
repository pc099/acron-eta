# Railway / Heroku-style process file.
# Use when deploying without Docker (e.g. Railway Nixpacks).
# Railway sets PORT; default 8000 for local.
web: uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}
