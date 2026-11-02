"""The committed quality suite v3, its catalog and the probe set are exactly what their build scripts produce."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", params=["build_quality_suite_v3", "build_security_probes"])
def builder(request: pytest.FixtureRequest) -> ModuleType:
    return _load(request.param)


def test_committed_files_match_their_build_script(builder: ModuleType) -> None:
    for path, text in builder.OUTPUTS.items():
        assert path.read_text(encoding="utf-8") == text, f"{path.name} was edited by hand: change the build script"


def test_check_mode_reports_a_hand_edited_file(
    builder: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    edited = tmp_path / "edited.json"
    edited.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setattr(builder, "OUTPUTS", {edited: "[1]\n"})

    assert builder.main(["--check"]) == 1
    assert "OUT OF DATE: edited.json" in capsys.readouterr().out
    assert edited.read_text(encoding="utf-8") == "[]\n"
