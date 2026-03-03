# INTENT — Product Vision

> **Version:** 1.0  
> **Date:** 03/02/2026

---

## 1. Executive Summary

INTENT is a modern web application (React) that allows users to submit one or more input files, process them through a configurable AI agentic pipeline built on AWS Strands (Python SDK), and produce structured output documents based on predefined templates. The system leverages up to 4 FAISS vector indexes to enrich agent reasoning from specialized document collections, and delivers fully traceable, replayable, auditable results.

---

## 2. Problem Statement

Transforming unstructured or semi-structured input documents into compliant, structured output documents is a recurring challenge across industries. It typically involves:

- Multiple heterogeneous source documents (standards, guidelines, catalogs, past examples)
- Manual, error-prone assembly processes with scattered feedback loops
- Strict compliance and traceability requirements
- No adequate AI tooling that combines document understanding, domain knowledge retrieval, and structured generation

INTENT centralizes and automates this process through a configurable agentic pipeline.

---

## 3. Functional Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        REACT UI (Modern, Drag & Drop)              │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │  File Input   │  │  Chat (NL)   │  │  Output Viewer            │ │
│  │  (1..N files) │  │  (EN / FR)   │  │  (Templates, PDF, XML)   │ │
│  │  Drag & Drop  │  │              │  │                           │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────▲───────────────┘ │
│         │                 │                       │                  │
└─────────┼─────────────────┼───────────────────────┼──────────────────┘
          │                 │                       │
          ▼                 ▼                       │
┌─────────────────────────────────────────────────────────────────────┐
│                     API GATEWAY (REST / WebSocket)                   │
└─────────┬─────────────────────────────────────────┬─────────────────┘
          │                                         │
          ▼                                         │
┌─────────────────────────────────────────────────────────────────────┐
│              AGENTIC ENGINE (AWS Strands Python SDK)                 │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Agent Orchestrator                                          │   │
│  │  (Sequential pipeline OR Strands Graph, config-driven)       │   │
│  │                                                               │   │
│  │  Agent 1 ──► Agent 2 ──► Agent 3 ──► ... ──► Agent N        │   │
│  │  (model A)   (model B)   (model C)           (model X)      │   │
│  └──────┬──────────────────────────────────────────┬────────────┘   │
│         │                                          │                 │
│         ▼                                          ▼                 │
│  ┌──────────────────┐                  ┌────────────────────────┐   │
│  │  FAISS Indexes    │                  │  Agent Tools           │   │
│  │  (up to 4)        │                  │                        │   │
│  │                   │                  │  • File Read           │   │
│  │  Index 1: Standards│                 │  • File Write          │   │
│  │  Index 2: Rules    │                 │  • Python REPL         │   │
│  │  Index 3: Catalogs │                 │    (Win + Linux)       │   │
│  │  Index 4: Examples │                 │  • Shell               │   │
│  │                   │                  │    (Bash + PowerShell) │   │
│  └──────────────────┘                  └────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Execution Logger (full trace, replay, audit)                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  LLM Provider Router (configurable per agent)                │   │
│  │                                                               │   │
│  │  ┌─────────┐  ┌──────────────┐  ┌────────────────────────┐  │   │
│  │  │ Bedrock  │  │ OpenAI-compat│  │ GitHub Copilot (OAuth) │  │   │
│  │  │ Services │  │ (any vendor) │  │                        │  │   │
│  │  └─────────┘  └──────────────┘  └────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│              OUTPUT GENERATION                                       │
│                                                                     │
│  Template Registry ──► Rendered Output (XML, PDF, DOCX, MD, ...)   │
│  (configurable list)                                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Key Components

### 4.1 React Frontend

| Feature | Description |
|---------|-------------|
| Drag & Drop file input | User drops 1 to N input files. Supported formats: **PPTX, DOCX, PDF, TXT, HTML, Markdown**. Files may be encrypted — the system supports configurable decryption on ingestion. Visual drop zone with file preview and format detection. |
| Natural language chat | Bilingual conversational interface (EN / FR) to formulate requests, ask questions, steer the pipeline. |
| Output viewer | Preview generated documents against templates. Export to PDF, XML, DOCX. |
| Execution monitor | Real-time timeline of the agentic pipeline. Live logs and agent status. |
| Configuration panel | Admin UI to configure LLM providers, agents, templates, FAISS indexes. |
| Modern design | Responsive, dark/light theme, component library (shadcn/ui or equivalent), native drag & drop. |

### 4.2 Agentic Engine (Backend — AWS Strands Python SDK)

| Component | Description |
|-----------|-------------|
| Sequential agent pipeline | Chain of agents defined by a configuration file (YAML/JSON) or a Strands Graph. Each agent has a specific role in building the output document. |
| Per-agent model configuration | Each agent can use a different LLM (e.g., Agent 1 on Bedrock Claude, Agent 2 on GPT-4, Agent 3 on Mistral via OpenAI-compatible endpoint). |
| FAISS indexes (up to 4) | Each index vectorizes a specific type of reference document. Agents query these indexes to retrieve contextual checks (rules, constraints, examples) that guide and validate output construction. |
| Agent tools | `read` (file reading), `write` (file writing), `python_repl` (Python execution, Windows + Linux compatible), `shell` (Bash + PowerShell). |

### 4.3 LLM Providers (configurable)

| Provider | Access |
|----------|--------|
| AWS Bedrock | Native SDK. Access to Claude, Mistral, Llama, Titan, etc. |
| OpenAI-compatible | Configurable endpoint. Supports OpenAI, Azure OpenAI, Mistral API, vLLM, Ollama, any compatible server. |
| GitHub Copilot | OAuth authentication. Use Copilot models as an LLM provider. |

### 4.4 Output Templates

Templates are defined in a configurable registry. Each template specifies:

- Output format (XML, PDF, DOCX, Markdown, HTML)
- Expected document structure (sections, fields, hierarchy)
- Validation rules (required fields, format constraints, cross-references)
- Required metadata (author, date, version, classification)
- Optional output encryption (method configurable independently from input decryption)

### 4.5 Logging, Replay & Audit

| Feature | Description |
|---------|-------------|
| Full trace | Every execution is logged: inputs, prompts sent, LLM responses, agent decisions, intermediate and final outputs. |
| Log encryption | Execution logs can be encrypted at rest. Encryption method is configurable independently from input/output encryption. |
| Token & call metrics | For each agent and each session, the system collects: total input tokens, total output tokens, number of LLM calls. Metrics are exported to a **CSV file** per session for cost tracking and analysis. |
| Replay | Any past execution can be replayed step-by-step for analysis or debugging. |
| Audit | Logs are structured to support compliance auditing (who produced what, when, with which data and model). |

---

## 5. FAISS Indexes — Vectorization Strategy

Each FAISS index represents a homogeneous document corpus. The system supports up to 4 indexes per execution.

| Index | Typical Content | Role for Agents |
|-------|----------------|-----------------|
| Index 1 | Standards & norms | Provide structural rules and format constraints. |
| Index 2 | Domain guidelines & policies | Provide operational rules and principles. |
| Index 3 | Catalogs & reference data | Provide factual data (entities, resources, parameters). |
| Index 4 | Past examples & lessons learned | Provide concrete examples and writing patterns. |

Agents query these indexes via similarity search to extract a set of "checks" — verification points, rules, and examples — that structure and validate the output document construction.

---

## 6. Pipeline Configuration

The pipeline is defined by a config file (YAML or JSON) or a Strands Graph:

```yaml
pipeline:
  name: "Structured Document Generation"
  agents:
    - name: "context_analyzer"
      model: "bedrock/claude-3-sonnet"
      faiss_indexes: [1, 2]
      tools: ["read"]
      description: "Analyzes input files and extracts key context"

    - name: "structure_builder"
      model: "openai/gpt-4"
      faiss_indexes: [1, 3]
      tools: ["read", "python_repl"]
      description: "Builds the document structure according to standards"

    - name: "content_generator"
      model: "bedrock/claude-3-opus"
      faiss_indexes: [2, 3, 4]
      tools: ["read", "write"]
      description: "Writes the content for each section"

    - name: "validator"
      model: "openai/gpt-4"
      faiss_indexes: [1, 2]
      tools: ["read", "python_repl"]
      description: "Validates compliance with standards and guidelines"

    - name: "formatter"
      model: "bedrock/claude-3-haiku"
      tools: ["read", "write", "python_repl"]
      template: "structured_doc_v1"
      description: "Produces the final document from the selected template"

  output:
    template: "structured_doc_v1"
    formats: ["xml", "pdf"]
```

---

## 7. Primary User Flow

```
1. User opens INTENT (React UI)
2. Drops one or more input files (PPTX, DOCX, PDF, TXT, HTML, MD)
   OR types a natural language request via the chat (EN or FR)
3. System identifies the agentic pipeline to execute
   (from config or manual selection)
4. Pipeline executes:
   a. Each agent processes its task sequentially
   b. Agents query relevant FAISS indexes for contextual checks
   c. Agents use their tools (read, write, repl, shell) as needed
   d. Every step is logged
5. Output document is generated from the selected template
6. User previews, validates, and exports (XML, PDF, DOCX)
7. Execution is archived for replay and audit
```

---

## 8. Non-Functional Requirements

| Requirement | Detail |
|-------------|--------|
| Bilingual | UI and chat support English and French. Auto-detection or manual selection. |
| Cross-platform tools | Python REPL and Shell tools work on both Windows (PowerShell) and Linux (Bash). |
| Full traceability | Every action, LLM call, and agent decision is logged with timestamp, agent ID, input/output. |
| Replayability | Any execution can be replayed identically for analysis or debugging. |
| Configurability | LLM providers, models per agent, FAISS indexes, templates, pipeline — all configurable without code changes. |
| Security | Authentication, access control, sensitive data handling. |
| Encryption | Input files, output documents, and logs each support independent, configurable encryption/decryption methods. Decryption on ingestion and encryption on output can use different keys and algorithms. |
| Usage metrics | Input tokens, output tokens, and LLM call count collected per agent per session, exported as CSV. |
| Real-time feedback | LLM response streaming to the UI. Live progress on pipeline execution. |

---

## 9. Target Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18+, TypeScript, Vite, TailwindCSS, shadcn/ui, react-dropzone, i18next (EN/FR) |
| Backend API | Python (FastAPI), WebSocket for streaming |
| Agentic Engine | AWS Strands Python SDK, Strands Graph |
| Vector Store | FAISS (Facebook AI Similarity Search) |
| LLM Providers | AWS Bedrock SDK, OpenAI SDK (compatible), GitHub Copilot OAuth |
| Logging | Structured JSON logs, file or database storage (SQLite / PostgreSQL) |
| Templates | Jinja2 or equivalent for document rendering |
| Infrastructure | Containerized (Docker), cloud or on-premise |

---

## 10. What Makes This Generic

This architecture is domain-agnostic by design:

- **Any input documents** → processed by configurable agents
- **Any reference corpus** → vectorized into up to 4 FAISS indexes
- **Any output format** → driven by a template registry
- **Any LLM provider** → swappable per agent via config
- **Any language** → bilingual UI, extensible to more locales
- **Any compliance need** → full execution logging with replay and audit

The same platform can serve document generation in legal, healthcare, engineering, finance, or any domain where structured documents must be produced from heterogeneous sources with domain-specific validation.

---

## 11. Next Steps

1. Validate this vision with the team
2. Scaffold the React + FastAPI project
3. Implement the first Strands agentic pipeline (2 agents, 1 FAISS index)
4. Connect a first LLM provider (Bedrock)
5. Produce a first test output from sample input files
