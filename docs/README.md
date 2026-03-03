# INTENT

INTENT is a full-stack web application that transforms unstructured input documents into structured output documents through a configurable AI agentic pipeline. Users submit files via drag-and-drop, interact through a bilingual chat interface (EN/FR), and receive generated documents rendered from configurable Jinja2 templates.

The backend orchestrates a sequential chain of AI agents using the AWS Strands Python SDK, each with its own LLM provider, tool access, and FAISS index bindings. Every execution step is logged for full traceability, replay, and audit compliance.

## Prerequisites

- Python 3.11+ (recommended on Windows: Python 3.12)
- Node.js 18+ (recommended: Node.js 20.19+)
- npm 9+

## Project Structure

```
intent/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── api/                # REST & WebSocket endpoints
│   │   ├── engine/             # Agentic engine (GraphFactory, AgentFactory, ModelFactory, tools)
│   │   ├── middleware/         # Auth middleware (JWT)
│   │   ├── models/             # Data models (Pydantic/dataclass)
│   │   ├── services/           # Business logic services
│   │   ├── config.py           # Application settings (env vars)
│   │   ├── main.py             # FastAPI app entry point
│   │   └── pipeline_orchestrator.py  # Full pipeline flow coordinator
│   ├── tests/
│   │   ├── unit/               # Unit tests (pytest)
│   │   ├── property/           # Property-based tests (Hypothesis)
│   │   └── integration/        # Integration tests
│   └── pyproject.toml
├── frontend/                   # React 18+ TypeScript frontend
│   ├── src/
│   │   ├── components/         # UI components (DropZone, ChatPanel, OutputViewer, etc.)
│   │   ├── providers/          # ThemeProvider, I18nProvider
│   │   ├── hooks/              # useAuth
│   │   ├── i18n/               # EN/FR translation files
│   │   ├── types/              # TypeScript type definitions
│   │   └── App.tsx             # Main application layout
│   └── package.json
└── intent/
    └── VISION_INTENT.md        # Product vision document
```

## Backend Setup

### Install dependencies

```bash
cd backend
pip install -e ".[dev]"
```

If you have multiple Python versions installed, ensure you are using the intended one (e.g. Python 3.12 on Windows).

### Environment variables

All settings are loaded from environment variables with sensible defaults for local development. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `INTENT_DEBUG` | `false` | Enable debug mode |
| `INTENT_HOST` | `0.0.0.0` | Server bind host |
| `INTENT_PORT` | `8000` | Server bind port |
| `INTENT_DATABASE_URL` | `sqlite:///./intent.db` | Database connection string |
| `INTENT_SECRET_KEY` | `change-me-in-production` | JWT signing secret |
| `INTENT_JWT_EXPIRATION_MINUTES` | `60` | Token expiration |
| `INTENT_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `INTENT_ENCRYPTION_KEY_INPUT` | *(empty)* | Encryption key for input files |
| `INTENT_ENCRYPTION_KEY_OUTPUT` | *(empty)* | Encryption key for output documents |
| `INTENT_ENCRYPTION_KEY_LOG` | *(empty)* | Encryption key for execution logs |
| `INTENT_UPLOAD_DIR` | `./uploads` | File upload directory |
| `INTENT_LOG_DIR` | `./logs` | Execution log directory |
| `INTENT_FAISS_INDEX_DIR` | `./faiss_indexes` | FAISS index directory |
| `INTENT_TEMPLATE_DIR` | `./templates` | Jinja2 template directory |

### AWS Bedrock (local development)

If you use `provider_type: "bedrock"` in pipeline configs, credentials and region are resolved from standard AWS configuration:

- Use an AWS CLI profile (including SSO) from `~/.aws/config` and `~/.aws/credentials`.
- Set `AWS_PROFILE` to the profile name you want the backend to use.
- Ensure a region is available via `AWS_REGION` or `AWS_DEFAULT_REGION` (or via the selected profile's `region` setting).
- For SSO profiles, run `aws sso login --profile <profile>` before starting the backend.

Pipeline configs may omit the Bedrock `region` field; the backend will fall back to `AWS_REGION` / `AWS_DEFAULT_REGION` / `~/.aws/config` (for `AWS_PROFILE`, defaulting to `default`).

### Run the backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. A health check endpoint is at `GET /health`.

## Frontend Setup

### Install dependencies

```bash
cd frontend
npm install
```

### Run the frontend

```bash
cd frontend
npm run dev
```

The UI will be available at `http://localhost:5173`.

During local development the frontend calls backend endpoints at `/api/...` (and WebSockets under `/api/ws/...`). Ensure your Vite dev server proxies `/api` to the backend (this repo is configured accordingly).

## Default Dev Credentials

For local development/testing, the backend ships with an in-memory user store:

- Username: `admin` Password: `admin`
- Username: `user` Password: `user`

### Build for production

```bash
cd frontend
npm run build
```

## API Overview

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/login` | Authenticate and receive JWT token |
| `GET` | `/api/auth/me` | Get current user profile |
| `POST` | `/api/files/upload` | Upload input files (multipart) |
| `POST` | `/api/pipeline/execute` | Execute a pipeline |
| `GET/POST/PUT/DELETE` | `/api/config/pipelines` | Pipeline configuration CRUD |
| `GET` | `/api/output/{session_id}/preview` | Preview generated output |
| `GET` | `/api/output/{session_id}/export?format=pdf\|docx\|md\|html\|pptx` | Export output |
| `GET` | `/api/metrics/{session_id}` | Session metrics |
| `GET` | `/api/metrics/{session_id}/csv` | Export metrics as CSV |
| `GET` | `/api/replay/{session_id}` | Load replay data |
| `GET` | `/api/replay/{session_id}/step/{step_number}` | Get specific replay step |

### WebSocket Endpoints

| Path | Description |
|------|-------------|
| `WS /api/ws/chat/{session_id}` | Bidirectional chat with LLM streaming |
| `WS /api/ws/execution/{session_id}` | Real-time pipeline execution events |

### Authentication

All endpoints (except `/health` and `/api/auth/login`) require a valid JWT token in the `Authorization: Bearer <token>` header. Admin-only endpoints (config, template, provider management) require the `admin` role.

## Testing

### Backend tests

From the `backend/` directory:

```bash
# Run all tests
python -m pytest tests/ --tb=short -q

# Run only unit tests
python -m pytest tests/unit/ --tb=short -q

# Run only property-based tests
python -m pytest tests/property/ --tb=short -q

# Run only integration tests
python -m pytest tests/integration/ --tb=short -q
```

The backend test suite includes 443 tests across unit, property-based (Hypothesis), and integration tests.

### Frontend tests

From the `frontend/` directory:

```bash
# Run all tests
npx vitest --run

# Run with coverage
npx vitest --run --coverage
```

The frontend test suite includes 138 tests across 14 test files, covering unit tests and property-based tests (fast-check).

### Test categories

- **Unit tests**: Verify specific behavior, edge cases, and error conditions for each component
- **Property-based tests**: Verify universal correctness properties across randomly generated inputs (29 properties defined)
- **Integration tests**: End-to-end flows including pipeline execution, WebSocket streaming, and authentication

## Tech Stack

### Backend
- Python 3.11+, FastAPI, Uvicorn
- AWS Strands Python SDK (Agent, GraphBuilder, model providers)
- FAISS (vector similarity search)
- Jinja2 (template rendering), WeasyPrint (PDF), python-docx (DOCX), python-pptx (PPTX)
- Cryptography (Fernet/AES-GCM encryption)
- Hypothesis (property-based testing), pytest

### Frontend
- React 18+, TypeScript, Vite
- TailwindCSS, shadcn/ui patterns
- i18next (EN/FR internationalization)
- react-dropzone (file upload)
- fast-check (property-based testing), Vitest, Testing Library

## License

Internal use.
