"""Concurrent collection of the pricing, security and quality stages."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pandas as pd

from src.api.openrouter_client import AsyncOpenRouterClient
from src.core.config import Settings
from src.evaluators.cost_analyzer import call_costs_to_dataframe
from src.evaluators.quality_judge import CollectResult


async def collect_stages(
    settings: Settings,
    models: list[str],
    client_factory: Callable[[Settings], Any],
    cost_stage: Callable[[AsyncOpenRouterClient], Awaitable[pd.DataFrame]],
    security_stage: Callable[[AsyncOpenRouterClient, list[str]], Awaitable[pd.DataFrame]],
    quality_stage: Callable[[AsyncOpenRouterClient, list[str]], Awaitable[CollectResult]],
) -> tuple[pd.DataFrame, pd.DataFrame, CollectResult, pd.DataFrame]:
    """Run existing injectable stages concurrently and collect actual call costs."""
    async with client_factory(settings) as client:
        pricing_df, security_df, collect_result = await asyncio.gather(
            cost_stage(client), security_stage(client, models), quality_stage(client, models)
        )
        actual_call_costs = call_costs_to_dataframe(client.call_costs)
    return pricing_df, security_df, collect_result, actual_call_costs


def enforce_collect_error_budget(
    collect_result: CollectResult,
    security_df: pd.DataFrame,
    *,
    model_count: int,
    max_quality_collection_error_rate: float,
    max_security_probe_error_rate: float,
) -> None:
    """Stop a run when transport/probe failures exceed configured thresholds."""
    if collect_result.prompt_count > 0 and model_count > 0 and collect_result.repetitions > 0:
        expected_quality_attempts = collect_result.prompt_count * model_count * collect_result.repetitions
    else:
        expected_quality_attempts = 0

    if expected_quality_attempts > 0:
        quality_error_rate = len(collect_result.collection_errors) / expected_quality_attempts
        if quality_error_rate > max_quality_collection_error_rate:
            raise ValueError(
                "[quality] Collection error budget exceeded: "
                f"{quality_error_rate:.2%} > {max_quality_collection_error_rate:.2%}. "
                "Fix upstream transport/provider instability before continuing."
            )

    if security_df.empty:
        raise ValueError("[security] Stage produced no rows; refusing to continue with an unvalidated security axis.")

    if "probe_count" in security_df.columns and "probe_error_count" in security_df.columns:
        probe_count = int(pd.to_numeric(security_df["probe_count"], errors="coerce").fillna(0).sum())
        probe_error_count = int(pd.to_numeric(security_df["probe_error_count"], errors="coerce").fillna(0).sum())
        if probe_count > 0:
            security_probe_error_rate = probe_error_count / probe_count
            if security_probe_error_rate > max_security_probe_error_rate:
                raise ValueError(
                    "[security] Probe error budget exceeded: "
                    f"{security_probe_error_rate:.2%} > {max_security_probe_error_rate:.2%}. "
                    "Fix probe/model transport failures before continuing."
                )
