"""Split an existing blind judging batch into parts the judge coordinator can forward whole.

New collections are split automatically by ``make collect``; use this for a
batch collected before that, or to re-split with another part size.

Usage
-----
    python scripts/split_judging_batch.py                      # latest judging_<ts>.json
    python scripts/split_judging_batch.py --judging data/intermediate/judging_<ts>.json
    python scripts/split_judging_batch.py --replace            # re-split before any part is scored
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline_artifacts import (  # noqa: E402
    JUDGING_PART_MAX_CHARS,
    JUDGING_PART_MAX_RESPONSES,
    write_judging_parts,
)

_INTERMEDIATE_DIR = Path("data/intermediate")
_BATCH_NAME = re.compile(r"^judging_\d{8}_\d{6}\.json$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--judging", type=Path, default=None, help="Blind judging batch (default: latest)")
    parser.add_argument("--max-chars", type=int, default=JUDGING_PART_MAX_CHARS, help="Largest part size")
    parser.add_argument("--max-responses", type=int, default=JUDGING_PART_MAX_RESPONSES, help="Most responses per part")
    parser.add_argument(
        "--replace", action="store_true", help="Replace existing part files when no part has been scored yet"
    )
    args = parser.parse_args(argv)

    batches = sorted(path for path in _INTERMEDIATE_DIR.glob("judging_*.json") if _BATCH_NAME.match(path.name))
    judging_path = args.judging or (batches[-1] if batches else None)
    if judging_path is None or not judging_path.exists():
        print("No judging_<ts>.json batch found. Run `make collect` first.", file=sys.stderr)
        return 1
    stale = sorted(judging_path.parent.glob(f"{judging_path.stem}_part*.json"))
    if stale and not args.replace:
        print(
            f"{judging_path.name} is already split ({len(stale)} part files). Pass --replace to re-split.",
            file=sys.stderr,
        )
        return 1
    timestamp = judging_path.stem.removeprefix("judging_")
    scored = sorted(judging_path.parent.glob(f"scores_{timestamp}_*part*.json"))
    if stale and scored:
        print(
            f"Parts of {judging_path.name} are already scored ({len(scored)} score files); "
            "re-splitting would orphan them. Finish judging the current parts.",
            file=sys.stderr,
        )
        return 1
    for part in stale:
        part.unlink()
    parts = write_judging_parts(
        json.loads(judging_path.read_text(encoding="utf-8")),
        judging_path.parent,
        args.max_chars,
        args.max_responses,
    )
    if not parts:
        print(f"{judging_path.name} already fits in one part; judge it as is.")
        return 0
    for part in parts:
        print(f"Wrote {part}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
