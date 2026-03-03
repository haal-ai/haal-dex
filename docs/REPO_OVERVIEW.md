# OLAF Agentic Framework — Repository Overview

> Generated: 2026-03-02

## What Is This Repo?

This is the **OLAF Agentic Framework**, a comprehensive AI-powered automation platform built on the **AWS Strands SDK**. It provides both CLI-based specialized tools and a general-purpose agent for automating complex software engineering workflows through multi-agent orchestration.

## Three Core Components

### 1. STRAF-CLI (Specialized CLI Commands)

A set of long-running agentic commands for specific dev tasks:

- `documentor` — Generate external MkDocs documentation from codebases
- `inlinedoc` — Generate inline docs (JSDoc, Javadoc, docstrings, Doxygen, godoc, Rust docs)
- `document-api` — API documentation generation with test/spec generation
- `refactor-hotspots` — Identify code hotspots via git history and apply refactorings
- `researcher` — Agent-driven research with quick/deep modes and web fetching
- `review-repos` — Multi-aspect repo review (bus factor, maintenance index, code quality, etc.)
- `solution-doc` — Solution-level documentation across multiple repos
- `test-augmentor` — Augment unit tests using adversarial multi-agent pipeline

### 2. STRAF Agent (General-Purpose)

A generic agent that can be called from IDEs or CLI tools as a background solution. Supports:

- Multiple LLM providers (AWS Bedrock, OpenAI-compatible, GitHub Copilot)
- Configurable tool modes (minimal, standard, full)
- Extensible skill system
- Full execution tracing and replay

### 3. IDE Skills (.windsurf / .agents)

Skills that bridge the gap between IDE interactions and the STRAF engine:

- `straf-cli-launcher` — Execute STRAF-CLI commands with parameter collection
- `generate-code-mapper-docs` — Technical project documentation from code analysis
- `create-documentor-profile` — Create documentation profiles

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.8+ |
| Agent Framework | AWS Strands SDK |
| Primary LLM | AWS Bedrock (Claude, Mistral, Llama, Nova) |
| Alt LLM Providers | OpenAI-compatible endpoints, GitHub Copilot |
| Config | JSON/YAML |
| Logging | Structured JSON, execution tracking with CSV metrics |

## Vision (INTENT)

The project has a forward-looking vision called **INTENT**: a React + FastAPI web application where users drop input files, process them through configurable agentic pipelines with up to 4 FAISS vector indexes for domain knowledge retrieval, and produce structured output documents with full traceability, replayability, and audit. This is the next evolution of the framework toward a document transformation platform.

## Project Status

- ✅ CLI command structure and core agent framework operational
- ✅ Skill system foundation in place
- 🔄 Command implementations, IDE integration, and documentation in progress

## License

Apache 2.0
