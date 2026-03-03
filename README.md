# HAAL-DEX (Document Extractor)

HAAL-DEX is a full-stack web application that transforms unstructured input documents into structured output documents through a configurable AI agentic pipeline. Built on AWS Strands Python SDK with a React 18+ TypeScript frontend and Python FastAPI backend.

## Features

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

## Quick Start

### Backend

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI runs at http://localhost:5173, backend API at http://localhost:8000.

## Testing

```bash
# Backend (443 tests)
cd backend
python -m pytest tests/ --tb=short -q

# Frontend (138 tests)
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
