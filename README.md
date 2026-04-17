# HAAL-DEX (Document Extractor)

HAAL-DEX is organized as two separate top-level solutions built on shared code. The repository contains a standalone chat solution and a standalone builder solution, both backed by shared React and FastAPI modules.

## Features

- **Standalone chat solution** — Dedicated conversational interface based on AWS Strands
- **Drag-and-drop file upload** — PPTX, DOCX, PDF, TXT, HTML, Markdown
- **Configurable AI agent pipeline** — Sequential chain of agents, each with its own LLM provider
- **Multi-provider LLM support** — AWS Bedrock, OpenAI-compatible, GitHub Copilot
- **FAISS vector indexes** — Up to 4 domain-specific indexes for agent context enrichment
- **Agent tools** — File read/write, Python REPL, Shell (cross-platform)
- **Template-based output** — Jinja2 templates with validation, export to PDF/XML/DOCX
- **Bilingual UI** — English and French with i18next
- **Real-time streaming** — WebSocket-based LLM response streaming and execution monitoring
- **Full traceability** — Structured JSON execution logs, step-by-step replay, audit compliance
- **Configurable encryption** — Independent encryption for inputs, outputs, and logs
- **Token metrics** — Per-agent token/call tracking with CSV export
- **Dark/light theme** — OS preference detection with manual toggle

## Solutions

- `chat-solution/` — standalone chat product
- `builder-solution/` — standalone pipeline and builder product

These two folders are the only supported application surfaces. The root `frontend/` and `backend/` directories now act as shared implementation plus a chat-first development default, not as a separate combined product.

Shared implementation lives in:

- `frontend/src` — reusable React components, providers, and app shells
- `backend/app` — reusable FastAPI routers, services, and app factories

## Quick Start

### Chat solution backend

```bash
cd chat-solution/backend
pip install -e .
uvicorn main:app --reload --port 8001
```

### Chat solution frontend

```bash
cd chat-solution/frontend
npm install
npm run dev
```

### Builder solution backend

```bash
cd builder-solution/backend
pip install -e .
uvicorn main:app --reload --port 8002
```

### Builder solution frontend

```bash
cd builder-solution/frontend
npm install
npm run dev
```

The chat UI proxies to `http://localhost:8001` and the builder UI proxies to `http://localhost:8002`.

## Testing

```bash
# Shared backend tests
cd backend
python -m pytest tests/ --tb=short -q

# Shared frontend tests
cd frontend
npx vitest --run
```

## Documentation

- [README](docs/README.md) — Detailed setup, configuration, and API reference
- [Architecture](docs/ARCHITECTURE.md) — System architecture and component design
- [Use Cases](docs/USE_CASES.md) — Usage scenarios and workflows
- [Vision](docs/VISION_INTENT.md) — Product vision document

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18+, TypeScript, Vite, TailwindCSS, i18next |
| Backend | Python 3.11+, FastAPI, Uvicorn |
| AI Engine | AWS Strands Python SDK |
| Vector Store | FAISS |
| Templates | Jinja2, WeasyPrint, python-docx |
| Testing | pytest + Hypothesis, Vitest + fast-check |

## License

Internal use.
