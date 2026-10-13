"""Opt-in, separate dialogue screen; offline unless --live is explicitly supplied."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from src.api.openrouter_client import AsyncOpenRouterClient
from src.core.config import get_settings
from src.core.model_presets import resolve_models_arg
from src.evaluators.dialogue_quality import DialogueCase, load_dialogue_cases, run_dialogue_suite


async def run_dialogue_command(*, live: bool, models_arg: str | None, output_dir: Path) -> Path:
    """Run a bounded suite and write dedicated, non-legacy CSV/JSON artifacts."""
    cases, suite_id = load_dialogue_cases()
    if live:
        settings = get_settings()
        models = resolve_models_arg(models_arg, strict=True) if models_arg else settings.target_models_list
        async with AsyncOpenRouterClient(settings) as client:

            async def complete(model: str, case: DialogueCase, messages: list[dict[str, str]]) -> str:
                response = await client.chat_completion(
                    model=model,
                    messages=messages,
                    usage_context="dialogue_quality",
                    scenario_id=case.scenario_id,
                    turn_index=(len(messages) - 2) // 2,
                    max_tokens=512,
                    temperature=0,
                )
                return response.choices[0].message.content or ""

            details, summary = await run_dialogue_suite(cases, suite_id, models, complete)
    else:
        models = resolve_models_arg(models_arg, strict=True) if models_arg else ["offline-demo"]

        async def complete(model: str, case: DialogueCase, messages: list[dict[str, str]]) -> str:
            del model
            return case.dry_run_responses[(len(messages) - 2) // 2]

        details, summary = await run_dialogue_suite(cases, suite_id, models, complete)

    evidence_source = "openrouter" if live else "synthetic_offline"
    details["evidence_source"] = evidence_source
    summary["evidence_source"] = evidence_source
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / f"dialogue_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    for label, frame in (("details", details), ("summary", summary)):
        frame.to_csv(f"{stem}_{label}.csv", index=False)
        frame.to_json(f"{stem}_{label}.json", orient="records", indent=2)
    return stem


def main() -> None:
    """Parse opt-in dialogue arguments without altering the existing pipeline CLI."""
    parser = argparse.ArgumentParser(description="Separate two-turn dialogue quality screen (offline by default).")
    parser.add_argument("--live", action="store_true", help="Explicitly enable paid OpenRouter completions.")
    parser.add_argument("--models", default=None, help="Model IDs or a preset; offline defaults to offline-demo.")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    output_dir = args.output_dir or (Path("results/dialogue") if args.live else Path("data/dry_run/dialogue"))
    stem = asyncio.run(run_dialogue_command(live=args.live, models_arg=args.models, output_dir=output_dir))
    print(f"{'LIVE' if args.live else 'SYNTHETIC OFFLINE'} dialogue evidence: {stem}_{{details,summary}}.{{csv,json}}")


if __name__ == "__main__":
    main()
