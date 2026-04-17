# Builder Solution

This solution contains the standalone pipeline and builder application.

## Structure

- `frontend/` — Vite app entrypoint for the builder UI
- `backend/` — FastAPI entrypoint for the builder API

Both wrappers reuse shared code from the repository root:

- shared frontend code in `../frontend/src`
- shared backend code in `../backend/app`

## Run the backend

```bash
cd builder-solution/backend
pip install -e .
uvicorn main:app --reload --port 8002
```

## Run the frontend

```bash
cd builder-solution/frontend
npm install
npm run dev
```

By default the frontend proxies API and WebSocket traffic to `http://127.0.0.1:8002`.
