# Implementation Plan: Smart Chat Strands

## Overview

This plan upgrades the INTENT chat system into a persistent, retrieval-augmented, multi-personality chat platform built on the Strands Agents SDK. Implementation proceeds bottom-up: data models and standalone services first, then retrieval backends, then the orchestration layer (router, escalation, tools), and finally the refactored WebSocket endpoint that wires everything together. Each task builds on the previous ones so there is no orphaned code.

## Tasks

- [x] 1. Extend the Personality model and PersonalityStore with new fields
  - [x] 1.1 Add new dataclasses to `backend/app/models/personality.py`
    - Add `RetrievalBackendConfig`, `ModelConfig`, `RetrievalACLEntry` dataclasses
    - Extend `PersonalityAccess` with `allowed_retrieval_indexes: list[RetrievalACLEntry] | None`
    - Extend `Personality` with `retrieval_backends`, `primary_model`, `fallback_model`, `env_data_sources` fields
    - All new fields must have defaults so existing code continues to work
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.10_

  - [x] 1.2 Extend `PersonalityStore` in `backend/app/services/personality_store.py`
    - Add `serialize(personality) -> str` method (JSON output)
    - Add `deserialize(json_str) -> Personality` method (unknown fields ignored, malformed JSON raises descriptive error)
    - Add `_migrate_legacy_access(data) -> dict` to map `allowed_faiss_indexes` to `allowed_retrieval_indexes`
    - Add `validate_backends(personality) -> list[str]` to check backend reachability
    - Update `_parse_personality` to parse new fields with backward-compatible defaults
    - When `fallback_model` is omitted, default it to `primary_model`
    - _Requirements: 2.8, 2.9, 2.10, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 1.3 Write property test for Personality config serialization round-trip
    - **Property 11: Personality config serialization round-trip**
    - **Validates: Requirements 9.1, 9.2, 9.3, 2.1, 2.2, 2.3, 2.4, 2.5**

  - [ ]* 1.4 Write property test for unknown field tolerance in deserialization
    - **Property 12: Unknown field tolerance in deserialization**
    - **Validates: Requirements 9.4, 2.10**

  - [ ]* 1.5 Write property test for fallback model defaults to primary
    - **Property 4: Fallback model defaults to primary**
    - **Validates: Requirements 2.9**

  - [ ]* 1.6 Write unit tests for PersonalityStore backward compatibility
    - Test loading legacy personality JSON (without new fields)
    - Test `_migrate_legacy_access` maps `allowed_faiss_indexes` correctly
    - Test malformed JSON produces descriptive error with location
    - _Requirements: 2.10, 9.5_

- [x] 2. Implement MemoryManager with condensation
  - [x] 2.1 Create `backend/app/services/memory_manager.py`
    - Implement `MemoryManager` class with `persist_message`, `restore_history`, `maybe_condense`, `create_conversation_manager`
    - Use JSON file storage at `{storage_dir}/{session_id}.json`
    - Integrate Strands SDK `SummarizingConversationManager` for condensation when available
    - Fall back to file-based persistence when Strands SDK is unavailable (log warning)
    - Condensation triggers: every N turns (default 10) or when token count exceeds threshold
    - Condensed messages replaced with a single "summary" role message preserving key facts
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11_

  - [ ]* 2.2 Write property test for conversation memory round-trip
    - **Property 1: Conversation memory round-trip**
    - **Validates: Requirements 1.1, 1.2, 1.4**

  - [ ]* 2.3 Write property test for condensation preserves recent messages
    - **Property 2: Condensation preserves recent messages and produces summary**
    - **Validates: Requirements 1.6, 1.7, 1.8, 1.10, 1.11**

  - [ ]* 2.4 Write unit tests for MemoryManager edge cases
    - Test empty session restore returns empty list
    - Test persist then restore round-trip with multiple messages
    - Test fallback to file-based when Strands SDK unavailable
    - Test condensation with conversation below threshold (no-op)
    - _Requirements: 1.1, 1.2, 1.5_

- [x] 3. Implement EnvironmentInjector
  - [x] 3.1 Create `backend/app/services/environment_injector.py`
    - Implement `EnvironmentInjector.inject(system_prompt, data_sources, base_dir) -> str`
    - Support file paths (.txt, .json, .yaml) and env var references ($VAR_NAME)
    - Append loaded data to system prompt as structured context
    - Log warnings for missing/unparseable sources, continue without them
    - When data_sources is empty, return system_prompt unchanged
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 3.2 Write property test for environment injection
    - **Property 9: Environment injection appends data to prompt**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.6**

  - [ ]* 3.3 Write unit tests for EnvironmentInjector
    - Test missing file logs warning and continues
    - Test unparseable YAML/JSON logs warning and continues
    - Test missing env var logs warning and continues
    - Test empty data_sources returns prompt unchanged
    - _Requirements: 7.4, 7.5, 7.6_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement SQLiteBM25Backend
  - [x] 5.1 Create `backend/app/engine/sqlite_bm25_backend.py`
    - Implement `SQLiteBM25Backend` with `query(query_text, top_k)` and `is_available()` methods
    - Implement `BM25Result` dataclass with `document_fragment`, `score`, `source`
    - Use `sqlite3` stdlib with FTS5 `MATCH` queries
    - Support BM25 Okapi (default `bm25()`) and BM25F (column-weighted `bm25()`) ranking
    - Return results sorted by descending BM25 score, limited to top_k
    - Return error message if database file missing or FTS5 table missing
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 5.2 Write property test for retrieval results sorted by descending score (SQLite)
    - **Property 5: Retrieval results sorted by descending score**
    - **Validates: Requirements 3.3**

  - [ ]* 5.3 Write property test for top-k limits result count (SQLite)
    - **Property 6: Top-k limits result count**
    - **Validates: Requirements 3.6**

  - [ ]* 5.4 Write unit tests for SQLiteBM25Backend
    - Test query against a temp SQLite DB with FTS5 table and inserted documents
    - Test `is_available()` returns False for missing database
    - Test `is_available()` returns False for missing FTS5 table
    - Test BM25 Okapi vs BM25F ranking selection
    - _Requirements: 3.1, 3.2, 3.4, 3.5_

- [x] 6. Implement BedrockEmbeddingBackend
  - [x] 6.1 Create `backend/app/engine/bedrock_embedding_backend.py`
    - Implement `BedrockEmbeddingBackend` with `query(query_text, top_k)` and `is_available()` methods
    - Support Titan Text Embeddings V2 and Nova Multimodal Embeddings model IDs
    - Generate query embedding via Bedrock `invoke_model`, search FAISS index
    - Return results sorted by descending similarity score, limited to top_k
    - Return error message with Bedrock error details on API failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6_

  - [ ]* 6.2 Write unit tests for BedrockEmbeddingBackend
    - Mock Bedrock API, create temp FAISS index, verify ranked results
    - Test error handling when Bedrock API fails
    - Test `is_available()` when credentials not configured
    - _Requirements: 4.1, 4.4_

- [x] 7. Implement RetrievalRouter with ACL enforcement and deduplication
  - [x] 7.1 Create `backend/app/engine/retrieval_router.py`
    - Implement `RetrievalRouter` with `query(query_text, top_k)` and `inject_context(results, system_prompt)` methods
    - Implement `RetrievalResult` dataclass
    - Query all permitted backends concurrently using `asyncio.gather`
    - Merge and deduplicate results by exact `document_fragment` content match
    - Sort merged results by descending score
    - Enforce ACL: reject queries to backends not in personality's `allowed_retrieval_indexes`
    - When ACL is omitted, default to backends in personality's `retrieval_backends` config
    - Log failures and allow agent to respond without retrieval context if all backends fail
    - Skip retrieval when no backends configured
    - Fall back to FAISS_Embedding backend when Bedrock_Embedding fails for same index
    - _Requirements: 2.6, 2.7, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 4.5_

  - [ ]* 7.2 Write property test for retrieval ACL enforcement
    - **Property 3: Retrieval ACL enforcement**
    - **Validates: Requirements 2.6, 2.7**

  - [ ]* 7.3 Write property test for retrieval deduplication produces unique fragments
    - **Property 7: Retrieval deduplication produces unique fragments**
    - **Validates: Requirements 5.2, 5.3**

  - [ ]* 7.4 Write property test for retrieval results sorted by descending score (merged)
    - **Property 5: Retrieval results sorted by descending score**
    - **Validates: Requirements 3.3, 4.3**

  - [ ]* 7.5 Write unit tests for RetrievalRouter
    - Test concurrent query with multiple mock backends
    - Test deduplication with overlapping results
    - Test ACL rejection for unauthorized backend
    - Test all backends fail returns empty results
    - Test no backends configured skips retrieval
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement EscalationDetector
  - [x] 9.1 Create `backend/app/engine/escalation_detector.py`
    - Implement `EscalationDetector` with `evaluate(message, conversation_depth) -> EscalationDecision`
    - Implement `EscalationDecision` dataclass with `should_escalate`, `reason`, `was_error_retry`
    - Configurable heuristics: `length_threshold`, `complexity_keywords`, `context_depth_threshold`
    - Deterministic: same inputs always produce same output
    - _Requirements: 6.1, 6.2, 6.3, 6.6_

  - [ ]* 9.2 Write property test for escalation heuristics
    - **Property 8: Escalation heuristics are deterministic and threshold-based**
    - **Validates: Requirements 6.1, 6.6**

  - [ ]* 9.3 Write unit tests for EscalationDetector
    - Test short simple message does not escalate
    - Test long message exceeding length_threshold escalates
    - Test message with complexity keyword escalates
    - Test deep conversation exceeding context_depth_threshold escalates
    - _Requirements: 6.1, 6.2, 6.3, 6.6_

- [ ] 10. Extend ToolRegistry with Strands SDK discovery and runtime registration
  - [x] 10.1 Extend `backend/app/engine/tools.py`
    - Add `ToolRegistry` class with `discover_strands_tools`, `register_custom_tool`, `get_tools_for_personality`, `get_all_tool_names`
    - Discover all tools from `strands_tools` package at init
    - Support runtime custom tool registration
    - Filter tools by personality `allowed_tools` list
    - Maintain backward compatibility with `ALL_TOOLS` and `CHAT_TOOLS`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 10.2 Write property test for tool filtering matches personality ACL
    - **Property 10: Tool filtering matches personality ACL**
    - **Validates: Requirements 8.2, 8.3, 8.4**

  - [ ]* 10.3 Write unit tests for ToolRegistry
    - Test `discover_strands_tools` finds built-in tools
    - Test `register_custom_tool` adds tool and is visible in `get_all_tool_names`
    - Test `get_tools_for_personality` returns intersection of registered and allowed
    - Test backward compatibility: `ALL_TOOLS` and `CHAT_TOOLS` still work
    - _Requirements: 8.1, 8.2, 8.6_

- [x] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Refactor Chat WebSocket endpoint to integrate all components
  - [x] 12.1 Refactor `backend/app/api/chat.py` to use MemoryManager
    - Replace in-memory `_conversations` dict with `MemoryManager` for persistence
    - On connect: restore conversation history via `MemoryManager.restore_history`
    - On each message: persist via `MemoryManager.persist_message` before responding
    - After response: persist assistant message, call `MemoryManager.maybe_condense`
    - On reconnect to condensed session: present summary + recent messages
    - _Requirements: 1.1, 1.2, 1.4, 1.6, 1.11_

  - [x] 12.2 Integrate RetrievalRouter into chat message flow
    - On each user message: query `RetrievalRouter` with personality's backends
    - Inject retrieval results into agent context via `RetrievalRouter.inject_context`
    - Skip retrieval when no backends configured
    - _Requirements: 5.1, 5.3, 5.6_

  - [x] 12.3 Integrate EscalationDetector and model fallback
    - Before agent invocation: evaluate message with `EscalationDetector`
    - Route to primary or fallback model based on decision
    - On primary model error/empty response: retry with fallback model
    - On both models fail: return structured error to client
    - Include `fallback_used` metadata flag in response when fallback is used
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7_

  - [x] 12.4 Integrate EnvironmentInjector and ToolRegistry
    - On session init: inject environment data into personality system prompt
    - Use `ToolRegistry.get_tools_for_personality` for agent tool selection
    - _Requirements: 7.1, 7.3, 8.3_

  - [x] 12.5 Implement personality switching in WebSocket handler
    - Detect personality_id change in incoming message
    - Preserve conversation history on switch (do not clear messages)
    - Reinitialize agent with new personality's prompt, backends, models, tools
    - Send metadata event to client indicating personality change
    - Return error if requested personality_id not found
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 12.6 Write property test for history preservation on personality switch
    - **Property 13: History preservation on personality switch**
    - **Validates: Requirements 10.3**

  - [ ]* 12.7 Write unit tests for refactored chat endpoint
    - Test message persistence and restore on reconnect
    - Test retrieval injection into agent context
    - Test escalation to fallback model on complex message
    - Test error retry with fallback when primary fails
    - Test personality switching preserves history
    - Test personality switch sends metadata event
    - Test unknown personality_id returns error
    - _Requirements: 1.1, 1.2, 5.3, 6.4, 6.7, 10.1, 10.4, 10.5_

- [x] 13. Implement graceful degradation guards
  - [x] 13.1 Add graceful degradation checks across all new components
    - MemoryManager: fall back to file-based when Strands SDK unavailable
    - SQLiteBM25Backend: disable when sqlite3 FTS5 unavailable, log warning
    - BedrockEmbeddingBackend: disable when Bedrock credentials not configured, log warning
    - FAISS backends: disable when faiss library not installed, log warning
    - Chat endpoint: fall back to existing default agent when Strands SDK not installed
    - All components use optional imports with try/except ImportError pattern
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 13.2 Write unit tests for graceful degradation
    - Mock each optional dependency as unavailable, verify fallback behavior
    - Test chat session works with zero retrieval backends
    - Test chat session works without Strands SDK
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The codebase already uses `hypothesis>=6.100.0`, `pytest`, and `pytest-asyncio` — no new test framework setup needed
- All new components follow the existing graceful degradation pattern (optional imports with try/except)
- Python is the implementation language throughout, matching the existing backend
