"""Pilot candidate quality items on real models before they enter the suite (PAID with --live).

Candidates come from ``data/prompts/quality_candidates_v3.json``, written by
``scripts/build_quality_suite_v3.py``. With ``--live``, the script first checks
that the gateway forwards every candidate unchanged, then sends each one to
every model ``--attempts`` times and scores the answers with the suite's
deterministic checks. It prints, per item, the mean score of every model and
how many models miss it: an item that no model misses is ``saturated`` and
does not enter the suite. Without ``--live`` it only lists the candidates.

Usage
-----
    python scripts/pilot_quality_items.py                          # offline: list the candidates
    python scripts/pilot_quality_items.py --live --models selection
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.api.openrouter_client import AsyncOpenRouterClient, OpenRouterError, completion_text  # noqa: E402
from src.core.config import get_settings  # noqa: E402
from src.core.model_presets import resolve_models_arg  # noqa: E402
from src.evaluators.deterministic_eval import CHECKS  # noqa: E402
from src.evaluators.prompt_delivery import audit_prompt_delivery, prompts_to_audit, rewritten_words  # noqa: E402

CANDIDATES_PATH = ROOT / "data/prompts/quality_candidates_v3.json"
OUTPUT_DIR = ROOT / "results/pilot"


def load_candidates(path: Path = CANDIDATES_PATH) -> list[dict]:
    """Load the candidates, refusing any that needs the judge panel: a pilot scores answers itself."""
    candidates = json.loads(path.read_text(encoding="utf-8"))
    judged = [item["item_id"] for item in candidates if item["category"] not in CHECKS]
    if judged:
        raise ValueError(f"Candidates without a deterministic check cannot be piloted: {judged}")
    return candidates


def item_status(scores: pd.Series) -> str:
    """``saturated`` when every model scores 5, else which models miss the item."""
    missed = scores[scores < 5]
    if missed.empty:
        return "saturated"
    return f"missed by {len(missed)}: " + ", ".join(model.split("/")[-1] for model in missed.index)


def summarize(details: pd.DataFrame) -> pd.DataFrame:
    """One row per item: each model's mean score over its attempts, and the item status."""
    table = details.pivot_table(index="item_id", columns="model", values="score", aggfunc="mean").round(2)
    table["status"] = table.apply(item_status, axis=1)
    return table


async def pilot(candidates: list[dict], models: list[str], attempts: int) -> pd.DataFrame:
    """Audit delivery, collect every attempt and score it; return one row per answer."""
    settings = get_settings()
    async with AsyncOpenRouterClient(settings) as client:
        audit = await audit_prompt_delivery(
            client, models, prompts_to_audit([(item["item_id"], item["prompt"]) for item in candidates], [])
        )
        if audit.altered_items:
            sent = {item["item_id"]: item["prompt"] for item in candidates}
            altered = "\n".join(
                f"  {name}: {rewritten_words(sent[name], text)}" for name, text in sorted(audit.altered_items.items())
            )
            raise SystemExit(f"The gateway rewrites these candidates; reword them before piloting:\n{altered}")

        async def answer(item: dict, model: str, attempt: int) -> dict[str, object]:
            try:
                completion = await client.chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": item["prompt"]}],
                    usage_context="quality_pilot",
                    temperature=0,
                    max_tokens=settings.quality_max_tokens,
                )
                response, _ = completion_text(completion, model)
            except OpenRouterError as exc:
                return {"item_id": item["item_id"], "model": model, "attempt": attempt, "error": str(exc)}
            result = CHECKS[item["category"]].run(item["prompt"], response, {**item, "execute_code": True})
            return {
                "item_id": item["item_id"],
                "model": model,
                "attempt": attempt,
                "score": result.score,
                "format_score": result.format_score,
                "reason": result.reason,
                "response": response,
            }

        rows = await asyncio.gather(
            *(answer(item, model, attempt) for item in candidates for model in models for attempt in range(attempts))
        )
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="Explicitly enable paid OpenRouter completions")
    parser.add_argument("--models", help="Model preset, 'selection' or comma-separated IDs (default: TARGET_MODELS)")
    parser.add_argument("--attempts", type=int, default=3, help="Attempts per item and model (default: 3)")
    parser.add_argument("--items", help="Comma-separated item IDs to pilot (default: every candidate)")
    args = parser.parse_args(argv)

    candidates = load_candidates()
    if args.items:
        wanted = {item_id.strip() for item_id in args.items.split(",")}
        unknown = wanted - {item["item_id"] for item in candidates}
        if unknown:
            parser.error(f"unknown candidate item(s): {', '.join(sorted(unknown))}")
        candidates = [item for item in candidates if item["item_id"] in wanted]
    if not args.live:
        for item in candidates:
            print(f"{item['item_id']:28s} {item['construct']}")
        print(f"{len(candidates)} candidates; add --live to pilot them (paid).")
        return 0

    models = resolve_models_arg(args.models, strict=True) if args.models else get_settings().target_models_list
    details = asyncio.run(pilot(candidates, models, args.attempts))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = OUTPUT_DIR / f"pilot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    details.to_csv(f"{stem}_details.csv", index=False)
    errors = int(details["error"].notna().sum()) if "error" in details.columns else 0
    summary = summarize(details.dropna(subset=["score"]))
    summary.to_csv(f"{stem}_summary.csv")
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print(summary.to_string())
    print(f"Wrote {stem}_details.csv and {stem}_summary.csv; {errors} collection error(s) left out of the scores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
