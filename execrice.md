# HAAL-DEX Training Exercises

This repository is used as a base for hands-on exercises to learn how to understand, extend, and improve an agentic full-stack application.

## Repository

- **Repo URL**: https://github.com/haal-ai/haal-dex
- **Access**: You need to **apply/request access** before you can clone or open pull requests.

## Contribution process (mandatory)

- **Fork the repo** (under your own GitHub account/org).
- **Create a feature branch** per exercise.
- **Do your work** (code + tests + docs updates if needed).
- **Open a pull request only if it is “awesome”**:
  - The change is cleanly designed and clearly useful.
  - It includes tests (unit/integration/e2e as appropriate).
  - It includes a short, high-signal PR description.
  - It improves maintainability (not just “it works on my machine”).
  - It is safe and secure (no secrets, no broad permissions).

## How the app works (1-paragraph mental model)

Users upload documents in the React UI, then interact through chat and/or run a configured pipeline. The FastAPI backend orchestrates a sequential chain of AI agents using the AWS Strands Python SDK, binding tools and FAISS indexes per agent. The backend streams progress and responses over WebSockets and produces structured logs/metrics for traceability and replay.

## Complexity scale (for ordering)

- **L1**: Small, mostly read-only understanding tasks or isolated UI tweaks
- **L2**: Localized changes with clear boundaries and tests
- **L3**: Cross-module changes (backend + frontend) with API contract updates
- **L4**: Multi-component refactors (orchestration + tooling + security implications)
- **L5**: Platform-level features (new subsystems, long-lived data, async/background processing)

---

# Theme 1 — AWS Strands: understanding implementation and improving it

Goal: learn where agent/tool/model decisions are made, how orchestration is constructed, and how to safely narrow capabilities.

## Exercises

- **[L1] Map tool injection**
  - Identify where tools are constructed and injected into agents.
  - Produce a short write-up in the PR description: “which tools exist, who gets them, and why”.
  - Acceptance criteria: you can point to the exact factory/module responsible and explain the data flow.

- **[L2] Understand agent orchestration generation**
  - Find where the pipeline graph/sequence is generated (graph/pipeline factory).
  - Explain how agent configs map to runtime Strands agents.
  - Acceptance criteria: you can trace a single pipeline run end-to-end (config → agent instances → execution events → logs).

- **[L3] Restrict tool scope to a folder**
  - Modify file tools so they can only read/write within a configured root folder (e.g. upload/session folder).
  - Consider symlinks, path traversal, and Windows path edge cases.
  - Acceptance criteria: tests proving `..` traversal is blocked and only allowed paths work.

- **[L2] Create a new tool and expose it to agents**
  - Add a simple but useful tool (examples: “list session files”, “read execution log step”, “render template preview”).
  - Wire it into the tool registry/factory so specific agents can use it.
  - Acceptance criteria: tool is callable in an agent run and has tests.

- **[L4] Enable GitHub Copilot via OAuth**
  - Add the OAuth flow + token handling needed for Copilot model access.
  - Ensure secrets are not logged and tokens are stored safely.
  - Acceptance criteria: local dev instructions + a working happy-path integration test or a mocked provider test.

- **[L3] Fix metrics so the view is clean**
  - Identify the current “metrics issue” (double counting, inconsistent schema, missing fields, UI mismatch, etc.).
  - Fix the root cause and update any API/UI contract.
  - Acceptance criteria: metrics endpoint and UI display are consistent and stable across runs.

- **[L3] Add provider + model selection in chat**
  - Extend chat configuration to pick provider and model per session (or per message, if you want a stretch).
  - Acceptance criteria: UI can select provider/model and backend uses it deterministically.

---

# Theme 2 — Kiro SDD: add new features based on what the system already does

Goal: practice structured, specification-driven development for changes that touch both backend and frontend.

## Exercises

- **[L2] Personality in chat**
  - Add a “personality” selector that changes system prompt / style.
  - Keep it explicit and auditable (stored in session config).
  - Acceptance criteria: personality is visible in replay/logs and affects responses.

- **[L4] Sub-agent inside chat (pre-coded agent)**
  - Add the ability for chat to invoke a named sub-agent (e.g. “Reviewer”, “Extractor”, “Debugger”).
  - Decide whether it’s a tool call, a routing decision, or a multi-agent orchestration.
  - Acceptance criteria: chat can delegate a subtask to sub-agent and stream results back.

- **[L4] Share agents between pipelines and chat**
  - If an agent is defined in a pipeline config, make it usable as a sub-agent in chat.
  - Acceptance criteria: one source of truth for agent definitions; both pipeline and chat can reference it.

- **[L3] Redesign the system prompt + clean ephemeral context**
  - Make system prompts consistent, composable, and minimal.
  - Ensure ephemeral runtime data does not “leak” into persistent context (logs, saved configs, etc.).
  - Acceptance criteria: deterministic prompt construction and clear separation of persistent vs ephemeral data.

- **[L3] Add tools to chat**
  - Allow enabling/disabling tool access for chat (per role, per session, or per environment).
  - Acceptance criteria: chat can call tools safely; permissions are enforced.

- **[L4] Add MCP servers to chat**
  - Add a way to register/enable MCP servers for chat sessions.
  - Acceptance criteria: configured MCP servers appear as available tools/capabilities and can be used.

---

# Theme 3 — Vibe UX: improve the experience and create “skills” to update the UI

Goal: practice product-minded UX changes, then package them into repeatable “skills” or guided flows.

## Exercises

- **[L2] Two layout modes**
  - Add a user-facing toggle between two layouts (examples: “Focus mode” vs “Workspace mode”).
  - Persist the preference.
  - Acceptance criteria: both layouts are polished and accessible; switching is instant and stable.

- **[L3] Layout-change skill**
  - Provide a “skill” that guides a user through changing layout (or generates a layout preset).
  - Decide where skills live (frontend-only, backend-assisted, or agent-driven).
  - Acceptance criteria: the skill is discoverable, usable, and doesn’t require manual code edits.

- **[L3] Stretch UX improvements (pick 1)**
  - Better execution timeline visualization (steps, durations, errors).
  - Improved file upload feedback (validation, progress, failure recovery).
  - Replay UI improvements (diffs between steps, search, annotations).

---

# Theme 4 — Production readiness & platform quality (integration, security, reliability)

Goal: turn experimental agentic features into maintainable, secure, testable platform capabilities.

## Exercises

- **[L3] Role-based capability control**
  - Enforce tool/model/provider permissions by user role (admin vs user).
  - Acceptance criteria: backend rejects forbidden configurations; UI hides or disables them.

- **[L4] Configuration validation & migration**
  - Add strict schema validation for pipeline configs (and a migration path when schema evolves).
  - Acceptance criteria: invalid configs produce actionable errors; tests cover migration.

- **[L3] Observability improvements**
  - Add structured logging improvements (correlation IDs, event types, durations).
  - Acceptance criteria: you can debug a session from logs without reading code.

- **[L4] Security hardening pass**
  - Review and tighten any file handling, shell usage, and secret handling.
  - Acceptance criteria: no path traversal; no secrets in logs; safe defaults.

- **[L5] Background queue for batch file processing**
  - Allow users to queue a set of files and apply pipelines in the background.
  - Define job lifecycle (queued/running/succeeded/failed), progress reporting, and retry rules.
  - Acceptance criteria: queued runs survive page refresh and can be monitored end-to-end.

- **[L5] Deliver a solution for a specific need (solution template)**
  - Add a guided “solution” flow (wizard) to configure pipeline + indexes + output template for a targeted use case.
  - Acceptance criteria: a user can select a need and get a working, reproducible configuration.

- **[L4] Generate new personalities**
  - Add a workflow to create, validate, and store new personalities (prompt + constraints + examples).
  - Acceptance criteria: personalities are versioned, selectable, and auditable in replay.

- **[L4] Fix replay (end-to-end)**
  - Identify replay gaps (missing events, mismatched step numbering, broken UI rendering, incomplete logs).
  - Acceptance criteria: a saved session can be replayed consistently and matches the original run.

---

# Theme 5 — Retrieval & indexing (FAISS and ranking)

Goal: provide strong tooling around the four FAISS indexes so users can build, name, evaluate, and reuse indexes reliably.

## Exercises

- **[L2] Index naming and discovery**
  - Allow naming indexes so users can assess what they address (domain/purpose, source set, date).
  - Acceptance criteria: UI shows names/metadata; backend stores metadata; replays reference the name.

- **[L3] Indexing tools for building the 4 FAISS indexes**
  - Provide tooling to ingest documents, chunk, embed, and write into each of the four indexes.
  - Acceptance criteria: reproducible indexing runs with logs/metrics (docs processed, chunks, errors).

- **[L4] Remote index support**
  - Enable using a remote index (or remote index storage) in addition to local disk.
  - Acceptance criteria: a pipeline can bind to local or remote indexes without code changes.

- **[L3] BM25 / TF-IDF retrieval option**
  - Add a lexical retrieval option (BM25 or TF-IDF) alongside vector search.
  - Acceptance criteria: configuration can pick retrieval mode; evaluation shows when lexical helps.

- **[L3] Local embedding**
  - Use a local embedding model for indexing and querying.
  - Acceptance criteria: local embeddings can be selected and produce consistent dimensions for FAISS.

- **[L4] Remote embedding**
  - Use a remote embedding provider (e.g. OpenAI-compatible / Bedrock embeddings) for indexing and querying.
  - Acceptance criteria: credentials handled securely; batching/rate limits handled; tests via mocking.

- **[L4] Re-ranking**
  - Add an optional rerank stage after initial retrieval.
  - Acceptance criteria: reranking is configurable and measurably improves relevance on a small benchmark.

- **[L4] MMR (Maximal Marginal Relevance)**
  - Add MMR to diversify retrieved chunks and reduce redundancy.
  - Acceptance criteria: configuration exposes MMR knobs; results show reduced duplication without quality loss.

---

# Extra exercise ideas (optional backlog)

Pick any of these when you want additional challenges:

- **Provider “capabilities” matrix**: compute what each provider supports (streaming, tools, vision, context length) and show it in UI.
- **Golden replay tests**: make a small deterministic pipeline and assert replay output/event sequence.
- **Template preview sandboxing**: render Jinja2 previews safely, with strict limits.
- **Better error taxonomy**: standardize backend errors (validation vs provider vs tool vs orchestration) and display them cleanly in UI.

## Definition of done (for any PR you submit)

- Code compiles and the app runs locally.
- Tests are added/updated and pass.
- The change is secure by default.
- The PR description explains “what, why, and how to review”.
