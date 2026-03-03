# Requirements Document

## Introduction

INTENT is a modern web application that allows users to submit input files, process them through a configurable AI agentic pipeline built on AWS Strands Python SDK, and produce structured output documents based on predefined templates. The system leverages up to 4 FAISS vector indexes for domain knowledge retrieval and delivers fully traceable, replayable, auditable results. The frontend is built with React 18+ and TypeScript; the backend uses FastAPI with WebSocket streaming.

## Glossary

- **INTENT_UI**: The React 18+ frontend application providing file input, chat, output viewing, execution monitoring, and configuration panels
- **File_Ingestion_Service**: The backend component responsible for receiving, validating, and optionally decrypting uploaded input files
- **Chat_Interface**: The bilingual (EN/FR) natural language conversational component embedded in the frontend
- **Pipeline_Orchestrator**: The backend component that manages the sequential execution of agents in a configured pipeline using AWS Strands Python SDK
- **Agent**: A single processing unit within the pipeline, configured with a specific LLM model, tools, and FAISS index access
- **FAISS_Index_Manager**: The component responsible for managing up to 4 FAISS vector indexes for similarity search
- **LLM_Router**: The component that routes LLM requests to the configured provider (AWS Bedrock, OpenAI-compatible, or GitHub Copilot) for each agent
- **Template_Registry**: The configurable registry of output document templates with format, structure, and validation rules
- **Output_Generator**: The component that renders final documents from templates using Jinja2
- **Execution_Logger**: The component that records full execution traces including inputs, prompts, LLM responses, agent decisions, and outputs
- **Metrics_Collector**: The component that collects token counts and LLM call counts per agent per session
- **Replay_Engine**: The component that enables step-by-step replay of past pipeline executions
- **Encryption_Service**: The component that handles independent, configurable encryption and decryption for inputs, outputs, and logs
- **Tool_Executor**: The component that provides agent tools: file read, file write, Python REPL (cross-platform), and shell (Bash + PowerShell)
- **Pipeline_Config**: A YAML or JSON file (or Strands Graph) that defines the pipeline structure, agent sequence, model assignments, tool access, and FAISS index bindings
- **Session**: A single end-to-end execution of a pipeline from file submission to output generation

## Requirements

### Requirement 1: File Upload via Drag and Drop

**User Story:** As a user, I want to drag and drop one or more input files into the application, so that I can submit documents for processing without manual file browsing.

#### Acceptance Criteria

1. THE INTENT_UI SHALL provide a visual drop zone that accepts one or more files via drag and drop
2. THE File_Ingestion_Service SHALL accept files in the following formats: PPTX, DOCX, PDF, TXT, HTML, and Markdown
3. WHEN a user drops files onto the drop zone, THE INTENT_UI SHALL display a preview of each file with its detected format
4. WHEN a user drops a file with an unsupported format, THE INTENT_UI SHALL display an error message identifying the unsupported format
5. IF a file upload fails, THEN THE File_Ingestion_Service SHALL return a descriptive error message indicating the cause of failure

### Requirement 2: Natural Language Chat Interface

**User Story:** As a user, I want to interact with the system through a natural language chat in English or French, so that I can formulate requests, ask questions, and steer the pipeline conversationally.

#### Acceptance Criteria

1. THE Chat_Interface SHALL accept natural language input in English and French
2. THE Chat_Interface SHALL support automatic language detection or manual language selection
3. WHEN a user sends a chat message, THE Chat_Interface SHALL display the response streamed in real time from the backend via WebSocket
4. THE Chat_Interface SHALL maintain conversation context within a session

### Requirement 3: Agentic Pipeline Orchestration

**User Story:** As a user, I want the system to process my input files through a configurable sequence of AI agents, so that each agent contributes a specific step toward producing the final output document.

#### Acceptance Criteria

1. THE Pipeline_Orchestrator SHALL execute agents sequentially as defined in the Pipeline_Config
2. WHEN a pipeline execution starts, THE Pipeline_Orchestrator SHALL pass the output of each agent as input to the next agent in the sequence
3. THE Pipeline_Orchestrator SHALL support pipeline definitions in YAML format, JSON format, and Strands Graph format
4. WHEN an agent in the pipeline fails, THE Pipeline_Orchestrator SHALL halt execution and report the failure with the agent name, step number, and error details
5. THE Pipeline_Orchestrator SHALL support pipelines containing 1 to N agents with no fixed upper limit

### Requirement 4: Per-Agent LLM Model Configuration

**User Story:** As an administrator, I want to assign a different LLM model and provider to each agent in the pipeline, so that I can optimize cost, performance, and capability per processing step.

#### Acceptance Criteria

1. THE LLM_Router SHALL route each agent's LLM requests to the provider and model specified in the Pipeline_Config
2. THE LLM_Router SHALL support AWS Bedrock as an LLM provider
3. THE LLM_Router SHALL support OpenAI-compatible endpoints (including OpenAI, Azure OpenAI, Mistral API, vLLM, and Ollama) as LLM providers
4. THE LLM_Router SHALL support GitHub Copilot via OAuth authentication as an LLM provider
5. IF an LLM provider is unreachable, THEN THE LLM_Router SHALL return an error identifying the provider and the connection failure reason

### Requirement 5: FAISS Vector Index Management

**User Story:** As an administrator, I want to configure up to 4 FAISS vector indexes representing different document corpora, so that agents can retrieve domain-specific context during processing.

#### Acceptance Criteria

1. THE FAISS_Index_Manager SHALL support up to 4 concurrent FAISS vector indexes per pipeline execution
2. THE Pipeline_Config SHALL specify which FAISS indexes each agent can query
3. WHEN an agent queries a FAISS index, THE FAISS_Index_Manager SHALL return relevant document fragments ranked by similarity score
4. IF a configured FAISS index is unavailable, THEN THE FAISS_Index_Manager SHALL report an error identifying the missing index

### Requirement 6: Agent Tools

**User Story:** As a pipeline designer, I want agents to have access to file read, file write, Python REPL, and shell tools, so that agents can perform file operations, execute code, and run system commands during processing.

#### Acceptance Criteria

1. THE Tool_Executor SHALL provide a file read tool that reads file contents from the local file system
2. THE Tool_Executor SHALL provide a file write tool that writes content to the local file system
3. THE Tool_Executor SHALL provide a Python REPL tool that executes Python code on both Windows and Linux operating systems
4. THE Tool_Executor SHALL provide a shell tool that executes commands via Bash on Linux and PowerShell on Windows
5. THE Pipeline_Config SHALL specify which tools each agent is permitted to use
6. WHEN an agent invokes a tool not permitted by the Pipeline_Config, THE Tool_Executor SHALL deny the request and log the denied attempt

### Requirement 7: Output Template Registry and Document Generation

**User Story:** As a user, I want the system to generate output documents based on predefined templates in multiple formats, so that I receive structured, compliant documents ready for use.

#### Acceptance Criteria

1. THE Template_Registry SHALL store templates that define output format, document structure, validation rules, required metadata, and optional encryption settings
2. THE Template_Registry SHALL support output formats including XML, PDF, DOCX, Markdown, and HTML
3. THE Output_Generator SHALL render final documents by applying Jinja2 templates to the pipeline output data
4. WHEN a rendered document fails template validation rules, THE Output_Generator SHALL report which validation rules were violated
5. THE Output_Generator SHALL include required metadata (author, date, version, classification) in each generated document

### Requirement 8: Output Preview and Export

**User Story:** As a user, I want to preview generated documents in the UI and export them in my desired format, so that I can validate results before saving.

#### Acceptance Criteria

1. THE INTENT_UI SHALL display a preview of the generated output document against the selected template
2. THE INTENT_UI SHALL allow the user to export the generated document in PDF, XML, and DOCX formats
3. WHEN a user requests an export, THE Output_Generator SHALL produce the document in the requested format within the same session

### Requirement 9: Execution Logging and Full Traceability

**User Story:** As an auditor, I want every pipeline execution to be fully logged with inputs, prompts, LLM responses, agent decisions, and outputs, so that I can trace and audit the entire document generation process.

#### Acceptance Criteria

1. THE Execution_Logger SHALL record for each pipeline step: timestamp, agent identifier, input data, prompts sent to the LLM, LLM responses, agent decisions, and output data
2. THE Execution_Logger SHALL store logs in structured JSON format
3. THE Execution_Logger SHALL support storage to file system or database (SQLite or PostgreSQL)
4. THE Execution_Logger SHALL record the complete input files and final output documents for each session

### Requirement 10: Execution Replay

**User Story:** As a developer, I want to replay any past pipeline execution step by step, so that I can analyze agent behavior and debug issues.

#### Acceptance Criteria

1. THE Replay_Engine SHALL load a past execution from the Execution_Logger's stored logs
2. THE Replay_Engine SHALL present each pipeline step sequentially with the recorded inputs, prompts, responses, and outputs
3. WHEN a user initiates a replay, THE INTENT_UI SHALL display the execution timeline with step-by-step navigation controls

### Requirement 11: Token and Call Metrics

**User Story:** As an administrator, I want to track token usage and LLM call counts per agent per session, so that I can monitor costs and optimize model usage.

#### Acceptance Criteria

1. THE Metrics_Collector SHALL record total input tokens, total output tokens, and number of LLM calls for each agent in each session
2. THE Metrics_Collector SHALL export metrics as a CSV file per session
3. THE INTENT_UI SHALL display real-time token and call metrics during pipeline execution

### Requirement 12: Configurable Encryption

**User Story:** As a security officer, I want input files, output documents, and execution logs to each support independent, configurable encryption, so that sensitive data is protected according to organizational policies.

#### Acceptance Criteria

1. THE Encryption_Service SHALL support configurable encryption for input files, output documents, and execution logs independently
2. THE Encryption_Service SHALL support different encryption keys and algorithms for input decryption, output encryption, and log encryption
3. WHEN an encrypted input file is uploaded, THE File_Ingestion_Service SHALL decrypt the file using the configured decryption method before processing
4. WHEN output encryption is enabled, THE Output_Generator SHALL encrypt the generated document using the configured encryption method
5. WHEN log encryption is enabled, THE Execution_Logger SHALL encrypt log entries at rest using the configured encryption method

### Requirement 13: Real-Time Execution Monitoring

**User Story:** As a user, I want to see real-time progress of the agentic pipeline execution, so that I can monitor which agent is active and track overall progress.

#### Acceptance Criteria

1. THE INTENT_UI SHALL display a real-time execution timeline showing each agent's status (pending, running, completed, failed)
2. WHILE a pipeline is executing, THE INTENT_UI SHALL stream live log entries from the backend via WebSocket
3. WHILE a pipeline is executing, THE INTENT_UI SHALL display the currently active agent and its progress

### Requirement 14: Pipeline Configuration Management

**User Story:** As an administrator, I want to create and manage pipeline configurations through the UI, so that I can define agent sequences, model assignments, tool access, and FAISS index bindings without editing code.

#### Acceptance Criteria

1. THE INTENT_UI SHALL provide a configuration panel for creating and editing Pipeline_Config files
2. THE INTENT_UI SHALL allow configuration of LLM providers, agent model assignments, template selections, and FAISS index bindings
3. THE Pipeline_Orchestrator SHALL load and validate Pipeline_Config files before execution
4. IF a Pipeline_Config file contains invalid settings, THEN THE Pipeline_Orchestrator SHALL report specific validation errors before execution begins

### Requirement 15: Bilingual User Interface

**User Story:** As a user, I want the application interface to be available in English and French, so that I can use the application in my preferred language.

#### Acceptance Criteria

1. THE INTENT_UI SHALL support English and French as interface languages
2. THE INTENT_UI SHALL support automatic browser language detection for initial language selection
3. THE INTENT_UI SHALL allow manual language switching at any time without losing session state
4. THE INTENT_UI SHALL use i18next for internationalization of all user-facing text

### Requirement 16: Dark and Light Theme

**User Story:** As a user, I want to switch between dark and light themes, so that I can use the application comfortably in different lighting conditions.

#### Acceptance Criteria

1. THE INTENT_UI SHALL support a dark theme and a light theme
2. THE INTENT_UI SHALL allow the user to switch between themes at any time without losing session state
3. THE INTENT_UI SHALL detect the user's operating system theme preference as the default theme

### Requirement 17: LLM Response Streaming

**User Story:** As a user, I want to see LLM responses streamed in real time, so that I do not have to wait for the full response before seeing partial results.

#### Acceptance Criteria

1. WHEN an LLM generates a response, THE INTENT_UI SHALL display the response tokens as they are received via WebSocket streaming
2. THE Pipeline_Orchestrator SHALL forward streamed LLM responses from the backend to the frontend via WebSocket in real time

### Requirement 18: Audit Compliance

**User Story:** As a compliance officer, I want execution logs to be structured for audit purposes, so that I can determine who produced what output, when, with which input data, and which LLM model.

#### Acceptance Criteria

1. THE Execution_Logger SHALL record the authenticated user identity for each session
2. THE Execution_Logger SHALL record the LLM provider and model identifier used by each agent in each session
3. THE Execution_Logger SHALL record timestamps with timezone information for each logged event
4. THE Execution_Logger SHALL produce logs in a structured format that associates input files, agent processing steps, and output documents within a single session record

### Requirement 19: Pipeline Configuration Parsing and Serialization

**User Story:** As a developer, I want pipeline configurations to be reliably parsed from YAML/JSON and serialized back, so that configurations are not corrupted during read/write cycles.

#### Acceptance Criteria

1. WHEN a YAML Pipeline_Config file is provided, THE Pipeline_Orchestrator SHALL parse the file into an internal Pipeline_Config object
2. WHEN a JSON Pipeline_Config file is provided, THE Pipeline_Orchestrator SHALL parse the file into an internal Pipeline_Config object
3. THE Pipeline_Orchestrator SHALL serialize a Pipeline_Config object back into valid YAML or JSON format
4. FOR ALL valid Pipeline_Config objects, parsing then serializing then parsing SHALL produce an equivalent Pipeline_Config object (round-trip property)
5. WHEN an invalid Pipeline_Config file is provided, THE Pipeline_Orchestrator SHALL return a descriptive error identifying the location and nature of the parsing failure

### Requirement 20: Authentication and Access Control

**User Story:** As a security officer, I want the application to authenticate users and control access, so that only authorized users can submit files, execute pipelines, and view results.

#### Acceptance Criteria

1. THE INTENT_UI SHALL require user authentication before granting access to application features
2. THE File_Ingestion_Service SHALL reject file uploads from unauthenticated requests
3. THE Pipeline_Orchestrator SHALL reject pipeline execution requests from unauthenticated requests
4. THE INTENT_UI SHALL enforce role-based access so that only administrators can modify Pipeline_Config, LLM provider settings, and template configurations
