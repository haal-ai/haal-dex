# Feature: intent, Property 21: Replay preserves execution data
"""Property 21: Replay preserves execution data

For any completed session, loading the replay should present all pipeline
steps in sequential order, and each step should contain the same inputs,
prompts, responses, and outputs as originally recorded.

**Validates: Requirements 10.1, 10.2**

Strategy:
- Generate a random session with N steps (1-10), each with random agent_id,
  input_data, prompts, responses, decisions, output_data.
- Log them via ExecutionLogger (log_session_start, log_step * N, log_session_end).
- Load via ReplayEngine.load_execution().
- Verify all steps are present in order with matching data.
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from app.config import Settings
from app.models.execution import ExecutionStep
from app.models.files import IngestedFile
from app.models.pipeline import (
    AgentConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)
from app.models.templates import DocumentMetadata, RenderedDocument
from app.services.execution_logger import ExecutionLogger
from app.services.replay_engine import ReplayEngine

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=50,
)
_short_id = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
)
_dict_data = st.dictionaries(
    keys=_short_id,
    values=_text,
    min_size=0,
    max_size=5,
)
_string_list = st.lists(_text, min_size=0, max_size=5)


@st.composite
def execution_step_strategy(draw, step_number: int):
    """Draw a random ExecutionStep with the given step number."""
    agent_id = draw(_short_id)
    agent_name = draw(_short_id)
    input_data = draw(_dict_data)
    prompts_sent = draw(_string_list)
    llm_responses = draw(_string_list)
    decisions = draw(_string_list)
    output_data = draw(_dict_data)
    llm_provider = draw(st.sampled_from(["bedrock", "openai_compatible", "github_copilot"]))
    llm_model = draw(_short_id)

    return ExecutionStep(
        step_number=step_number,
        agent_id=agent_id,
        agent_name=agent_name,
        status="completed",
        timestamp=datetime.now(timezone.utc),
        input_data=input_data,
        prompts_sent=prompts_sent,
        llm_responses=llm_responses,
        llm_provider=llm_provider,
        llm_model=llm_model,
        decisions=decisions,
        output_data=output_data,
        error=None,
    )


@st.composite
def session_steps_strategy(draw):
    """Draw a list of 1-10 ExecutionSteps with sequential step numbers."""
    n = draw(st.integers(min_value=1, max_value=10))
    steps = []
    for i in range(n):
        step = draw(execution_step_strategy(step_number=i + 1))
        steps.append(step)
    return steps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline_config() -> PipelineConfig:
    """Create a minimal PipelineConfig for session logging."""
    return PipelineConfig(
        name="test-pipeline",
        agents=[
            AgentConfig(
                name="agent-1",
                model="bedrock/test",
                provider_config=ProviderConfig(provider_type="bedrock", model_id="test"),
                description="test agent",
            )
        ],
        output=OutputConfig(template="default", formats=["md"]),
    )


def _make_input_file(session_id: str) -> IngestedFile:
    """Create a minimal IngestedFile for session logging."""
    return IngestedFile(
        id=str(uuid.uuid4()),
        original_name="test.txt",
        format="txt",
        size_bytes=4,
        content=b"test",
        was_encrypted=False,
        session_id=session_id,
    )


def _make_output_doc(session_id: str) -> RenderedDocument:
    """Create a minimal RenderedDocument for session logging."""
    return RenderedDocument(
        id=str(uuid.uuid4()),
        session_id=session_id,
        template_id="default",
        format="md",
        content=b"# Output",
        metadata=DocumentMetadata(
            author="tester",
            date=datetime.now(timezone.utc),
            version="1.0",
            classification="internal",
        ),
        validation_result=[],
    )


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@given(steps=session_steps_strategy())
@settings(max_examples=100, deadline=None)
def test_replay_preserves_execution_data(steps: list[ExecutionStep]):
    """Property 21: Loading replay presents all steps in order with same
    inputs, prompts, responses, outputs as originally recorded.

    **Validates: Requirements 10.1, 10.2**
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        session_id = str(uuid.uuid4())
        config = _make_pipeline_config()
        settings_obj = Settings(log_dir=tmp_dir)
        logger = ExecutionLogger(settings=settings_obj)

        # --- Record session via ExecutionLogger ---
        asyncio.run(logger.log_session_start(
            session_id=session_id,
            user_id="test-user",
            inputs=[_make_input_file(session_id)],
            config=config,
        ))

        for step in steps:
            asyncio.run(logger.log_step(session_id, step))

        asyncio.run(logger.log_session_end(
            session_id=session_id,
            outputs=[_make_output_doc(session_id)],
        ))

        # --- Load via ReplayEngine ---
        engine = ReplayEngine(execution_logger=logger)
        replay = asyncio.run(engine.load_execution(session_id))

        # All steps are present
        assert len(replay.steps) == len(steps), (
            f"Expected {len(steps)} steps, got {len(replay.steps)}"
        )

        # Steps are in sequential order and data matches
        for original, replayed in zip(steps, replay.steps):
            assert replayed.step_number == original.step_number, (
                f"Step number mismatch: {replayed.step_number} != {original.step_number}"
            )
            assert replayed.agent_id == original.agent_id, (
                f"agent_id mismatch at step {original.step_number}"
            )
            assert replayed.agent_name == original.agent_name, (
                f"agent_name mismatch at step {original.step_number}"
            )
            assert replayed.input_data == original.input_data, (
                f"input_data mismatch at step {original.step_number}"
            )
            assert replayed.prompts_sent == original.prompts_sent, (
                f"prompts_sent mismatch at step {original.step_number}"
            )
            assert replayed.llm_responses == original.llm_responses, (
                f"llm_responses mismatch at step {original.step_number}"
            )
            assert replayed.decisions == original.decisions, (
                f"decisions mismatch at step {original.step_number}"
            )
            assert replayed.output_data == original.output_data, (
                f"output_data mismatch at step {original.step_number}"
            )

        # Timeline also has the correct count and order
        assert len(replay.timeline) == len(steps)
        for i, entry in enumerate(replay.timeline):
            assert entry.step_number == steps[i].step_number
            assert entry.agent_id == steps[i].agent_id
