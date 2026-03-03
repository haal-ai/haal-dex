# Feature: intent, Property 18: Execution log completeness
# Feature: intent, Property 19: Execution logs are valid JSON
# Feature: intent, Property 20: Session logs include input and output documents
"""Property tests for execution logging.

Property 18 — Execution log completeness:
  Each log entry contains timestamp/tz, agent ID, input, prompts, responses,
  decisions, output, user identity, LLM provider/model; session associates
  inputs, steps, outputs.
  **Validates: Requirements 9.1, 18.1, 18.2, 18.3, 18.4**

Property 19 — Execution logs are valid JSON:
  Every log entry is parseable as valid JSON.
  **Validates: Requirements 9.2**

Property 20 — Session logs include input and output documents:
  Completed session logs contain complete input files and output documents.
  **Validates: Requirements 9.4**
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from hypothesis import given, settings, strategies as st

from app.config import Settings
from app.models.execution import ExecutionStep, SessionLog
from app.models.files import IngestedFile
from app.models.pipeline import (
    AgentConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)
from app.models.templates import DocumentMetadata, RenderedDocument
from app.services.execution_logger import ExecutionLogger

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_identifier = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
)

_provider_types = st.sampled_from(["bedrock", "openai_compatible", "github_copilot"])
_model_ids = st.sampled_from([
    "claude-3-sonnet", "gpt-4o", "gpt-4", "mistral-large", "llama-3",
])
_statuses = st.sampled_from(["pending", "running", "completed", "failed"])
_formats = st.sampled_from(["txt", "pdf", "docx", "html", "md", "pptx"])
_output_formats = st.sampled_from(["pdf", "xml", "docx", "md", "html"])

_short_text = st.text(min_size=0, max_size=100)
_text_list = st.lists(_short_text, min_size=0, max_size=5)
_simple_dict = st.dictionaries(
    keys=st.text(min_size=1, max_size=20),
    values=st.text(min_size=0, max_size=50),
    min_size=0,
    max_size=5,
)

# Use latin-1 encodable bytes so content round-trips through JSON
_file_content = st.binary(min_size=0, max_size=200).map(
    lambda b: bytes(x % 256 for x in b)
)


@st.composite
def execution_step_strategy(draw):
    """Generate a random ExecutionStep."""
    return ExecutionStep(
        step_number=draw(st.integers(min_value=0, max_value=100)),
        agent_id=draw(_identifier),
        agent_name=draw(_identifier),
        status=draw(_statuses),
        timestamp=datetime.now(timezone.utc),
        input_data=draw(_simple_dict),
        prompts_sent=draw(_text_list),
        llm_responses=draw(_text_list),
        llm_provider=draw(_provider_types),
        llm_model=draw(_model_ids),
        decisions=draw(_text_list),
        output_data=draw(_simple_dict),
        error=draw(st.one_of(st.none(), _short_text)),
    )


@st.composite
def ingested_file_strategy(draw, session_id: str | None = None):
    """Generate a random IngestedFile."""
    sid = session_id or draw(_identifier)
    return IngestedFile(
        id=draw(_identifier),
        original_name=draw(_identifier) + "." + draw(_formats),
        format=draw(_formats),
        size_bytes=draw(st.integers(min_value=0, max_value=100_000)),
        content=draw(_file_content),
        was_encrypted=draw(st.booleans()),
        session_id=sid,
    )


@st.composite
def rendered_document_strategy(draw, session_id: str | None = None):
    """Generate a random RenderedDocument."""
    sid = session_id or draw(_identifier)
    return RenderedDocument(
        id=draw(_identifier),
        session_id=sid,
        template_id=draw(_identifier),
        format=draw(_output_formats),
        content=draw(_file_content),
        metadata=DocumentMetadata(
            author=draw(_identifier),
            date=datetime.now(timezone.utc),
            version=draw(st.from_regex(r"[0-9]+\.[0-9]+", fullmatch=True)),
            classification=draw(st.sampled_from(["public", "internal", "confidential"])),
        ),
        validation_result=[],
    )


@st.composite
def pipeline_config_strategy(draw):
    """Generate a minimal valid PipelineConfig."""
    n_agents = draw(st.integers(min_value=1, max_value=4))
    agents = []
    for i in range(n_agents):
        agents.append(
            AgentConfig(
                name=f"agent-{i}",
                model=draw(_model_ids),
                provider_config=ProviderConfig(
                    provider_type=draw(_provider_types),
                    model_id=draw(_model_ids),
                ),
                description=draw(_short_text),
                tools=draw(st.lists(
                    st.sampled_from(["read", "write", "python_repl", "shell"]),
                    min_size=0, max_size=3, unique=True,
                )),
            )
        )
    return PipelineConfig(
        name=draw(_identifier),
        agents=agents,
        output=OutputConfig(
            template=draw(_identifier),
            formats=draw(st.lists(_output_formats, min_size=1, max_size=3)),
        ),
    )


def _make_logger(tmp_dir: str) -> ExecutionLogger:
    """Create an ExecutionLogger writing to the given temp directory."""
    s = Settings(log_dir=tmp_dir)
    return ExecutionLogger(settings=s)


# ---------------------------------------------------------------------------
# Property 18: Execution log completeness
# ---------------------------------------------------------------------------


@given(
    session_id=_identifier,
    user_id=_identifier,
    steps=st.lists(execution_step_strategy(), min_size=1, max_size=5),
    input_files=st.lists(ingested_file_strategy(), min_size=1, max_size=3),
    output_docs=st.lists(rendered_document_strategy(), min_size=1, max_size=3),
    config=pipeline_config_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_execution_log_completeness(
    session_id: str,
    user_id: str,
    steps: list[ExecutionStep],
    input_files: list[IngestedFile],
    output_docs: list[RenderedDocument],
    config: PipelineConfig,
):
    """Property 18: Each log entry contains timestamp/tz, agent ID, input,
    prompts, responses, decisions, output, user identity, LLM provider/model;
    session associates inputs, steps, outputs.

    **Validates: Requirements 9.1, 18.1, 18.2, 18.3, 18.4**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        lgr = _make_logger(tmp_dir)

        # Fix session_id references in input files and output docs
        for f in input_files:
            f.session_id = session_id
        for d in output_docs:
            d.session_id = session_id

        # Run the full session lifecycle
        asyncio.run(lgr.log_session_start(session_id, user_id, input_files, config))
        for step in steps:
            asyncio.run(lgr.log_step(session_id, step))
        asyncio.run(lgr.log_session_end(session_id, output_docs))

        # Retrieve the session log
        session_log: SessionLog = asyncio.run(lgr.get_session_log(session_id))

        # --- Session-level completeness ---
        assert session_log.session_id == session_id
        # Req 18.1: authenticated user identity
        assert session_log.user_id == user_id
        # Req 18.4: associates inputs, steps, outputs
        assert len(session_log.steps) == len(steps)
        assert len(session_log.input_files) == len(input_files)
        assert len(session_log.output_documents) == len(output_docs)

        # --- Per-step completeness (Req 9.1, 18.2, 18.3) ---
        for original, logged in zip(steps, session_log.steps):
            # Req 18.3: timestamp with timezone
            assert logged.timestamp is not None
            assert logged.timestamp.tzinfo is not None

            # Req 9.1: agent identifier
            assert logged.agent_id == original.agent_id
            assert logged.agent_name == original.agent_name

            # Req 9.1: input data
            assert logged.input_data == original.input_data

            # Req 9.1: prompts sent
            assert logged.prompts_sent == original.prompts_sent

            # Req 9.1: LLM responses
            assert logged.llm_responses == original.llm_responses

            # Req 9.1: decisions
            assert logged.decisions == original.decisions

            # Req 9.1: output data
            assert logged.output_data == original.output_data

            # Req 18.2: LLM provider and model
            assert logged.llm_provider == original.llm_provider
            assert logged.llm_model == original.llm_model


# ---------------------------------------------------------------------------
# Property 19: Execution logs are valid JSON
# ---------------------------------------------------------------------------


@given(
    session_id=_identifier,
    user_id=_identifier,
    steps=st.lists(execution_step_strategy(), min_size=0, max_size=5),
    input_files=st.lists(ingested_file_strategy(), min_size=0, max_size=3),
    output_docs=st.lists(rendered_document_strategy(), min_size=0, max_size=3),
    config=pipeline_config_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_execution_logs_are_valid_json(
    session_id: str,
    user_id: str,
    steps: list[ExecutionStep],
    input_files: list[IngestedFile],
    output_docs: list[RenderedDocument],
    config: PipelineConfig,
):
    """Property 19: Every log entry is parseable as valid JSON.

    **Validates: Requirements 9.2**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        lgr = _make_logger(tmp_dir)

        for f in input_files:
            f.session_id = session_id
        for d in output_docs:
            d.session_id = session_id

        asyncio.run(lgr.log_session_start(session_id, user_id, input_files, config))
        for step in steps:
            asyncio.run(lgr.log_step(session_id, step))
        asyncio.run(lgr.log_session_end(session_id, output_docs))

        # Read the raw file and verify it's valid JSON
        raw_path = Path(tmp_dir) / f"{session_id}.json"
        assert raw_path.exists(), f"Log file not found at {raw_path}"

        raw_content = raw_path.read_text(encoding="utf-8")
        parsed = json.loads(raw_content)  # Must not raise

        assert isinstance(parsed, dict), "Top-level JSON must be an object"
        assert "session_id" in parsed
        assert "steps" in parsed
        assert isinstance(parsed["steps"], list)

        # Each step must also be a valid JSON object
        for step_data in parsed["steps"]:
            assert isinstance(step_data, dict)


# ---------------------------------------------------------------------------
# Property 20: Session logs include input and output documents
# ---------------------------------------------------------------------------


@given(
    session_id=_identifier,
    user_id=_identifier,
    input_files=st.lists(ingested_file_strategy(), min_size=1, max_size=5),
    output_docs=st.lists(rendered_document_strategy(), min_size=1, max_size=5),
    config=pipeline_config_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_session_logs_include_input_and_output_documents(
    session_id: str,
    user_id: str,
    input_files: list[IngestedFile],
    output_docs: list[RenderedDocument],
    config: PipelineConfig,
):
    """Property 20: Completed session logs contain complete input files and
    output documents.

    **Validates: Requirements 9.4**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        lgr = _make_logger(tmp_dir)

        for f in input_files:
            f.session_id = session_id
        for d in output_docs:
            d.session_id = session_id

        asyncio.run(lgr.log_session_start(session_id, user_id, input_files, config))
        asyncio.run(lgr.log_session_end(session_id, output_docs))

        session_log: SessionLog = asyncio.run(lgr.get_session_log(session_id))

        # Session must be completed
        assert session_log.completed_at is not None

        # --- Input files round-trip ---
        assert len(session_log.input_files) == len(input_files)
        for original, logged in zip(input_files, session_log.input_files):
            assert logged.id == original.id
            assert logged.original_name == original.original_name
            assert logged.format == original.format
            assert logged.size_bytes == original.size_bytes
            assert logged.content == original.content  # complete content preserved
            assert logged.was_encrypted == original.was_encrypted
            assert logged.session_id == original.session_id

        # --- Output documents round-trip ---
        assert len(session_log.output_documents) == len(output_docs)
        for original, logged in zip(output_docs, session_log.output_documents):
            assert logged.id == original.id
            assert logged.session_id == original.session_id
            assert logged.template_id == original.template_id
            assert logged.format == original.format
            assert logged.content == original.content  # complete content preserved
            assert logged.metadata.author == original.metadata.author
            assert logged.metadata.version == original.metadata.version
            assert logged.metadata.classification == original.metadata.classification
