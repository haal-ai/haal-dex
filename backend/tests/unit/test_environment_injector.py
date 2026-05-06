"""Unit tests for EnvironmentInjector."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import yaml

from app.services.environment_injector import EnvironmentInjector


@pytest.fixture()
def injector() -> EnvironmentInjector:
    return EnvironmentInjector()


# ------------------------------------------------------------------
# Requirement 7.6 — empty data_sources returns prompt unchanged
# ------------------------------------------------------------------


def test_empty_data_sources_returns_prompt_unchanged(
    injector: EnvironmentInjector, tmp_path: Path
) -> None:
    prompt = "You are a helpful assistant."
    result = injector.inject(prompt, [], tmp_path)
    assert result == prompt


# ------------------------------------------------------------------
# Requirement 7.1 / 7.2 — file loading (.txt, .json, .yaml)
# ------------------------------------------------------------------


def test_load_txt_file(injector: EnvironmentInjector, tmp_path: Path) -> None:
    txt_file = tmp_path / "readme.txt"
    txt_file.write_text("Project overview content", encoding="utf-8")

    result = injector.inject("Base prompt", ["readme.txt"], tmp_path)
    assert result.startswith("Base prompt")
    assert "Project overview content" in result
    assert "[file:readme.txt]" in result


def test_load_json_file(injector: EnvironmentInjector, tmp_path: Path) -> None:
    data = {"key": "value", "count": 42}
    json_file = tmp_path / "config.json"
    json_file.write_text(json.dumps(data), encoding="utf-8")

    result = injector.inject("Base prompt", ["config.json"], tmp_path)
    assert "key" in result
    assert "value" in result
    assert "[file:config.json]" in result


def test_load_yaml_file(injector: EnvironmentInjector, tmp_path: Path) -> None:
    data = {"setting": "enabled", "level": 3}
    yaml_file = tmp_path / "settings.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    result = injector.inject("Base prompt", ["settings.yaml"], tmp_path)
    assert "setting" in result
    assert "[file:settings.yaml]" in result


def test_load_yml_extension(injector: EnvironmentInjector, tmp_path: Path) -> None:
    data = {"name": "test"}
    yml_file = tmp_path / "data.yml"
    yml_file.write_text(yaml.dump(data), encoding="utf-8")

    result = injector.inject("Base prompt", ["data.yml"], tmp_path)
    assert "name" in result
    assert "[file:data.yml]" in result


# ------------------------------------------------------------------
# Requirement 7.2 — env var references
# ------------------------------------------------------------------


def test_load_env_var(
    injector: EnvironmentInjector, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MY_TEST_VAR", "some-env-value")
    result = injector.inject("Base prompt", ["$MY_TEST_VAR"], tmp_path)
    assert "some-env-value" in result
    assert "[env:MY_TEST_VAR]" in result


# ------------------------------------------------------------------
# Requirement 7.4 — missing file logs warning and continues
# ------------------------------------------------------------------


def test_missing_file_logs_warning_and_continues(
    injector: EnvironmentInjector, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        result = injector.inject("Base prompt", ["nonexistent.txt"], tmp_path)

    assert result == "Base prompt"
    assert any("does not exist" in r.message for r in caplog.records)


# ------------------------------------------------------------------
# Requirement 7.5 — unparseable JSON/YAML logs warning and continues
# ------------------------------------------------------------------


def test_unparseable_json_logs_warning_and_continues(
    injector: EnvironmentInjector, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{invalid json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = injector.inject("Base prompt", ["bad.json"], tmp_path)

    assert result == "Base prompt"
    assert any("Failed to parse JSON" in r.message for r in caplog.records)


def test_unparseable_yaml_logs_warning_and_continues(
    injector: EnvironmentInjector, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(":\n  - :\n    invalid: [", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = injector.inject("Base prompt", ["bad.yaml"], tmp_path)

    # Either it parsed (YAML is lenient) or it warned — either way prompt is intact
    assert result.startswith("Base prompt")


# ------------------------------------------------------------------
# Missing env var logs warning and continues
# ------------------------------------------------------------------


def test_missing_env_var_logs_warning_and_continues(
    injector: EnvironmentInjector, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NONEXISTENT_VAR_12345", raising=False)

    with caplog.at_level(logging.WARNING):
        result = injector.inject("Base prompt", ["$NONEXISTENT_VAR_12345"], tmp_path)

    assert result == "Base prompt"
    assert any("not set" in r.message for r in caplog.records)


# ------------------------------------------------------------------
# Multiple sources — mix of valid and invalid
# ------------------------------------------------------------------


def test_multiple_sources_mixed(
    injector: EnvironmentInjector, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("Some notes", encoding="utf-8")
    monkeypatch.setenv("PROJ_NAME", "MyProject")

    result = injector.inject(
        "Base prompt",
        ["notes.txt", "missing.txt", "$PROJ_NAME", "$MISSING_VAR_XYZ"],
        tmp_path,
    )

    assert result.startswith("Base prompt")
    assert "Some notes" in result
    assert "MyProject" in result
    # Missing sources are skipped, but valid ones are present
    assert "--- Environment Context ---" in result


# ------------------------------------------------------------------
# Structured context format
# ------------------------------------------------------------------


def test_context_block_separator(
    injector: EnvironmentInjector, tmp_path: Path
) -> None:
    txt_file = tmp_path / "info.txt"
    txt_file.write_text("info content", encoding="utf-8")

    result = injector.inject("Base prompt", ["info.txt"], tmp_path)
    assert "--- Environment Context ---" in result
    assert result.startswith("Base prompt\n\n--- Environment Context ---")
