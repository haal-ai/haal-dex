# Chat Solution

This solution contains the standalone chat application.

## Structure

- `frontend/` — Vite app entrypoint for the chat UI
- `backend/` — FastAPI entrypoint for the chat API

Both wrappers reuse shared code from the repository root:

- shared frontend code in `../frontend/src`
- shared backend code in `../backend/app`

## Run the backend

```bash
cd chat-solution/backend
pip install -e .
uvicorn main:app --reload --port 8001
```

## Run the frontend

```bash
cd chat-solution/frontend
npm install
npm run dev
```

By default the frontend proxies API and WebSocket traffic to `http://127.0.0.1:8001`.
