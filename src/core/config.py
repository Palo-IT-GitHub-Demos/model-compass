"""Centralised, type-safe configuration loaded from environment variables.

Usage:
    from src.core.config import get_settings

    settings = get_settings()
    api_key = settings.openrouter_api_key.get_secret_value()
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.model_presets import resolve_models_arg


class Settings(BaseSettings):
    """Application settings resolved from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,
        populate_by_name=True,
        extra="ignore",  # Silently drop unknown env vars (e.g. PORT, APP_ENV).
    )

    # ── OpenRouter ─────────────────────────────────────────────────────────────
    openrouter_api_key: SecretStr
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── Evaluation ─────────────────────────────────────────────────────────────
    # Note: le juge LLM est désormais un agent Copilot (@judge-anthropic,
    # @judge-openai, @judge-google). JUDGE_MODEL n'est plus utilisé.

    # Stored as a comma-separated string so pydantic-settings never attempts to
    # JSON-decode it.  Exposed as ``list[str]`` via the computed field below.
    # ⚠️  Si TARGET_MODELS est défini dans .env, il écrase ce défaut.
    #     Pour tester avec exactement ces 3 modèles, ne pas définir
    #     TARGET_MODELS dans .env.
    target_models: str = Field(
        default=("nvidia/nemotron-3-ultra-550b-a55b:free,google/gemma-4-31b-it:free,openai/gpt-oss-20b:free")
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def target_models_list(self) -> list[str]:
        """Parse ``TARGET_MODELS`` into a list, expanding a bare preset name.

        Accepts a JSON array, a comma-separated model list, or (new) a single
        named preset (see ``src.core.model_presets.MODEL_PRESETS``) such as
        ``TARGET_MODELS=paid_flagship`` — resolved via ``resolve_models_arg``.
        """
        raw = self.target_models.strip()
        if raw.startswith("["):
            import json  # noqa: PLC0415

            try:
                decoded: Any = json.loads(raw)
                if isinstance(decoded, list) and all(isinstance(item, str) for item in decoded):
                    return decoded
            except Exception:  # noqa: BLE001
                pass
        return resolve_models_arg(raw)

    # ── HTTP client ────────────────────────────────────────────────────────────
    request_timeout: float = 60.0
    max_retries: int = 3
    max_concurrent_requests: int = 3  # Conservative default for free-tier rate limits

    # ── Observability ──────────────────────────────────────────────────────────
    mlflow_tracking_uri: str = "sqlite:///results/mlflow/mlruns.db"

    # ── Security ───────────────────────────────────────────────────────────────
    # The security path has one probe set (data/prompts/security_probes.json,
    # every scored probe run three times): "full" runs it whole, "skip" leaves
    # security out of the run entirely. A skipped run drops the security
    # component from the recommendation and is flagged as non-reference
    # evidence on every report page. Resolved by
    # ``main._resolve_security_probes_path``; security_probes_path below
    # replaces the probe set for experiments only.
    security_mode: Literal["full", "skip"] = "full"

    # Optional path to a JSON file containing custom security probes —
    # overrides security_mode above.
    security_probes_path: str | None = None

    # ── Quality screen ─────────────────────────────────────────────────────────
    # Attempts per prompt. Three is the standard path: it gives the confidence
    # intervals and stability every reference report needs. Lower it only for
    # an exploratory pre-screen, which the report then flags as non-reference.
    quality_repetitions: int = Field(default=3, ge=1, le=5)

    # Prompt suite and catalog pair: "v3" (generic-screen-v3, default), "v2"
    # (previous suite, kept to re-merge its runs) or "v1" (generic-screen-v1,
    # immutable legacy baseline). Resolved by ``main._activate_quality_suite``.
    quality_suite: str = "v3"

    # Run generated code from code_execution prompts against their test cases
    # in the restricted sandbox (src/evaluators/code_sandbox.py), which scores
    # the share of tests passed. On in the standard path; set it to false to
    # send those responses to the judge panel instead.
    quality_code_execution: bool = True

    # Ceiling on a quality answer, hidden reasoning included. It bounds a model
    # that loops until its maximum output (a 131,072-token, 20-minute empty
    # answer in the 0.4.0 reference run) while leaving reasoning models ample
    # room; an answer that reaches it empty is scored as an empty response.
    quality_max_tokens: int = Field(default=16_384, ge=256)

    # Abort a run when collection transport failures exceed this ratio.
    max_quality_collection_error_rate: float = Field(default=0.15, ge=0.0, le=1.0)

    # Abort a run when security probe transport failures exceed this ratio.
    max_security_probe_error_rate: float = Field(default=0.15, ge=0.0, le=1.0)

    # Optional JSON override for the Model Compass decision weights. When
    # absent, the versioned use-case catalog supplies the 50/25/20/5 default.
    model_compass_weights: str | None = None

    # ── Cost modeling ──────────────────────────────────────────────────────────
    # Workload profile used for TCO/CER calculations.
    # Accepted values: "enterprise_qa" | "code_assistant" | "document_analysis"
    #                  | "chatbot_high_volume"
    workload_profile: str = "enterprise_qa"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()  # type: ignore[call-arg]
