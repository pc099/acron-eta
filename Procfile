# Railway / Heroku-style process file.
# Starts the NEW backend (backend/app/) — NOT the old src/api/.
# Railway sets PORT; default 8000 for local.
web: sh -c 'cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'
