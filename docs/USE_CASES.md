# INTENT — Use Cases

## UC-1: Document Generation Pipeline

**Actor:** User

**Goal:** Transform one or more input documents into a structured output document using a configured AI agent pipeline.

**Flow:**
1. User opens INTENT and authenticates
2. User drags and drops input files (PPTX, DOCX, PDF, TXT, HTML, or MD) onto the DropZone
3. System validates file formats and displays previews
4. User selects or confirms the pipeline configuration to use
5. User triggers pipeline execution
6. System executes agents sequentially — each agent processes its step, queries FAISS indexes for domain context, and uses permitted tools
7. ExecutionTimeline shows real-time progress: which agent is active, live log entries, streaming LLM responses
8. MetricsDashboard displays token counts per agent in real-time
9. On completion, OutputViewer shows the rendered document preview
10. User exports the document in PDF, DOCX, PPTX, Markdown, or HTML format

**Alternate flows:**
- If a file has an unsupported format, the DropZone shows an inline error
- If an agent fails, the pipeline halts and the timeline shows the failed step with error details
- If the LLM provider is unreachable, the error identifies the provider and failure reason

---

## UC-2: Conversational Interaction

**Actor:** User

**Goal:** Steer the pipeline or ask questions through natural language chat in English or French.

**Flow:**
1. User types a message in the ChatPanel (EN or FR)
2. System detects the language or uses the manually selected language
3. Message is sent over WebSocket to the backend
4. LLM response streams back in real-time, token by token
5. ChatPanel displays the response as it arrives
6. Conversation context is maintained within the session — follow-up messages reference prior context

**Notes:**
- The chat interface supports both English and French with automatic language detection
- Language can be switched manually at any time without losing session state

---

## UC-3: Execution Replay and Debugging

**Actor:** Developer / Auditor

**Goal:** Replay a past pipeline execution step by step to analyze agent behavior or debug issues.

**Flow:**
1. User navigates to the Replay tab
2. User selects a past session to replay
3. ReplayViewer loads the execution from stored logs
4. Each pipeline step is presented sequentially with:
   - Input data received by the agent
   - Prompts sent to the LLM
   - LLM responses
   - Agent decisions
   - Output data produced
5. User navigates forward/backward through steps using timeline controls

**Value:** Full traceability of every decision made by every agent, enabling root cause analysis and quality assurance.

---

## UC-4: Pipeline Configuration (Admin)

**Actor:** Administrator

**Goal:** Create or modify pipeline configurations without editing code.

**Flow:**
1. Admin navigates to the Config tab (visible only to admin role)
2. ConfigPanel displays existing pipeline configurations
3. Admin creates a new config or edits an existing one:
   - Defines the agent sequence (name, order)
   - Assigns LLM provider and model per agent (Bedrock, OpenAI-compatible, or GitHub Copilot)
   - Specifies which tools each agent can use (read, write, python_repl, shell)
   - Binds FAISS indexes to agents (up to 4 indexes)
   - Selects the output template and export formats
4. System validates the configuration before saving
5. If validation fails, specific errors are shown (invalid fields, missing required values)

**Example pipeline config (YAML):**
```yaml
pipeline:
  name: "Structured Document Generation"
  agents:
    - name: "context_analyzer"
      model: "bedrock/claude-3-sonnet"
      faiss_indexes: [1, 2]
      tools: ["read"]
    - name: "content_generator"
      model: "openai/gpt-4"
      faiss_indexes: [2, 3, 4]
      tools: ["read", "write"]
    - name: "formatter"
      model: "bedrock/claude-3-haiku"
      tools: ["read", "write", "python_repl"]
      template: "structured_doc_v1"
  output:
    template: "structured_doc_v1"
    formats: ["md", "pdf", "docx"]
```

---

## UC-5: Audit and Compliance Review

**Actor:** Compliance Officer / Auditor

**Goal:** Determine who produced what output, when, with which input data, and which LLM model — for regulatory or internal compliance.

**Flow:**
1. Auditor accesses execution logs (via API or direct log storage)
2. Each session log contains:
   - Authenticated user identity
   - Timestamps with timezone for every event
   - Complete input files submitted
   - Per-agent processing steps: prompts sent, LLM responses, decisions made
   - LLM provider and model identifier used by each agent
   - Final output documents generated
3. Logs are structured JSON, associating inputs → processing steps → outputs within a single session record
4. If log encryption is enabled, logs are encrypted at rest with a configurable key

**Value:** Complete audit trail from input to output, satisfying traceability requirements for regulated industries.

---

## UC-6: Cost Monitoring and Optimization

**Actor:** Administrator

**Goal:** Track token usage and LLM call counts to monitor costs and optimize model assignments.

**Flow:**
1. During pipeline execution, MetricsDashboard shows real-time token counts per agent
2. After execution, admin views session metrics:
   - Input tokens per agent
   - Output tokens per agent
   - Number of LLM calls per agent
3. Admin exports metrics as CSV for cost analysis
4. Based on metrics, admin adjusts pipeline config — e.g., switching expensive agents to cheaper models, or reducing tool access to limit unnecessary LLM calls

---

## UC-7: Encrypted Document Processing

**Actor:** Security Officer / User

**Goal:** Process sensitive documents with encryption at every stage — input decryption, output encryption, and log encryption.

**Flow:**
1. Security officer configures encryption settings:
   - Input encryption: algorithm and key for decrypting uploaded files
   - Output encryption: algorithm and key for encrypting generated documents
   - Log encryption: algorithm and key for encrypting execution logs at rest
   - Each target uses independent keys and algorithms
2. User uploads encrypted input files
3. FileIngestionService decrypts files using the configured input key before processing
4. Pipeline executes normally on decrypted content
5. OutputGenerator encrypts the rendered document using the configured output key
6. ExecutionLogger encrypts log entries at rest using the configured log key

**Supported algorithms:** Fernet, AES-256-GCM

---

## UC-8: Multi-Provider LLM Usage

**Actor:** Pipeline Designer

**Goal:** Use different LLM providers for different agents in the same pipeline to optimize cost, capability, and performance.

**Flow:**
1. Designer configures a pipeline with mixed providers:
   - Agent 1 (context analysis): AWS Bedrock / Claude 3 Sonnet — good at understanding
   - Agent 2 (content generation): OpenAI / GPT-4 — strong at writing
   - Agent 3 (validation): Bedrock / Claude 3 Haiku — fast and cheap for checks
   - Agent 4 (formatting): GitHub Copilot — code-oriented formatting
2. Each agent gets its own Strands model provider instance via ModelFactory
3. Pipeline executes with each agent routing to its configured provider
4. If any provider is unreachable, the error identifies which provider failed

**Supported providers:**
- AWS Bedrock (Claude, Mistral, Llama, Titan)
- OpenAI-compatible (OpenAI, Azure OpenAI, Mistral API, vLLM, Ollama)
- GitHub Copilot (via OAuth)

---

## UC-9: FAISS-Enriched Agent Reasoning

**Actor:** Pipeline Designer

**Goal:** Enrich agent reasoning with domain-specific knowledge from up to 4 FAISS vector indexes.

**Flow:**
1. Admin configures FAISS indexes representing different document corpora:
   - Index 0: Standards and norms
   - Index 1: Domain guidelines and policies
   - Index 2: Catalogs and reference data
   - Index 3: Past examples and lessons learned
2. Pipeline config specifies which indexes each agent can query
3. During execution, agents use the `query_faiss` tool to retrieve relevant document fragments ranked by similarity score
4. Retrieved context guides the agent's reasoning and output construction

**Value:** Agents don't rely solely on their training data — they ground their output in organization-specific documents, improving accuracy and compliance.

---

## UC-10: Bilingual Interface Usage

**Actor:** User (French or English speaker)

**Goal:** Use the application entirely in the preferred language.

**Flow:**
1. On first visit, the UI detects the browser's language preference
2. If the browser is set to French, the entire interface renders in French; otherwise English
3. User can manually switch language at any time via the language toggle button
4. Switching language does not lose session state (uploaded files, chat history, execution results)
5. Chat interface accepts input in both English and French
6. Theme (dark/light) can also be toggled independently without affecting session state
