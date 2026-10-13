"""Argument parsing and per-command settings for the pipeline entry point."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from typing import Any

from src.core.config import Settings
from src.core.model_presets import resolve_models_arg


def build_arg_parser(
    security_modes: Mapping[str, object], quality_suites: Mapping[str, object]
) -> argparse.ArgumentParser:
    """Build the legacy CLI parser, including its free-form subcommand."""
    parser = argparse.ArgumentParser(prog="python -m src.main", description="OpenRouter LLM evaluation pipeline.")
    parser.add_argument(
        "subcommand",
        nargs="?",
        default="collect",
        help="collect|run|merge|dry-run|verify|models (default: collect)",
    )
    parser.add_argument(
        "--models",
        default=None,
        help=(
            "Model-set preset name (see 'python -m src.main models') or a "
            "comma-separated list of explicit model IDs. Overrides "
            "TARGET_MODELS for this run only. Ignored by merge/models."
        ),
    )
    parser.add_argument(
        "--security",
        choices=sorted(security_modes),
        default=None,
        help=("Security probe set for this run only. Overrides SECURITY_MODE. Ignored by merge/models."),
    )
    parser.add_argument(
        "--quality-suite",
        choices=sorted(quality_suites),
        default=None,
        help="Quality prompt suite and catalog for this run only. Overrides QUALITY_SUITE. Use it for merge too.",
    )
    parser.add_argument("--paid-only", action="store_true", help="Keep only paid models for 'select'.")
    parser.add_argument("--free-only", action="store_true", help="Keep only zero-priced/free-tier models for 'select'.")
    parser.add_argument("--max-input-price", type=float, default=None, help="Maximum input price per 1M tokens.")
    parser.add_argument("--max-output-price", type=float, default=None, help="Maximum output price per 1M tokens.")
    parser.add_argument("--min-context", type=int, default=None, help="Minimum context length in tokens.")
    parser.add_argument(
        "--limit",
        type=int,
        default=6,
        help="Default maximum models for 'select' (default: 6; enter another value to change it).",
    )
    return parser


def settings_override_from_args(args: argparse.Namespace, get_settings: Callable[[], Settings]) -> Settings | None:
    """Resolve settings at call time so façade-level configuration stays patchable."""
    overrides: dict[str, Any] = {}
    if args.models:
        resolved = resolve_models_arg(args.models, strict=True)
        overrides["target_models"] = ",".join(resolved)
    if args.security:
        overrides["security_mode"] = args.security
        overrides["security_probes_path"] = None
    if args.quality_suite:
        overrides["quality_suite"] = args.quality_suite
    if not overrides:
        return None
    return get_settings().model_copy(update=overrides)
