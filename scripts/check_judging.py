"""Check a blind judging batch's score files before `make merge` and list what is left to judge.

For every judging part and every judge, a score file is ``ok`` only when it
covers exactly the expected (prompt_id, attempt, alias) responses, carries the
judge identifier declared in ``.github/agents/judge-<provider>.agent.md``, and
the Copilot Chat debug log of the run that wrote it shows the declared model
and no read of any file other than the part. VS Code silently runs a custom
agent on the chat's current model when its ``model:`` ID is unavailable, so
the debug log is the only evidence of which model actually judged.

For every part a judge still has to score, the script prints the exact
delegation message for ``@judge-coordinator`` to relay.

Usage
-----
    python scripts/check_judging.py                        # latest batch
    python scripts/check_judging.py --timestamp 20261029_171757
    python scripts/check_judging.py --quarantine           # move invalid score files aside
    python scripts/check_judging.py --skip-model-audit     # no Copilot debug logs available
    python scripts/check_judging.py --strict               # exit 2 while Phase 2 is incomplete

The last line is always ``STATUS: COMPLETE`` or ``STATUS: INCOMPLETE``. The
exit code is 0 in both cases, so that judges still to run do not look like a
failure; it is 1 when the check itself cannot run, and 2 for an incomplete
batch only with ``--strict``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

PROVIDERS = ("anthropic", "openai", "google")
INTERMEDIATE_DIR = Path("data/intermediate")
AGENTS_DIR = Path(".github/agents")
QUARANTINE_DIRNAME = "rejected_scores"
DEBUG_LOGS_ENV = "COPILOT_DEBUG_LOGS_DIR"

_QUALIFIED_MODEL = re.compile(r"^(?P<name>.+?)\s*\(copilot\)$", re.IGNORECASE)
_BATCH_NAME = re.compile(r"^judging_(\d{8}_\d{6})\.json$")
_PART_SUFFIX = re.compile(r"_part(\d{2})of(\d{2})$")
_READ_TOOLS = {"read_file", "grep_search", "file_search", "list_dir", "semantic_search"}
_WRITE_TOOLS = {
    "create_file",
    "apply_patch",
    "insert_edit_into_file",
    "replace_string_in_file",
    "multi_replace_string_in_file",
}

ResponseKey = tuple[int, int, str]


@dataclass(frozen=True)
class JudgeSpec:
    provider: str
    model: str  # model ID Copilot logs, e.g. claude-opus-5.5
    judge_id: str
    declared: str = ""  # qualified name in the agent's `model:` line, e.g. Claude Opus 5.5 (copilot)


@dataclass(frozen=True)
class Part:
    path: Path
    suffix: str
    expected: frozenset[ResponseKey]

    @property
    def label(self) -> str:
        match = _PART_SUFFIX.search(self.suffix)
        return f"part {match.group(1)}/{match.group(2)}" if match else "batch"


@dataclass
class JudgeRun:
    path: Path
    started_ms: int
    message: str = ""
    models: set[str] = field(default_factory=set)
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)


@dataclass
class Status:
    part: Part
    spec: JudgeSpec
    score_path: Path
    state: str  # ok | missing | invalid | unverified
    problems: list[str] = field(default_factory=list)


def is_qualified_model(name: str) -> bool:
    return _QUALIFIED_MODEL.match(name) is not None


def logged_model_id(qualified_name: str) -> str:
    """The model ID Copilot logs for a picker name: ``Claude Opus 5.5 (copilot)`` → ``claude-opus-5.5``."""
    match = _QUALIFIED_MODEL.match(qualified_name)
    name = match.group("name") if match else qualified_name
    return re.sub(r"\s+", "-", name.strip()).lower()


def judge_spec(provider: str, agents_dir: Path | None = None) -> JudgeSpec:
    """Read the declared model and judge identifier from a judge agent file.

    VS Code resolves ``model:`` only by qualified display name, such as
    ``Claude Opus 5.5 (copilot)``; a bare model ID silently falls back to the
    chat's current model, so it is refused here.
    """
    text = ((agents_dir or AGENTS_DIR) / f"judge-{provider}.agent.md").read_text(encoding="utf-8")
    model_line = re.search(r"^model:\s*(.+)$", text, re.MULTILINE)
    judge_id = re.search(r'"judge":\s*"([^"]+)"', text)
    if model_line is None or judge_id is None:
        raise ValueError(f"judge-{provider}.agent.md must declare `model:` and an output `judge` identifier")
    declared = [entry.strip(" '\"") for entry in model_line.group(1).strip("[] ").split(",") if entry.strip(" '\"")]
    if not declared or not is_qualified_model(declared[0]):
        raise ValueError(
            f"judge-{provider}.agent.md declares `model: {model_line.group(1).strip()}`; use the qualified name "
            "the Copilot model picker shows, e.g. `Claude Opus 5.5 (copilot)`: VS Code silently runs a bare ID "
            "on the chat's current model"
        )
    return JudgeSpec(provider, logged_model_id(declared[0]), judge_id.group(1), declared[0])


def latest_timestamp(intermediate_dir: Path) -> str | None:
    stamps = sorted(m.group(1) for p in intermediate_dir.glob("judging_*.json") if (m := _BATCH_NAME.match(p.name)))
    return stamps[-1] if stamps else None


def _expected_keys(payload: Mapping[str, object]) -> frozenset[ResponseKey]:
    keys: set[ResponseKey] = set()
    items = payload.get("pending_judgments") or []
    for item in items if isinstance(items, list) else []:
        responses = item.get("responses") or {}
        for alias, text in responses.items():
            if isinstance(text, str) and text.strip():
                keys.add((int(item["prompt_id"]), int(item.get("attempt", 0)), str(alias)))
    return frozenset(keys)


def batch_parts(intermediate_dir: Path, timestamp: str) -> list[Part]:
    """The part files of a split batch, or the single batch file when it is not split."""
    paths = sorted(intermediate_dir.glob(f"judging_{timestamp}_part*of*.json"))
    if not paths:
        paths = [intermediate_dir / f"judging_{timestamp}.json"]
    parts = []
    for path in paths:
        suffix = path.stem.removeprefix(f"judging_{timestamp}")
        parts.append(Part(path, suffix, _expected_keys(json.loads(path.read_text(encoding="utf-8")))))
    return parts


def score_path(intermediate_dir: Path, timestamp: str, provider: str, part: Part) -> Path:
    return intermediate_dir / f"scores_{timestamp}_{provider}{part.suffix}.json"


def validate_scores(payload: object, spec: JudgeSpec, timestamp: str, expected: frozenset[ResponseKey]) -> list[str]:
    """Structural problems of one judge's score payload for one part (empty when valid)."""
    if not isinstance(payload, dict):
        return ["payload is not a JSON object"]
    problems = []
    if payload.get("judge") != spec.judge_id:
        problems.append(f"judge is {payload.get('judge')!r}, expected {spec.judge_id!r}")
    if payload.get("timestamp") != timestamp:
        problems.append(f"timestamp is {payload.get('timestamp')!r}, expected {timestamp!r}")
    scores = payload.get("scores")
    if not isinstance(scores, list):
        return [*problems, "`scores` is not a list"]
    seen: set[ResponseKey] = set()
    duplicates: set[ResponseKey] = set()
    for item in scores:
        try:
            prompt_id, attempt = int(item["prompt_id"]), int(item.get("attempt", 0))
            judgments = list(item["judgments"])
        except (KeyError, TypeError, ValueError):
            problems.append(f"malformed score item {str(item)[:80]}")
            continue
        for judgment in judgments:
            alias = judgment.get("alias") if isinstance(judgment, dict) else None
            score = judgment.get("score") if isinstance(judgment, dict) else None
            key = (prompt_id, attempt, str(alias))
            if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
                problems.append(f"score {score!r} outside 1–5 for prompt {prompt_id}, attempt {attempt}, alias {alias}")
            reasoning = judgment.get("reasoning") if isinstance(judgment, dict) else None
            if not isinstance(reasoning, str) or not reasoning.strip():
                problems.append(f"empty reasoning for prompt {prompt_id}, attempt {attempt}, alias {alias}")
            elif "[DRY-RUN]" in reasoning:
                problems.append(f"synthetic dry-run reasoning for prompt {prompt_id}, attempt {attempt}, alias {alias}")
            (duplicates if key in seen else seen).add(key)
    for label, keys in (
        ("missing", expected - seen),
        ("unexpected", seen - expected),
        ("scored twice", duplicates),
    ):
        if keys:
            listed = ", ".join(f"prompt {p} attempt {a} alias {s}" for p, a, s in sorted(keys)[:5])
            problems.append(f"{len(keys)} {label}: {listed}{' …' if len(keys) > 5 else ''}")
    return problems


def debug_log_dirs(environ: Mapping[str, str] = os.environ, home: Path | None = None) -> list[Path]:
    """Copilot Chat debug-log folders of every local VS Code workspace storage."""
    if environ.get(DEBUG_LOGS_ENV):
        return [Path(entry) for entry in environ[DEBUG_LOGS_ENV].split(os.pathsep) if entry]
    home = home or Path.home()
    roots = [home / ".vscode-server/data/User/workspaceStorage"]
    for product in ("Code", "Code - Insiders"):
        roots += [
            home / "Library/Application Support" / product / "User/workspaceStorage",
            home / ".config" / product / "User/workspaceStorage",
        ]
        if environ.get("APPDATA"):
            roots.append(Path(environ["APPDATA"]) / product / "User/workspaceStorage")
    return [path for root in roots if root.is_dir() for path in root.glob("*/GitHub.copilot-chat/debug-logs")]


def _tool_paths(attrs: Mapping[str, object]) -> list[str]:
    try:
        args = json.loads(str(attrs.get("args", "{}")))
    except json.JSONDecodeError:
        return [str(attrs.get("args", ""))]
    if not isinstance(args, dict):
        return []
    return [str(args[key]) for key in ("filePath", "path", "query", "includePattern") if args.get(key)]


def parse_judge_run(path: Path) -> JudgeRun:
    """Model, delegation message and file accesses of one judge subagent debug log."""
    run = JudgeRun(path=path, started_ms=0)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        attrs = record.get("attrs") if isinstance(record.get("attrs"), dict) else {}
        kind, name = record.get("type"), record.get("name")
        if kind == "session_start":
            run.started_ms = int(record.get("ts", 0))
        elif kind == "user_message" and not run.message:
            run.message = str(attrs.get("content", ""))
        elif kind == "llm_request" and attrs.get("model"):
            run.models.add(str(attrs["model"]))
        elif kind == "tool_call" and name in _READ_TOOLS:
            run.reads += _tool_paths(attrs)
        elif kind == "tool_call" and name in _WRITE_TOOLS:
            run.writes += _tool_paths(attrs)
    return run


def judge_runs(log_dirs: Iterable[Path], provider: str, timestamp: str) -> list[JudgeRun]:
    runs = []
    for log_dir in log_dirs:
        for path in log_dir.glob(f"*/runSubagent-judge-{provider}-*.jsonl"):
            run = parse_judge_run(path)
            if timestamp in run.message:
                runs.append(run)
    return sorted(runs, key=lambda run: run.started_ms)


def _run_for(runs: list[JudgeRun], part: Part, scores: Path) -> JudgeRun | None:
    """The run that wrote *scores*: the last one writing that path, else the last delegated this part before it."""
    written_at = scores.stat().st_mtime * 1000
    writers = [run for run in runs if any(Path(write).name == scores.name for write in run.writes)]
    if writers:
        return writers[-1]
    match = _PART_SUFFIX.search(part.suffix)
    legacy_marker = f'"part": {int(match.group(1))},' if match else ""

    def delegated(run: JudgeRun) -> bool:
        return part.path.name in run.message or bool(legacy_marker and legacy_marker in run.message)

    earlier = [run for run in runs if delegated(run) and run.started_ms <= written_at]
    return earlier[-1] if earlier else None


def audit_run(run: JudgeRun, spec: JudgeSpec, part: Part) -> list[str]:
    problems = []
    if run.models != {spec.model}:
        problems.append(f"ran on {', '.join(sorted(run.models)) or 'no model'}, expected {spec.model}")
    foreign = sorted({read for read in run.reads if Path(read).name != part.path.name})
    if foreign:
        problems.append(f"read files other than its part: {', '.join(foreign[:3])}")
    return problems


def check_batch(
    intermediate_dir: Path,
    timestamp: str,
    specs: list[JudgeSpec],
    log_dirs: list[Path] | None,
) -> list[Status]:
    """Status of every (part, judge) pair; *log_dirs* ``None`` skips the model audit."""
    statuses = []
    runs = {spec.provider: judge_runs(log_dirs or [], spec.provider, timestamp) for spec in specs}
    for part in batch_parts(intermediate_dir, timestamp):
        for spec in specs:
            path = score_path(intermediate_dir, timestamp, spec.provider, part)
            if not path.exists():
                statuses.append(Status(part, spec, path, "missing"))
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                statuses.append(Status(part, spec, path, "invalid", [f"invalid JSON: {exc}"]))
                continue
            problems = validate_scores(payload, spec, timestamp, part.expected)
            if not problems and log_dirs is not None:
                run = _run_for(runs[spec.provider], part, path)
                if run is None:
                    statuses.append(Status(part, spec, path, "unverified", ["no Copilot debug log for this run"]))
                    continue
                problems = audit_run(run, spec, part)
            statuses.append(Status(part, spec, path, "invalid" if problems else "ok", problems))
    return statuses


def delegation_message(status: Status, timestamp: str) -> str:
    return (
        f"Batch timestamp: `{timestamp}`. Read `{status.part.path.as_posix()}` in a single read_file call, "
        "judge every item according to your instructions, and write your scores payload with create_file "
        f"to `{status.score_path.as_posix()}`. Read and write no other file."
    )


def quarantine(path: Path) -> Path:
    target_dir = path.parent / QUARANTINE_DIRNAME
    target_dir.mkdir(exist_ok=True)
    target = target_dir / path.name
    index = 1
    while target.exists():
        target = target_dir / f"{path.stem}.{index}{path.suffix}"
        index += 1
    shutil.move(str(path), target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timestamp", default=None, help="Batch timestamp (default: latest judging_<ts>.json)")
    parser.add_argument("--quarantine", action="store_true", help=f"Move invalid score files to {QUARANTINE_DIRNAME}/")
    parser.add_argument(
        "--skip-model-audit", action="store_true", help="Do not check the judge model in Copilot debug logs"
    )
    parser.add_argument("--strict", action="store_true", help="Exit with code 2 while the batch is incomplete")
    args = parser.parse_args(argv)

    timestamp = args.timestamp or latest_timestamp(INTERMEDIATE_DIR)
    if timestamp is None or not (INTERMEDIATE_DIR / f"judging_{timestamp}.json").exists():
        print("No judging_<ts>.json batch found. Run `make collect` first.", file=sys.stderr)
        return 1
    specs = [judge_spec(provider) for provider in PROVIDERS]
    log_dirs = None if args.skip_model_audit else debug_log_dirs()
    if log_dirs == []:
        print(
            f"No Copilot Chat debug logs found; set {DEBUG_LOGS_ENV} or pass --skip-model-audit "
            "(the judge model then stays unverified).",
            file=sys.stderr,
        )
        return 1
    statuses = check_batch(INTERMEDIATE_DIR, timestamp, specs, log_dirs)

    print(f"Batch {timestamp} — judges: " + ", ".join(f"{s.provider}={s.model}" for s in specs))
    for status in statuses:
        detail = f" — {'; '.join(status.problems)}" if status.problems else ""
        print(f"  {status.part.label:<12} {status.spec.provider:<10} {status.state.upper():<10}{detail}")
        if status.state == "invalid" and args.quarantine:
            print(f"    moved to {quarantine(status.score_path)}")
            status.state = "missing"

    todo = [status for status in statuses if status.state == "missing"]
    blocked = [status for status in statuses if status.state in {"invalid", "unverified"}]
    parts = {status.part.path for status in statuses}
    done = {s.part.path for s in statuses} - {s.part.path for s in statuses if s.state != "ok"}
    print(f"\n{len(done)}/{len(parts)} parts judged and verified.")
    if todo:
        print(f"\nTODO — {len(todo)} delegation(s) to relay verbatim:")
        for status in todo:
            print(f"TODO judge-{status.spec.provider} | {delegation_message(status, timestamp)}")
    if blocked:
        print(
            f"\n{len(blocked)} score file(s) invalid or unverified. Rerun with --quarantine to move invalid ones "
            "aside and judge them again; an unverified file needs its Copilot debug log or --skip-model-audit."
        )
    complete = not todo and not blocked
    print(f"\nSTATUS: {'COMPLETE — run `make merge`' if complete else 'INCOMPLETE — do not run `make merge`'}")
    return 2 if args.strict and not complete else 0


if __name__ == "__main__":
    raise SystemExit(main())
