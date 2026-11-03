"""Shared pytest fixtures."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from src.core import model_selector


@pytest.fixture(autouse=True)
def _isolate_saved_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep `make select` tests from overwriting the user's real saved selection."""
    monkeypatch.setattr(
        "src.main.save_selection",
        partial(model_selector.save_selection, path=tmp_path / "model_selection.json"),
    )


@pytest.fixture(autouse=True)
def _dummy_openrouter_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a fake OpenRouter key, so tests never depend on a local `.env` nor reach the real API.

    Without it the suite passed locally, where `.env` holds a key, and failed in CI, which has none.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-not-a-real-key")
