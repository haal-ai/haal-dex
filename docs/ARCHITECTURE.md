# INTENT — Architecture Document

## System Overview

INTENT follows a layered client-server architecture with WebSocket streaming for real-time communication. The frontend is a React 18+ SPA that communicates with a Python FastAPI backend over REST and WebSocket. The backend's agentic engine is built entirely on the AWS Strands Python SDK.

```
┌──────────────────────────────────────────────────────────────┐
│                    INTENT_UI (React 18+)                      │
│  DropZone │ ChatPanel │ OutputViewer │ ExecutionTimeline │ …  │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP (REST) + WebSocket
┌──────────────────────▼───────────────────────────────────────┐
│                    FastAPI Backend                             │
│  Auth Middleware → API Routers → PipelineOrchestrator          │
│                                  ↓                            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              Agentic Engine (Strands SDK)                │  │
│  │  GraphFactory → AgentFactory → ModelFactory              │  │
│  │  @tool functions (read, write, repl, shell, query_faiss) │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐    │
│  │ ExecutionLog │ │ MetricsCollect│ │ EncryptionService  │    │
│  └──────────────┘ └──────────────┘ └────────────────────┘    │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐    │
│  │ TemplateReg  │ │ OutputGen    │ │ ReplayEngine       │    │
│  └──────────────┘ └──────────────┘ └────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
         │                    │                    │
    ┌────▼────┐        ┌─────▼─────┐       ┌──────▼──────┐
    │ SQLite/ │        │ FAISS     │       │ File System │
    │ Postgres│        │ Indexes   │       │ (uploads,   │
    │         │        │ (up to 4) │       │  logs, tpl) │
    └─────────┘        └───────────┘       └─────────────┘
```

## Layer Breakdown

### 1. Frontend Layer (INTENT_UI)

Built with React 18+, TypeScript, Vite, and TailwindCSS.

Components:

| Component | Responsibility |
|-----------|---------------|
| `DropZone` | Drag-and-drop file upload with format validation and preview. Accepts PPTX, DOCX, PDF, TXT, HTML, MD. |
| `ChatPanel` | Bilingual (EN/FR) natural language chat. Messages stream in real-time over WebSocket. |
| `OutputViewer` | Document preview and export (PDF, XML, DOCX). |
| `ExecutionTimeline` | Real-time agent status display (pending/running/completed/failed) with live log streaming. |
| `MetricsDashboard` | Token counts and LLM call metrics per agent during execution. |
| `ReplayViewer` | Step-by-step replay of past pipeline executions. |
| `ConfigPanel` | Admin-only CRUD for pipeline configurations. |
| `AuthGate` | Login flow, JWT token management, role-based route protection. |
| `ThemeProvider` | Dark/light theme toggle with OS preference detection. |
| `I18nProvider` | i18next setup with browser language detection and manual EN/FR switching. |

### 2. API Layer

FastAPI application with 8 routers:

| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth` | `/api/auth` | Login, token validation, user profile |
| `files` | `/api/files` | File upload with format validation |
| `pipeline` | `/api/pipeline` | Pipeline execution (REST + WebSocket) |
| `config` | `/api/config` | Pipeline configuration CRUD (admin) |
| `output` | `/api/output` | Document preview and export |
| `metrics` | `/api/metrics` | Session metrics and CSV export |
| `replay` | `/api/replay` | Execution replay data |
| `chat` | `/api/ws/chat` | WebSocket chat streaming |

Auth middleware validates JWT tokens and enforces RBAC (admin vs user roles) on all protected endpoints.

### 3. Pipeline Orchestrator

`PipelineOrchestrator` is the central coordinator that wires the full flow:

```
File Upload → Decrypt (if configured) → Build Strands Graph → Execute Agents
    → Log Steps → Collect Metrics → Render Output → Encrypt Output (if configured)
```

It delegates to:
- `GraphFactory` for building and executing the Strands agent graph
- `ExecutionLogger` for per-step structured logging
- `MetricsCollector` for token/call tracking
- `OutputGenerator` for Jinja2 template rendering
- `EncryptionService` for input decryption and output encryption

### 4. Agentic Engine

The engine is built on the AWS Strands Python SDK and consists of three factories:

**GraphFactory** — Translates a `PipelineConfig` into a `strands.multiagent.Graph` with sequential topology using `GraphBuilder`. Each agent node is connected in sequence so that each agent's output flows to the next. Supports both synchronous execution and streaming via `graph.stream_async()`.

**AgentFactory** — Creates `strands.Agent` instances from `AgentConfig`. Each agent gets:
- A model provider (via ModelFactory)
- A filtered set of `@tool` functions (only those permitted by the pipeline config)
- A system prompt
- A name identifier

**ModelFactory** — Creates Strands model provider instances based on `ProviderConfig`:
- `strands.models.BedrockModel` for AWS Bedrock
- `strands.models.openai.OpenAIModel` for OpenAI-compatible endpoints (OpenAI, Azure OpenAI, Mistral, vLLM, Ollama)
- Custom `GitHubCopilotModel` (extends `strands.models.Model`) for GitHub Copilot via OAuth

### 5. Agent Tools

Five `@tool`-decorated functions available to agents:

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents from the local file system |
| `write_file` | Write content to a file |
| `python_repl` | Execute Python code (cross-platform: Windows + Linux) |
| `shell` | Execute shell commands (Bash on Linux, PowerShell on Windows) |
| `query_faiss` | Query a FAISS index for similar documents (uses `ToolContext.invocation_state` for shared state) |

Tool permissions are enforced at the `AgentFactory` level — agents only receive the tools they're permitted to use. Denied tool access is logged.

### 6. Services Layer

| Service | Responsibility |
|---------|---------------|
| `FileIngestionService` | Receives uploaded files, validates format, decrypts if configured |
| `ConfigParser` | Parses pipeline configs from YAML/JSON, serializes back (round-trip safe) |
| `ConfigValidator` | Validates pipeline config structure and field values before execution |
| `EncryptionService` | Configurable encryption/decryption for inputs, outputs, and logs independently (Fernet/AES-GCM) |
| `ExecutionLogger` | Records per-step structured JSON logs (timestamp, agent, prompts, responses, decisions) |
| `MetricsCollector` | Tracks input/output tokens and LLM call counts per agent per session, exports CSV |
| `ReplayEngine` | Loads past executions from stored logs for step-by-step replay |
| `TemplateRegistry` | Stores and manages output templates (format, structure, validation rules, metadata) |
| `OutputGenerator` | Renders documents via Jinja2 templates, validates against rules, exports to PDF/XML/DOCX |
| `AuthService` | JWT authentication, token issuance/validation, RBAC enforcement |

### 7. FAISS Index Manager

Manages up to 4 concurrent FAISS vector indexes per pipeline execution. Each index represents a different document corpus (standards, guidelines, catalogs, examples). Agents query indexes via the `query_faiss` tool through `invocation_state` shared context.

## Communication Patterns

### REST
Used for: file upload, pipeline config CRUD, output export, metrics download, authentication.

### WebSocket
Two WebSocket endpoints:
- `/api/ws/chat/{session_id}` — Bidirectional chat with real-time LLM response streaming
- `/api/ws/execution/{session_id}` — Unidirectional stream of pipeline execution events

Execution events map from Strands `graph.stream_async()` events:
- `multiagent_node_start` → `agent_start`
- `multiagent_node_stream` → `llm_token`
- `multiagent_node_stop` → `agent_complete`
- `multiagent_result` → `pipeline_complete`

## Data Flow

### Pipeline Execution Flow

```
1. User uploads files via DropZone → POST /api/files/upload
2. User triggers pipeline → POST /api/pipeline/execute (or connects to WS)
3. PipelineOrchestrator:
   a. Creates session, logs session start
   b. Decrypts input files if encryption configured
   c. GraphFactory builds Strands Graph from PipelineConfig
   d. Graph executes agents sequentially:
      Agent₁(input) → output₁ → Agent₂(output₁) → output₂ → … → AgentN
   e. Each agent can use its permitted tools and query FAISS indexes
   f. ExecutionLogger records each step
   g. MetricsCollector tracks tokens per agent
4. OutputGenerator renders final document from Jinja2 template
5. EncryptionService encrypts output if configured
6. User previews/exports via OutputViewer
```

### Streaming Flow

```
Frontend connects to WS /api/ws/execution/{session_id}
    ← agent_start (agent name, step number)
    ← llm_token (streaming text chunks)
    ← agent_complete (agent finished)
    ← … (repeat for each agent)
    ← pipeline_complete (final status, execution order, timing)
```

## Data Models

Key data models (defined in `backend/app/models/`):

- `PipelineConfig` — Pipeline definition: name, agent list, output config, timeout
- `AgentConfig` — Per-agent: name, model, provider config, tools, FAISS indexes, system prompt
- `ProviderConfig` — LLM provider: type (bedrock/openai_compatible/github_copilot), model ID, endpoint, credentials
- `Session` — Execution session: ID, user, status, timestamps, input/output references
- `ExecutionStep` — Per-step log: agent, timestamp, prompts, responses, decisions, provider/model
- `IngestedFile` — Uploaded file: name, format, size, content, encryption status
- `RenderedDocument` — Generated output: template, format, content, metadata, validation result
- `EncryptionConfig` — Per-target encryption: algorithm, key reference, target (input/output/log)

## Error Handling

Errors follow a consistent JSON structure:

```json
{
  "error": {
    "code": "PIPELINE_AGENT_FAILURE",
    "message": "Agent 'content_generator' failed at step 3",
    "details": { "agent_name": "...", "step_number": 3, "cause": "..." },
    "timestamp": "2026-03-15T14:30:00Z",
    "session_id": "abc-123"
  }
}
```

Error categories include: file format errors (400), upload failures (500), decryption failures (400), config validation errors (422), agent execution failures (from Strands Graph), LLM provider errors, FAISS index unavailability, tool permission denials, template validation failures, and auth errors (401/403).

## Security

- JWT-based authentication on all protected endpoints
- Role-based access control (admin vs user)
- Independent encryption for inputs, outputs, and logs (Fernet/AES-GCM)
- Tool permission enforcement per agent
- CORS configuration for frontend origin
