# Requirements Document

## Introduction

The Smart Chat Strands feature upgrades the existing INTENT chat system from a stateless, single-model conversation endpoint into a persistent, multi-personality, retrieval-augmented chat platform. Each personality gains its own system prompt, environment data injection, retrieval backends (SQLite with BM25 variants and Bedrock embedding models), a primary model with automatic fallback to a stronger model for harder tasks, and full access to the Strands SDK tool ecosystem. Conversation memory is managed through the Strands SDK memory management capabilities, replacing the current in-memory-only context.

## Glossary

- **Chat_Session**: A WebSocket-connected conversation identified by a session ID, holding persistent message history and personality binding.
- **Personality**: A named configuration that defines a system prompt, environment data sources, retrieval backends, model assignments, and tool permissions for a Chat_Session.
- **Personality_Store**: The service responsible for loading, persisting, and validating Personality configurations (currently JSON-backed, extended with new fields).
- **Memory_Manager**: The component that uses Strands SDK memory management to persist and retrieve conversation history across Chat_Session reconnections.
- **Memory_Condenser**: A sub-component of the Memory_Manager that periodically evaluates stored conversation history and condenses low-value messages (repetitive exchanges, resolved tangents, superseded information) into compact summaries, keeping the active context focused and token-efficient.
- **Retrieval_Backend**: A pluggable search component attached to a Personality that queries indexed data. Supported types: SQLite_BM25, FAISS_Embedding, Bedrock_Embedding.
- **SQLite_BM25**: A retrieval backend that queries a SQLite database using BM25 Okapi or BM25F ranking algorithms over FTS5 virtual tables.
- **FAISS_Embedding**: A retrieval backend that queries FAISS vector indexes using sentence-transformer embeddings (existing FAISSIndexManager).
- **Bedrock_Embedding**: A retrieval backend that queries FAISS vector indexes using Amazon Bedrock embedding models (Titan Text Embeddings V2 or Nova Multimodal Embeddings).
- **Primary_Model**: The default LLM model assigned to a Personality for standard conversation turns.
- **Fallback_Model**: A stronger or alternative LLM model that the system escalates to when the Primary_Model cannot handle a task adequately.
- **Escalation_Detector**: The component that determines whether a conversation turn should be routed to the Fallback_Model instead of the Primary_Model.
- **Environment_Injector**: The component that loads external data from a Personality's configured environment sources and injects it into the system prompt or agent context.
- **Tool_Registry**: The registry of all available Strands SDK tools, including built-in tools and user-provided custom tools.
- **Retrieval_Router**: The component that selects and queries the appropriate Retrieval_Backend(s) for a Personality based on the user query.
- **Personality_Config**: The serialized configuration format (JSON) for a Personality, including all new fields for retrieval, models, and environment.

## Requirements

### Requirement 1: Conversation Memory Persistence

**User Story:** As a user, I want my chat conversations to be remembered across reconnections, so that I do not lose context when my WebSocket connection drops or I return later.

#### Acceptance Criteria

1. WHEN a user sends a message in a Chat_Session, THE Memory_Manager SHALL persist the message and its role to durable storage before sending the response.
2. WHEN a user reconnects to an existing Chat_Session, THE Memory_Manager SHALL restore the full conversation history from durable storage.
3. THE Memory_Manager SHALL use the Strands SDK memory management API as the persistence mechanism.
4. WHILE a Chat_Session is active, THE Memory_Manager SHALL maintain an in-memory cache of the conversation history synchronized with durable storage.
5. IF the Strands SDK memory management API is unavailable, THEN THE Memory_Manager SHALL fall back to local file-based persistence and log a warning.
6. WHEN a Chat_Session conversation history exceeds a configurable token limit, THE Memory_Manager SHALL summarize older messages while preserving the most recent messages in full.
7. THE Memory_Condenser SHALL periodically evaluate the conversation history and condense low-value messages (repetitive exchanges, resolved tangents, superseded information) into compact summaries.
8. THE Memory_Condenser SHALL run after every configurable number of conversation turns (default: every 10 turns) or when the total token count exceeds a configurable threshold, whichever comes first.
9. WHEN the Memory_Condenser runs, IT SHALL preserve key facts, decisions, and user preferences extracted from the condensed messages, discarding only redundant or obsolete content.
10. THE Memory_Condenser SHALL store the condensed summary as a special "summary" message in the conversation history, replacing the original messages it condensed.
11. WHEN a user reconnects to a Chat_Session that has been condensed, THE Memory_Manager SHALL present the condensed summary followed by the recent unconsumed messages, so the conversation remains coherent.

### Requirement 2: Enhanced Personality Model

**User Story:** As an administrator, I want to configure rich personalities with retrieval backends, model assignments, and environment data sources, so that each personality can specialize in different domains.

#### Acceptance Criteria

1. THE Personality_Config SHALL include a list of Retrieval_Backend configurations, each specifying a backend type and connection parameters.
2. THE Personality_Config SHALL include a Primary_Model configuration specifying provider type, model ID, and model parameters.
3. THE Personality_Config SHALL include a Fallback_Model configuration specifying provider type, model ID, and model parameters.
4. THE Personality_Config SHALL include a list of environment data source paths that the Environment_Injector reads at session initialization.
5. THE Personality_Config SHALL include an access control list specifying which Retrieval_Backend indexes the Personality is permitted to query, identified by backend type and index name or database path.
6. WHEN a Retrieval_Backend query is initiated, THE Retrieval_Router SHALL verify that the active Personality has access to the requested index and reject queries to unauthorized indexes with a logged warning.
7. WHEN a Personality_Config omits the allowed retrieval indexes list, THE Personality_Store SHALL default to granting access only to the Retrieval_Backends explicitly listed in that Personality's Retrieval_Backend configurations.
8. WHEN a Personality_Config is loaded, THE Personality_Store SHALL validate that all referenced Retrieval_Backend connections are reachable.
9. WHEN a Personality_Config omits the Fallback_Model, THE Personality_Store SHALL default the Fallback_Model to the same configuration as the Primary_Model.
10. THE Personality_Config SHALL remain backward-compatible with existing personality JSON files that lack the new fields, mapping existing allowed_faiss_indexes to the new retrieval access control format.

### Requirement 3: SQLite BM25 Retrieval Backend

**User Story:** As a user, I want the chat personality to search indexed data in a SQLite database using BM25 ranking, so that I get relevant keyword-matched results from structured data.

#### Acceptance Criteria

1. WHEN a query is submitted to a SQLite_BM25 backend, THE Retrieval_Router SHALL execute a FTS5 full-text search against the configured SQLite database.
2. THE SQLite_BM25 backend SHALL support both BM25 Okapi and BM25F ranking algorithms, selectable per Retrieval_Backend configuration.
3. WHEN the SQLite_BM25 backend returns results, THE Retrieval_Router SHALL return document fragments ranked by descending BM25 score.
4. IF the configured SQLite database file does not exist, THEN THE SQLite_BM25 backend SHALL return an error message indicating the database is unavailable.
5. IF the configured SQLite database lacks the expected FTS5 virtual table, THEN THE SQLite_BM25 backend SHALL return an error message indicating the index is not initialized.
6. THE SQLite_BM25 backend SHALL accept a configurable top-k parameter limiting the number of returned results.

### Requirement 4: Bedrock Embedding Retrieval Backend

**User Story:** As a user, I want the chat personality to search indexed data using Amazon Bedrock embedding models, so that I get semantically relevant results using cloud-hosted embeddings.

#### Acceptance Criteria

1. WHEN a query is submitted to a Bedrock_Embedding backend, THE Retrieval_Router SHALL generate a query embedding using the configured Bedrock embedding model.
2. THE Bedrock_Embedding backend SHALL support Amazon Titan Text Embeddings V2 and Amazon Nova Multimodal Embeddings models.
3. WHEN the Bedrock_Embedding backend generates a query embedding, THE Retrieval_Router SHALL search the associated FAISS index and return document fragments ranked by descending similarity score.
4. IF the Bedrock embedding API call fails, THEN THE Bedrock_Embedding backend SHALL return an error message including the Bedrock error details.
5. IF the Bedrock embedding API call fails and a FAISS_Embedding backend is configured for the same index, THEN THE Retrieval_Router SHALL fall back to the FAISS_Embedding backend using sentence-transformers.
6. THE Bedrock_Embedding backend SHALL accept a configurable top-k parameter limiting the number of returned results.

### Requirement 5: Retrieval Router and Multi-Backend Query

**User Story:** As a user, I want the chat system to automatically query the right retrieval backends for my personality, so that I get the most relevant information without manually choosing a search method.

#### Acceptance Criteria

1. WHEN a user message is received in a Chat_Session, THE Retrieval_Router SHALL query all Retrieval_Backends configured for the active Personality.
2. WHEN multiple Retrieval_Backends return results, THE Retrieval_Router SHALL merge and deduplicate results by document fragment content.
3. THE Retrieval_Router SHALL inject the merged retrieval results into the agent context as supplementary information before the agent generates a response.
4. IF all configured Retrieval_Backends fail for a query, THEN THE Retrieval_Router SHALL log the failures and allow the agent to respond without retrieval context.
5. THE Retrieval_Router SHALL execute queries to independent Retrieval_Backends concurrently.
6. WHEN no Retrieval_Backends are configured for a Personality, THE Retrieval_Router SHALL skip retrieval and pass the user message directly to the agent.

### Requirement 6: Primary and Fallback Model Escalation

**User Story:** As a user, I want the system to automatically use a stronger model when my question is too complex for the default model, so that I get better answers for difficult tasks.

#### Acceptance Criteria

1. WHEN a user message is received, THE Escalation_Detector SHALL evaluate whether the Primary_Model is sufficient for the task.
2. WHEN the Escalation_Detector determines the Primary_Model is sufficient, THE Chat_Session SHALL route the message to the Primary_Model.
3. WHEN the Escalation_Detector determines the task requires escalation, THE Chat_Session SHALL route the message to the Fallback_Model.
4. IF the Primary_Model returns an error or an empty response, THEN THE Chat_Session SHALL retry the message with the Fallback_Model.
5. IF the Fallback_Model also returns an error, THEN THE Chat_Session SHALL return an error message to the user indicating both models failed.
6. THE Escalation_Detector SHALL use configurable heuristics including message length, detected complexity keywords, and conversation context depth to determine escalation.
7. WHEN a message is routed to the Fallback_Model, THE Chat_Session SHALL include a metadata flag in the response indicating the fallback model was used.

### Requirement 7: Environment Data Injection

**User Story:** As an administrator, I want each personality to load data from its environment at session start, so that the personality has domain-specific context available for every conversation.

#### Acceptance Criteria

1. WHEN a Chat_Session is initialized with a Personality, THE Environment_Injector SHALL read all configured environment data source paths for that Personality.
2. THE Environment_Injector SHALL support file paths (text, JSON, YAML) and environment variable references as data sources.
3. WHEN environment data is loaded, THE Environment_Injector SHALL append the data to the Personality system prompt as structured context.
4. IF an environment data source path does not exist, THEN THE Environment_Injector SHALL log a warning and continue initialization without that source.
5. IF an environment data source file cannot be parsed, THEN THE Environment_Injector SHALL log a warning with the parse error and continue initialization without that source.
6. WHEN a Personality has no configured environment data sources, THE Environment_Injector SHALL use the Personality system prompt without modification.

### Requirement 8: Strands SDK Tool Integration

**User Story:** As a user, I want the chat personalities to use all tools provided by the Strands SDK, so that the agent can perform actions like file operations, code execution, and web searches during our conversation.

#### Acceptance Criteria

1. THE Tool_Registry SHALL discover and register all tools available from the Strands SDK tools package.
2. THE Tool_Registry SHALL support registration of user-provided custom tools at runtime.
3. WHEN a Personality is loaded, THE Tool_Registry SHALL filter available tools to only those permitted by the Personality access controls.
4. WHEN a new tool is registered at runtime, THE Tool_Registry SHALL make the tool available to all Personalities whose access controls permit the tool.
5. IF a tool execution fails, THEN THE Tool_Registry SHALL return the error message to the agent without terminating the Chat_Session.
6. THE Tool_Registry SHALL maintain backward compatibility with the existing ALL_TOOLS registry and CHAT_TOOLS subset.

### Requirement 9: Personality Configuration Serialization

**User Story:** As a developer, I want to serialize and deserialize personality configurations reliably, so that personality data is not corrupted during storage and retrieval.

#### Acceptance Criteria

1. THE Personality_Store SHALL serialize Personality_Config objects to JSON format.
2. THE Personality_Store SHALL deserialize JSON strings into Personality_Config objects.
3. FOR ALL valid Personality_Config objects, serializing then deserializing SHALL produce an equivalent Personality_Config object (round-trip property).
4. WHEN a Personality_Config JSON string contains unknown fields, THE Personality_Store SHALL ignore the unknown fields and parse the known fields.
5. IF a Personality_Config JSON string is malformed, THEN THE Personality_Store SHALL return a descriptive error indicating the parse failure location.

### Requirement 10: Chat Session Personality Switching

**User Story:** As a user, I want to switch personalities mid-conversation, so that I can consult different domain experts within the same session.

#### Acceptance Criteria

1. WHEN a user sends a message with a different personality_id than the current Chat_Session personality, THE Chat_Session SHALL switch to the new Personality.
2. WHEN a Personality switch occurs, THE Chat_Session SHALL reinitialize the agent with the new Personality system prompt, retrieval backends, model assignments, and tools.
3. WHEN a Personality switch occurs, THE Memory_Manager SHALL preserve the conversation history from the previous Personality.
4. IF the requested personality_id does not exist in the Personality_Store, THEN THE Chat_Session SHALL return an error message indicating the personality is not found.
5. WHEN a Personality switch occurs, THE Chat_Session SHALL send a metadata event to the client indicating the active personality has changed.

### Requirement 11: Graceful Degradation

**User Story:** As a developer, I want the smart chat system to degrade gracefully when optional dependencies are unavailable, so that the system remains functional in minimal environments.

#### Acceptance Criteria

1. IF the Strands SDK is not installed, THEN THE Chat_Session SHALL fall back to the existing default chat agent behavior.
2. IF the SQLite database library is unavailable, THEN THE SQLite_BM25 backend SHALL be disabled and THE Retrieval_Router SHALL skip SQLite retrieval with a logged warning.
3. IF the Bedrock embedding API credentials are not configured, THEN THE Bedrock_Embedding backend SHALL be disabled and THE Retrieval_Router SHALL skip Bedrock retrieval with a logged warning.
4. IF the FAISS library is not installed, THEN THE FAISS_Embedding and Bedrock_Embedding backends SHALL be disabled and THE Retrieval_Router SHALL skip vector retrieval with a logged warning.
5. THE Chat_Session SHALL remain functional with zero Retrieval_Backends configured, operating as a direct LLM conversation.
