"""Check, before a paid run, that the benchmark prompts reach the models as written.

A gateway between this tool and the models may rewrite requests. OpenRouter's
workspace guardrails, for instance, replace what they detect with labels such
as ``[PROMPT_INJECTION]`` or ``[ADDRESS]``, and the call still succeeds and is
billed. A score earned on a rewritten prompt measures the gateway, not the
model, and nothing in the response says so.

OpenRouter can echo the body it forwards upstream, so every prompt is audited
at the start of each collection, with no cache: a filter that changes or
disappears is picked up by the next run. A rewritten quality item stops the run,
because the suite is ours to reword. A rewritten security probe is not sent and
leaves the RSI, whose ``security_probe_set_id`` then names the probes really
measured. Probes are never reworded to get past the filter: it is a security
control, and passing it by disguise would measure nothing useful.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.api.openrouter_client import OpenRouterError

logger = logging.getLogger(__name__)

MIN_DELIVERED_SCORED_SHARE = 0.7
"""Below this share of scored probes delivered, an RSI says too little to be worth paying for."""

_AUDIT_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 2.0
_DEBUG_REDACTION_MARKER = "from debug output>"
"""OpenRouter hides secret-looking text from the echo itself, not necessarily from the model."""
_PROBE_TEXT = "Say hello."


class PromptDeliveryError(ValueError):
    """The run cannot produce evidence on the prompts as written; nothing was collected."""


class _EchoClient(Protocol):
    async def upstream_request(self, model: str, text: str) -> dict[str, Any] | None: ...

    async def get_models(self) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class AuditedPrompt:
    """One text to check: a quality item or one turn of a security probe."""

    kind: str
    name: str
    text: str


@dataclass
class PromptDeliveryAudit:
    """What the gateway forwards for each benchmark prompt."""

    audit_model: str
    checked_count: int = 0
    altered_items: dict[str, str] = field(default_factory=dict)
    altered_probes: dict[str, str] = field(default_factory=dict)
    unverifiable: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        """Record stored with the run, so the report can state what was left out."""
        return {
            "verified": True,
            "audit_model": self.audit_model,
            "checked_count": self.checked_count,
            "undelivered_probes": sorted(self.altered_probes),
            "unverifiable": sorted(self.unverifiable),
        }


def not_verified_payload() -> dict[str, object]:
    """Record of a run that switched the audit off."""
    return {"verified": False, "undelivered_probes": [], "unverifiable": []}


def _text_of(content: object) -> Iterable[str]:
    """Yield the text of a message's content, whichever shape the upstream API uses."""
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                yield str(part["text"])


def delivered_user_text(upstream: Mapping[str, Any]) -> str | None:
    """Return the user text of an echoed upstream body, or ``None`` for an unknown shape.

    Providers name it differently: ``messages`` (chat), ``input`` (responses),
    ``contents``/``parts`` (Gemini). A body that only carries a rendered prompt
    string cannot be compared reliably.
    """
    for key in ("messages", "input", "contents"):
        entries = upstream.get(key)
        if not isinstance(entries, list):
            continue
        texts = [
            text
            for entry in entries
            if isinstance(entry, Mapping) and entry.get("role") == "user"
            for text in _text_of(entry.get("content", entry.get("parts")))
        ]
        if texts:
            return "\n".join(texts)
    return None


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _unit_price(model: Mapping[str, Any]) -> float:
    pricing = model.get("pricing") or {}
    try:
        return float(pricing.get("prompt", 0)) + float(pricing.get("completion", 0))
    except (TypeError, ValueError):
        return float("inf")


async def _audit_models(client: _EchoClient, models: list[str]) -> list[str]:
    """Return the target models by price, starting with the cheapest whose upstream body can be read."""
    prices = {str(entry.get("id")): _unit_price(entry) for entry in await client.get_models()}
    by_price = sorted(models, key=lambda name: prices.get(name, float("inf")))
    for index, model in enumerate(by_price):
        try:
            upstream = await client.upstream_request(model, _PROBE_TEXT)
        except OpenRouterError as exc:
            logger.warning("[delivery] Cannot audit through '%s': %s", model, exc)
            continue
        if upstream is not None and delivered_user_text(upstream) is not None:
            return [model, *by_price[index + 1 :], *by_price[:index]]
    raise PromptDeliveryError(
        "Could not read what the gateway forwards through any target model, so prompt delivery cannot be checked. "
        "Set PROMPT_DELIVERY_AUDIT=false to run anyway; the report will flag the run as not reference-grade."
    )


async def _delivered(client: _EchoClient, models: list[str], prompt: AuditedPrompt) -> str | None:
    # The guardrail applies to the whole workspace, so any target model can echo it. A provider that
    # renders the chat into one prompt string is unreadable, so a retry also moves on to the next model.
    for attempt in range(max(_AUDIT_ATTEMPTS, len(models))):
        model = models[attempt % len(models)]
        try:
            upstream = await client.upstream_request(model, prompt.text)
        except OpenRouterError as exc:
            logger.warning("[delivery] Audit of '%s' failed (attempt %d): %s", prompt.name, attempt + 1, exc)
        else:
            text = delivered_user_text(upstream) if upstream is not None else None
            if text is not None:
                return text
            logger.warning(
                "[delivery] No readable echo for '%s' via '%s' (attempt %d)", prompt.name, model, attempt + 1
            )
        await asyncio.sleep(_RETRY_DELAY_SECONDS)
    return None


def prompts_to_audit(
    quality_prompts: Iterable[tuple[str, str]], probes: Iterable[Mapping[str, Any]]
) -> list[AuditedPrompt]:
    """List every text of the run: each quality item and each turn of each probe."""
    audited = [AuditedPrompt("quality", name, text) for name, text in quality_prompts]
    for probe in probes:
        turns = probe.get("turns") or [probe.get("message")]
        audited.extend(AuditedPrompt("security", str(probe["name"]), str(turn)) for turn in turns if turn)
    return audited


async def audit_prompt_delivery(
    client: _EchoClient, models: list[str], prompts: list[AuditedPrompt]
) -> PromptDeliveryAudit:
    """Ask the gateway what it would forward for every prompt.

    Raises:
        PromptDeliveryError: If the forwarded text cannot be read at all.
    """
    audit_models = await _audit_models(client, models)
    delivered = await asyncio.gather(*(_delivered(client, audit_models, prompt) for prompt in prompts))
    audit = PromptDeliveryAudit(audit_model=audit_models[0], checked_count=len(prompts))
    for prompt, text in zip(prompts, delivered, strict=True):
        if text is None:
            raise PromptDeliveryError(f"Could not read what the gateway forwards for '{prompt.name}'.")
        if _DEBUG_REDACTION_MARKER in text:
            audit.unverifiable.append(prompt.name)
        elif _normalized(text) != _normalized(prompt.text):
            altered = audit.altered_items if prompt.kind == "quality" else audit.altered_probes
            altered[prompt.name] = text
    return audit


def enforce_prompt_delivery(audit: PromptDeliveryAudit, scored_probe_names: Iterable[str]) -> None:
    """Stop before any paid call when the run could not produce usable evidence.

    Raises:
        PromptDeliveryError: If a quality item is rewritten, or too few scored
            probes get through.
    """
    if audit.altered_items:
        details = "\n".join(f"  {name}: {text[:200]!r}" for name, text in sorted(audit.altered_items.items()))
        raise PromptDeliveryError(
            f"{len(audit.altered_items)} quality item(s) would reach the models rewritten by the gateway:\n{details}\n"
            "Reword them in scripts/build_quality_suite_v3.py and rebuild the suite; nothing was collected."
        )
    scored = set(scored_probe_names)
    if scored:
        delivered_share = len(scored - set(audit.altered_probes)) / len(scored)
        if delivered_share < MIN_DELIVERED_SCORED_SHARE:
            raise PromptDeliveryError(
                f"Only {delivered_share:.0%} of the scored security probes reach the models unchanged "
                f"(minimum {MIN_DELIVERED_SCORED_SHARE:.0%}), too few for a meaningful RSI: "
                f"{sorted(scored & set(audit.altered_probes))}. Nothing was collected. "
                "Use SECURITY=skip to run without security evidence, or ask the workspace admin about the guardrails."
            )
