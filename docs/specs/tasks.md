# Implementation Plan: INTENT

## Overview

Incremental implementation of the INTENT full-stack application: a configurable AI agentic pipeline system built on AWS Strands Python SDK (backend) with a React 18+ TypeScript frontend. Tasks are ordered to build foundational layers first (data models, auth, encryption), then core engine components (tools, models, agents, graph), then output/logging, then frontend, and finally integration wiring.

## Tasks

- [x] 1. Project scaffolding and data models
  - [x] 1.1 Initialize backend project structure with FastAPI, dependencies, and configuration
    - Create `backend/` directory with `pyproject.toml` (FastAPI, uvicorn, strands-agents, strands-agents-builder, pyyaml, hypothesis, pytest, faiss-cpu, sentence-transformers, cryptography, python-multipart, python-magic, Jinja2, WeasyPrint, python-docx, lxml, structlog, PyJWT)
    - Create `backend/app/main.py` with FastAPI app skeleton and CORS config
    - Create `backend/app/config.py` for app settings (env-based)
    - _Requirements: all (foundation)_

  - [x] 1.2 Initialize frontend project structure with Vite, React 18, TypeScript, TailwindCSS, shadcn/ui
    - Scaffold with `npm create vite@latest` (React + TypeScript template)
    - Install dependencies: tailwindcss, shadcn/ui, i18next, react-i18next, react-dropzone, fast-check, vitest
    - Configure TailwindCSS and shadcn/ui
    - _Requirements: all (foundation)_

  - [x] 1.3 Define all backend data models and types
    - Create `backend/app/models/` with: `pipeline.py` (PipelineConfig, AgentConfig, ProviderConfig, OAuthConfig, OutputConfig), `files.py` (IngestedFile, FileValidationResult, SUPPORTED_FORMATS), `session.py` (Session), `execution.py` (ExecutionStep, SessionLog), `metrics.py` (SessionMetrics, AgentMetrics), `templates.py` (Template, ValidationRule, RenderedDocument, DocumentMetadata), `encryption.py` (EncryptionConfig), `auth.py` (UserContext, AuthToken, LoginRequest), `faiss_models.py` (IndexConfig, SimilarityResult)
    - _Requirements: 1.2, 3.3, 4.1, 5.1, 7.1, 9.1, 11.1, 12.1, 18.1, 19.1, 20.1_

  - [x] 1.4 Define all frontend TypeScript types and interfaces
    - Create `frontend/src/types/` with: `api.ts` (FileUploadResponse, PipelineExecuteRequest/Response, OutputPreview), `websocket.ts` (ExecutionEvent, ChatResponse, AgentStatusData, LLMStreamToken, PipelineCompleteData), `models.ts` (PipelineConfig, AgentConfig, Template, Session, SessionMetrics)
    - _Requirements: 1.1, 2.3, 3.1, 8.1, 11.3, 13.1_

- [x] 2. Authentication and access control
  - [x] 2.1 Implement AuthService with JWT token issuance and validation
    - Create `backend/app/services/auth_service.py` with `AuthService` class
    - Implement `authenticate()` (credential validation, JWT generation), `validate_token()` (JWT decode, expiry check), `has_role()` (role checking)
    - _Requirements: 20.1_

  - [x] 2.2 Implement FastAPI auth middleware and route protection
    - Create `backend/app/middleware/auth.py` with dependency injection for auth
    - Protect all endpoints: file upload, pipeline execution, config CRUD, output, metrics, replay
    - Reject unauthenticated requests with 401, unauthorized with 403
    - Create `POST /api/auth/login` and `GET /api/auth/me` endpoints
    - _Requirements: 20.1, 20.2, 20.3, 20.4_

  - [x] 2.3 Write property tests for auth and RBAC
    - **Property 28: Unauthenticated request rejection** — For any unauthenticated request to a protected endpoint, the system should reject with 401
    - **Validates: Requirements 20.1, 20.2, 20.3**
    - **Property 29: Role-based access control enforcement** — For any non-admin user, attempts to modify PipelineConfig/LLM settings/templates should be denied; admin users should be allowed
    - **Validates: Requirements 20.4**

- [x] 3. Encryption service
  - [x] 3.1 Implement EncryptionService with configurable per-target encryption
    - Create `backend/app/services/encryption_service.py` with `EncryptionService` class
    - Implement `encrypt()`, `decrypt()`, `get_config()` supporting Fernet and AES-256-GCM
    - Support independent configuration for input, output, and log targets with different keys/algorithms
    - _Requirements: 12.1, 12.2_

  - [x] 3.2 Write property test for encryption round trip
    - **Property 23: Encryption round trip per target** — For any data and encryption config, encrypt then decrypt returns original data; each target uses independent key/algorithm
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

- [x] 4. File ingestion service
  - [x] 4.1 Implement FileIngestionService with format validation and decryption
    - Create `backend/app/services/file_ingestion.py` with `FileIngestionService` class
    - Implement `upload()`, `validate_format()` (check against SUPPORTED_FORMATS set), `decrypt_if_needed()` (delegate to EncryptionService)
    - Create `POST /api/files/upload` endpoint (multipart, auth-protected)
    - Return descriptive errors for unsupported formats and upload failures
    - _Requirements: 1.2, 1.4, 1.5, 12.3_

  - [x] 4.2 Write property test for file format validation
    - **Property 1: File format acceptance matches supported set** — For any file, accept iff format is in {PPTX, DOCX, PDF, TXT, HTML, MD}; reject others with error identifying the unsupported format
    - **Validates: Requirements 1.2, 1.4**

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Pipeline configuration parsing and validation
  - [x] 6.1 Implement PipelineConfig parser and serializer
    - Create `backend/app/services/config_parser.py`
    - Implement `parse_config(raw, format)` for YAML and JSON → PipelineConfig
    - Implement `serialize_config(config, format)` for PipelineConfig → YAML/JSON
    - Return descriptive parse errors with location and nature of failure for invalid configs
    - _Requirements: 19.1, 19.2, 19.3, 19.5_

  - [x] 6.2 Implement PipelineConfig validation
    - Create `backend/app/services/config_validator.py`
    - Validate agent configs, provider configs, tool names, FAISS index bindings, template references
    - Return specific validation errors identifying invalid fields
    - _Requirements: 14.3, 14.4_

  - [x] 6.3 Write property tests for config parsing and validation
    - **Property 26: Pipeline config serialization round trip** — For any valid PipelineConfig, serialize then parse produces equivalent object; parse(serialize(parse(raw))) == parse(raw)
    - **Validates: Requirements 19.1, 19.2, 19.3, 19.4**
    - **Property 27: Invalid config parsing error specificity** — For any invalid config, parser returns error identifying location and nature of failure
    - **Validates: Requirements 19.5**
    - **Property 24: Pipeline config validation reports specific errors** — For any config with invalid settings, report specific validation errors before execution
    - **Validates: Requirements 14.3, 14.4**

- [x] 7. LLM model providers (ModelFactory)
  - [x] 7.1 Implement ModelFactory with Bedrock, OpenAI-compatible, and GitHub Copilot providers
    - Create `backend/app/engine/model_factory.py` with `ModelFactory` class
    - Implement `create_model()` using match on `provider_type`: return `BedrockModel`, `OpenAIModel`, or `GitHubCopilotModel`
    - Implement `check_provider_health()` for connectivity verification
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x] 7.2 Implement GitHubCopilotModel extending strands.models.Model
    - Create `backend/app/engine/github_copilot_model.py` with `GitHubCopilotModel` class
    - Implement `stream()`, `update_config()`, `get_config()` with OAuth authentication
    - _Requirements: 4.4_

  - [x] 7.3 Write property test for LLM routing and unit tests for providers
    - **Property 7: LLM routing matches agent configuration** — For any agent configured with provider P and model M, routing should target provider P with model M
    - **Validates: Requirements 4.1**
    - **Property 8: Unreachable LLM provider error identification** — For any unreachable provider, error identifies provider name and failure reason
    - **Validates: Requirements 4.5**
    - Unit tests for Bedrock, OpenAI-compatible, and GitHub Copilot provider creation
    - _Requirements: 4.2, 4.3, 4.4_

- [x] 8. Agent tools (@tool functions)
  - [x] 8.1 Implement @tool decorated functions
    - Create `backend/app/engine/tools.py` with `read_file`, `write_file`, `python_repl`, `shell`, `query_faiss` as `@tool` decorated functions
    - `python_repl`: cross-platform via subprocess (Windows + Linux)
    - `shell`: Bash on Linux, PowerShell on Windows (platform detection)
    - `query_faiss`: access FAISS manager via `tool_context.invocation_state`
    - Create `ALL_TOOLS` registry dict
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 8.2 Write property tests for tools
    - **Property 11: File read/write round trip** — For any content and path, write then read returns original content
    - **Validates: Requirements 6.1, 6.2**
    - **Property 12: Python REPL correctness** — For any valid Python expression, REPL returns correct result
    - **Validates: Requirements 6.3**
    - **Property 13: Tool permission enforcement** — For any agent with permitted tools P and tool T not in P, T is denied and logged
    - **Validates: Requirements 6.6**

- [x] 9. FAISS Index Manager
  - [x] 9.1 Implement FAISSIndexManager
    - Create `backend/app/engine/faiss_manager.py` with `FAISSIndexManager` class
    - Implement `load_indexes()` (up to 4 concurrent), `query()` (return fragments ranked by similarity score), `get_loaded_indexes()`
    - Report errors for unavailable indexes
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 9.2 Write property tests for FAISS
    - **Property 9: FAISS index count constraint** — Accept 1-4 indexes, reject >4
    - **Validates: Requirements 5.1**
    - **Property 10: FAISS similarity results are ranked by score** — Results ordered by descending similarity score
    - **Validates: Requirements 5.3**

- [x] 10. AgentFactory and GraphFactory (Pipeline Orchestrator)
  - [x] 10.1 Implement AgentFactory
    - Create `backend/app/engine/agent_factory.py` with `AgentFactory` class
    - Implement `create_agent()`: resolve model via ModelFactory, select permitted @tool functions, add query_faiss if FAISS bindings exist, set system_prompt and name on `strands.Agent`
    - Log denied tool access when config references non-permitted tools
    - _Requirements: 3.1, 4.1, 5.2, 6.5, 6.6_

  - [x] 10.2 Implement GraphFactory with sequential graph building and streaming execution
    - Create `backend/app/engine/graph_factory.py` with `GraphFactory` class
    - Implement `build_graph()`: use `GraphBuilder` to create sequential topology from PipelineConfig, `add_node()` per agent, `add_edge()` for sequential chaining, `set_entry_point()`, `set_execution_timeout()`, `build()`
    - Implement `execute()` and `stream_execute()`: build graph, run with `invocation_state` shared state, forward `stream_async()` events to WebSocket
    - Handle agent failure: halt execution, report agent name, step number, error details
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 17.2_

  - [x] 10.3 Write property tests for pipeline orchestration
    - **Property 4: Pipeline agent output chaining** — For agents [A1..AN], Ai+1's input equals Ai's output
    - **Validates: Requirements 3.1, 3.2**
    - **Property 5: Pipeline failure halts and reports** — If agent at step K fails, halt at K, report agent name/step/error, no agents after K execute
    - **Validates: Requirements 3.4**
    - **Property 6: Pipeline accepts any positive agent count** — For any positive N, pipeline with N agents is accepted
    - **Validates: Requirements 3.5**

- [x] 11. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Execution logging and metrics
  - [x] 12.1 Implement ExecutionLogger with structured JSON logging
    - Create `backend/app/services/execution_logger.py` with `ExecutionLogger` class
    - Implement `log_step()`, `log_session_start()`, `log_session_end()`, `get_session_log()`, `list_sessions()`
    - Record per step: timestamp (with timezone), agent ID, input data, prompts, LLM responses, decisions, output data, user identity, LLM provider/model
    - Store as structured JSON to file system or database (SQLite/PostgreSQL)
    - Encrypt logs at rest if configured (delegate to EncryptionService)
    - Record complete input files and output documents per session
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 12.5, 18.1, 18.2, 18.3, 18.4_

  - [x] 12.2 Write property tests for execution logging
    - **Property 18: Execution log completeness** — Each log entry contains timestamp/tz, agent ID, input, prompts, responses, decisions, output, user identity, LLM provider/model; session associates inputs, steps, outputs
    - **Validates: Requirements 9.1, 18.1, 18.2, 18.3, 18.4**
    - **Property 19: Execution logs are valid JSON** — Every log entry is parseable as valid JSON
    - **Validates: Requirements 9.2**
    - **Property 20: Session logs include input and output documents** — Completed session logs contain complete input files and output documents
    - **Validates: Requirements 9.4**

  - [x] 12.3 Implement MetricsCollector with CSV export
    - Create `backend/app/services/metrics_collector.py` with `MetricsCollector` class
    - Implement `record()`, `record_from_node_result()`, `get_session_metrics()`, `export_csv()`
    - Record input tokens, output tokens, LLM call count per agent per session
    - Create `GET /api/metrics/{session_id}` and `GET /api/metrics/{session_id}/csv` endpoints
    - _Requirements: 11.1, 11.2_

  - [x] 12.4 Write property test for metrics CSV round trip
    - **Property 22: Metrics recording and CSV export round trip** — Record metrics, export CSV, parse CSV yields same values
    - **Validates: Requirements 11.1, 11.2**

- [x] 13. Replay engine
  - [x] 13.1 Implement ReplayEngine
    - Create `backend/app/services/replay_engine.py` with `ReplayEngine` class
    - Implement `load_execution()`, `get_step()`, `get_timeline()`
    - Load from ExecutionLogger storage, present steps sequentially with recorded data
    - Create `GET /api/replay/{session_id}` and `GET /api/replay/{session_id}/step/{step_number}` endpoints
    - _Requirements: 10.1, 10.2_

  - [x] 13.2 Write property test for replay
    - **Property 21: Replay preserves execution data** — Loading replay presents all steps in order with same inputs, prompts, responses, outputs as originally recorded
    - **Validates: Requirements 10.1, 10.2**

- [x] 14. Template registry and output generation
  - [x] 14.1 Implement TemplateRegistry
    - Create `backend/app/services/template_registry.py` with `TemplateRegistry` class
    - Implement `get_template()`, `list_templates()`, `register_template()`
    - Templates define format, structure, validation rules, required metadata, encryption settings
    - _Requirements: 7.1_

  - [x] 14.2 Implement OutputGenerator with Jinja2 rendering, validation, and export
    - Create `backend/app/services/output_generator.py` with `OutputGenerator` class
    - Implement `render()` (Jinja2 template application), `validate()` (check rules, report violations), `export()` (PDF via WeasyPrint, DOCX via python-docx, XML via lxml, Markdown, HTML)
    - Include required metadata (author, date, version, classification) in each document
    - Encrypt output if configured (delegate to EncryptionService)
    - Create `GET /api/output/{session_id}/preview` and `GET /api/output/{session_id}/export` endpoints
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 8.3, 12.4_

  - [x] 14.3 Write property tests for templates and output
    - **Property 14: Template completeness** — Every template contains format, structure, validation rules, metadata; every document has author/date/version/classification
    - **Validates: Requirements 7.1, 7.5**
    - **Property 15: Jinja2 template rendering produces output** — For valid template and data, render produces non-empty document
    - **Validates: Requirements 7.3**
    - **Property 16: Validation failure reports violated rules** — For documents violating rules, report exactly which rules were violated
    - **Validates: Requirements 7.4**
    - **Property 17: Export format matches request** — For any valid session and format (PDF/XML/DOCX), export produces document in requested format
    - **Validates: Requirements 8.3**

- [x] 15. Backend API wiring — pipeline execution and WebSocket endpoints
  - [x] 15.1 Implement pipeline execution REST and WebSocket endpoints
    - Create `backend/app/api/pipeline.py` with `POST /api/pipeline/execute` and `WS /api/ws/execution/{session_id}`
    - Wire GraphFactory.stream_execute() to WebSocket, forwarding stream_async events (agent_start, llm_token, agent_complete, pipeline_complete)
    - Create session management (create, track status, store results)
    - _Requirements: 3.1, 3.2, 13.2, 17.2_

  - [x] 15.2 Implement chat WebSocket endpoint
    - Create `backend/app/api/chat.py` with `WS /api/ws/chat/{session_id}`
    - Wire to a strands.Agent for conversational interaction with streaming responses
    - Maintain conversation context within session
    - _Requirements: 2.1, 2.3, 2.4, 17.1_

  - [x] 15.3 Implement pipeline config CRUD endpoints
    - Create `backend/app/api/config.py` with `GET/POST/PUT/DELETE /api/config/pipelines`
    - Admin-only access (RBAC enforcement)
    - Load, validate, parse, serialize pipeline configs
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 19.1, 19.2, 20.4_

- [x] 16. Checkpoint — Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Frontend — Theme, i18n, and auth
  - [x] 17.1 Implement ThemeProvider with dark/light theme support
    - Create `frontend/src/providers/ThemeProvider.tsx`
    - Detect OS theme preference as default, allow manual switching without losing session state
    - _Requirements: 16.1, 16.2, 16.3_

  - [x] 17.2 Implement I18nProvider with EN/FR support
    - Create `frontend/src/providers/I18nProvider.tsx` and `frontend/src/i18n/` with EN and FR translation files
    - Configure i18next with browser language detection, manual language switching without losing session state
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

  - [x] 17.3 Implement AuthGate with login flow and RBAC route protection
    - Create `frontend/src/components/AuthGate.tsx` and `frontend/src/hooks/useAuth.ts`
    - Login form, JWT token management, role-based route protection (admin vs user)
    - _Requirements: 20.1, 20.4_

- [x] 18. Frontend — Core components
  - [x] 18.1 Implement DropZone component with drag-and-drop file upload
    - Create `frontend/src/components/DropZone.tsx` using react-dropzone
    - Accept PPTX, DOCX, PDF, TXT, HTML, MD files; show preview with detected format; display error for unsupported formats
    - Upload files to `POST /api/files/upload`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 18.2 Implement ChatPanel component with bilingual WebSocket streaming
    - Create `frontend/src/components/ChatPanel.tsx`
    - Connect to `WS /api/ws/chat/{session_id}`, display streamed responses in real time
    - Accept EN/FR input, maintain conversation context display
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 17.1_

  - [x] 18.3 Implement ExecutionTimeline component with real-time monitoring
    - Create `frontend/src/components/ExecutionTimeline.tsx`
    - Connect to `WS /api/ws/execution/{session_id}`, display agent status (pending/running/completed/failed)
    - Stream live log entries, show currently active agent and progress
    - _Requirements: 13.1, 13.2, 13.3_

  - [x] 18.4 Implement OutputViewer component with preview and export
    - Create `frontend/src/components/OutputViewer.tsx`
    - Display document preview against selected template
    - Export buttons for PDF, XML, DOCX formats
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 18.5 Implement ConfigPanel component (admin only)
    - Create `frontend/src/components/ConfigPanel.tsx`
    - CRUD for PipelineConfig: agent sequence, model assignments, tool access, FAISS index bindings, template selection
    - LLM provider configuration
    - _Requirements: 14.1, 14.2_

  - [x] 18.6 Implement MetricsDashboard component
    - Create `frontend/src/components/MetricsDashboard.tsx`
    - Display real-time token/call counts per agent during execution (via WebSocket metrics_update events)
    - _Requirements: 11.3_

  - [x] 18.7 Implement ReplayViewer component with step-by-step navigation
    - Create `frontend/src/components/ReplayViewer.tsx`
    - Display execution timeline with step-by-step navigation controls
    - Load replay data from `GET /api/replay/{session_id}`
    - _Requirements: 10.3_

- [x] 19. Frontend — Property and unit tests
  - [x] 19.1 Write frontend property tests
    - **Property 2: File preview renders for each dropped file** — For any list of valid files, UI renders a preview element per file with detected format
    - **Validates: Requirements 1.3**
    - **Property 3: Chat session context accumulation** — For N messages in a session, context contains all N messages in order
    - **Validates: Requirements 2.4**
    - **Property 25: UI preference changes preserve session state** — Switching language or theme preserves all non-preference session state
    - **Validates: Requirements 15.3, 16.2**

  - [x] 19.2 Write frontend unit tests
    - DropZone renders drop zone (Req 1.1), ChatPanel accepts EN/FR (Req 2.1), language detection (Req 2.2), OutputViewer renders preview (Req 8.1), export buttons (Req 8.2), ExecutionTimeline renders (Req 10.3, 13.1), ConfigPanel renders (Req 14.1, 14.2), EN/FR support (Req 15.1), browser language detection (Req 15.2), dark/light theme (Req 16.1), OS theme detection (Req 16.3)

- [x] 20. Frontend — App shell and page wiring
  - [x] 20.1 Wire all components into the main App layout
    - Create `frontend/src/App.tsx` with routing, layout (sidebar with chat, main area with drop zone/output/timeline)
    - Wrap with ThemeProvider, I18nProvider, AuthGate
    - Connect all components to backend API and WebSocket endpoints
    - _Requirements: all frontend requirements_

- [x] 21. Integration and end-to-end wiring
  - [x] 21.1 Wire full pipeline flow: file upload → pipeline execution → output generation
    - Ensure file upload triggers session creation, pipeline execution streams events to frontend, output is generated and available for preview/export
    - Wire ExecutionLogger and MetricsCollector into GraphFactory execution flow
    - Wire EncryptionService into file ingestion, output generation, and log storage
    - _Requirements: 1.1-1.5, 3.1-3.5, 7.3, 8.1-8.3, 9.1-9.4, 11.1-11.3, 12.3-12.5, 13.1-13.3, 17.1-17.2_

  - [x] 21.2 Write backend integration tests
    - End-to-end pipeline execution with mock LLM providers
    - WebSocket streaming verification (chat + execution events)
    - File upload → pipeline → output flow
    - Auth and authorization flow
    - Encryption across the full pipeline
    - _Requirements: 3.1, 3.2, 17.1, 17.2, 20.1, 20.2, 20.3, 12.1-12.5_

- [x] 22. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate the 29 correctness properties from the design document
- Backend uses Python with pytest + Hypothesis; frontend uses TypeScript with Vitest + fast-check
- Checkpoints at tasks 5, 11, 16, and 22 ensure incremental validation
- All Strands SDK integration (Agent, GraphBuilder, ModelFactory, @tool, stream_async) is concentrated in tasks 7-10
