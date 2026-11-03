"""Validate the repository's Conventional Commit header rules."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_TYPES = ("feat", "fix", "chore", "docs", "test", "refactor", "perf", "ci", "build", "revert")
_HEADER = re.compile(rf"^(?:{'|'.join(_TYPES)})(?:\([a-z0-9][a-z0-9._/-]*\))?: (?P<subject>\S(?:.*\S)?)$")
_MAX_HEADER_LENGTH = 72


def validate_commit_message(message: str) -> list[str]:
    """Return all violations in the first non-empty, non-comment message line."""
    header = next(
        (line for line in message.splitlines() if line.strip() and not line.lstrip().startswith("#")),
        "",
    )
    if not header:
        return ["commit message header is empty"]

    errors: list[str] = []
    if len(header) > _MAX_HEADER_LENGTH:
        errors.append(f"header is {len(header)} characters; maximum is {_MAX_HEADER_LENGTH}")
    match = _HEADER.fullmatch(header)
    if match is None:
        errors.append("use <allowed-type>(optional-scope): <lower-case subject>")
        return errors

    subject = match.group("subject")
    if subject != subject.lower():
        errors.append("subject must be lower-case")
    if subject.endswith("."):
        errors.append("subject must not end with a period")
    return errors


def main() -> int:
    """Read the commit message path passed by Git and return a hook status."""
    if len(sys.argv) != 2:
        print("Expected the commit-message file path.", file=sys.stderr)
        return 2
    try:
        message = Path(sys.argv[1]).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read commit message: {exc}", file=sys.stderr)
        return 2

    errors = validate_commit_message(message)
    if errors:
        print("Invalid Conventional Commit message:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
