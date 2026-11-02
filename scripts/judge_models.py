"""Check, before judging, that every judge agent's model resolves on your Copilot plan; switch a judge in one command.

VS Code silently runs a custom agent on the chat's current model when its
``model:`` line does not resolve, which wastes a whole judging round. This
preflight reads the model list Copilot Chat records in its local debug logs
(``models.json``) and, for each judge agent, reports whether the declared
model is enabled, whether it is also benchmarked in the saved selection
(self-judging), and whether the judge identifier still matches the model. When
a model disappears from the plan it lists the enabled candidates of the same
vendor; ``--set`` then rewrites the agent's ``model:`` line and judge
identifier together.

Usage
-----
    python scripts/judge_models.py                                     # preflight
    python scripts/judge_models.py --set "anthropic=Claude Sonnet 5 (copilot)"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import check_judging  # noqa: E402
from src.core.model_selector import SELECTION_PATH  # noqa: E402

VENDORS = {"anthropic": "Anthropic", "openai": "OpenAI", "google": "Google"}


@dataclass(frozen=True)
class CopilotModel:
    id: str
    name: str
    vendor: str

    @property
    def qualified(self) -> str:
        return f"{self.name} (copilot)"


def expected_judge_id(model_id: str, provider: str) -> str:
    """Judge identifier convention: ``copilot-<model id without punctuation>-<provider>``."""
    return f"copilot-{re.sub(r'[^a-z0-9]', '', model_id.lower())}-{provider}"


def enabled_models(log_dirs: Iterable[Path]) -> list[CopilotModel] | None:
    """Chat models enabled on the plan, from the most recent Copilot ``models.json``; ``None`` when none is found."""
    files = [path for log_dir in log_dirs for path in log_dir.glob("*/models.json")]
    if not files:
        return None
    entries = json.loads(max(files, key=lambda path: path.stat().st_mtime).read_text(encoding="utf-8"))
    models = []
    for entry in entries if isinstance(entries, list) else []:
        policy = entry.get("policy")
        state = policy.get("state") if isinstance(policy, dict) else policy
        if entry.get("model_picker_enabled") and state == "enabled":
            models.append(CopilotModel(str(entry["id"]), str(entry["name"]), str(entry.get("vendor", ""))))
    return models


def benchmarked_ids(selection_path: Path = SELECTION_PATH) -> set[str]:
    """Model IDs of the saved selection, without their OpenRouter provider prefix."""
    try:
        slugs = json.loads(selection_path.read_text(encoding="utf-8")).get("models", [])
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(slug).split("/", 1)[-1].split(":", 1)[0].lower() for slug in slugs}


def preflight(
    agents_dir: Path, models: list[CopilotModel] | None, benchmarked: set[str]
) -> tuple[list[str], list[str]]:
    """Report lines and blocking errors for the three judge agents."""
    lines: list[str] = []
    errors: list[str] = []
    by_name = {model.qualified.lower(): model for model in models or []}
    for provider in check_judging.PROVIDERS:
        try:
            spec = check_judging.judge_spec(provider, agents_dir)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        status = "OK"
        notes = []
        name = spec.declared
        if models is not None and name.lower() not in by_name:
            status = "NOT ON PLAN"
            candidates = [m.qualified for m in models if m.vendor.lower() == VENDORS[provider].lower()]
            errors.append(
                f"judge-{provider}: `{name}` is not enabled on your Copilot plan; VS Code would run it on the "
                f"chat's model. Enabled {VENDORS[provider]} models: {', '.join(candidates) or 'none'}"
            )
        if spec.judge_id != expected_judge_id(spec.model, provider):
            status = "STALE ID" if status == "OK" else status
            errors.append(
                f"judge-{provider}: identifier `{spec.judge_id}` does not match `{name}`; expected "
                f"`{expected_judge_id(spec.model, provider)}` (use --set to change both)"
            )
        if spec.model in benchmarked:
            notes.append("also benchmarked: scores itself, see the outcome without the own-provider judge")
        lines.append(f"  judge-{provider:<10} {name:<32} {status:<12}{' — ' + '; '.join(notes) if notes else ''}")
    return lines, errors


def set_judge_model(agents_dir: Path, provider: str, qualified_name: str) -> Path:
    """Rewrite one judge agent's ``model:`` line and judge identifier for *qualified_name*."""
    path = agents_dir / f"judge-{provider}.agent.md"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^model: .*$", f"model: {qualified_name}", text, count=1, flags=re.M)
    model_id = check_judging.logged_model_id(qualified_name)
    text = re.sub(r'"judge":\s*"[^"]+"', f'"judge": "{expected_judge_id(model_id, provider)}"', text, count=1)
    label = qualified_name.rsplit("(", 1)[0].strip()
    text = re.sub(r"using .+? \((\w+)\) as LLM-as-a-Judge", rf"using {label} (\1) as LLM-as-a-Judge", text, count=1)
    text = re.sub(r"You are running as \*\*.+? \((\w+)\)\*\*", rf"You are running as **{label} (\1)**", text, count=1)
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", default=None, metavar="PROVIDER=NAME (copilot)", help="Switch one judge's model")
    args = parser.parse_args(argv)
    agents_dir = check_judging.AGENTS_DIR

    if args.set:
        provider, _, name = args.set.partition("=")
        if provider not in check_judging.PROVIDERS or not check_judging.is_qualified_model(name.strip()):
            print('--set expects PROVIDER="<picker name> (copilot)", e.g. anthropic="Claude Opus 5.5 (copilot)"')
            return 1
        print(f"Updated {set_judge_model(agents_dir, provider, name.strip())}")

    models = enabled_models(check_judging.debug_log_dirs())
    lines, errors = preflight(agents_dir, models, benchmarked_ids())
    print("Judge models" + (" (plan not checked: no Copilot models.json found)" if models is None else ""))
    print("\n".join(lines))
    for error in errors:
        print(f"ERROR {error}")
    print(f"\nSTATUS: {'READY' if not errors else 'BLOCKED — fix the judge agents before judging'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
