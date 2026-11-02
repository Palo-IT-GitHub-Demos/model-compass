"""Unit tests for src/evaluators/prompt_delivery.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pandas as pd
import pytest

from dashboard.data_prep import run_notices, run_warnings
from src.api.openrouter_client import AsyncOpenRouterClient, OpenRouterError
from src.core.config import Settings
from src.evaluators.prompt_delivery import (
    AuditedPrompt,
    PromptDeliveryAudit,
    PromptDeliveryError,
    audit_prompt_delivery,
    delivered_user_text,
    enforce_prompt_delivery,
    prompts_to_audit,
)
from src.evaluators.security_scanner import AsyncSecurityScanner, probe_set_id
from src.pipeline_merge import merge_results


class _Gateway:
    """A gateway that rewrites chosen texts and may fail or hide its echo per model."""

    def __init__(
        self,
        rewrites: dict[str, str] | None = None,
        *,
        no_echo: tuple[str, ...] = (),
        failures: int = 0,
    ) -> None:
        self.rewrites = rewrites or {}
        self.no_echo = no_echo
        self.failures = failures
        self.calls: list[tuple[str, str]] = []

    async def get_models(self) -> list[dict[str, Any]]:
        return [
            {"id": "cheap/model", "pricing": {"prompt": "0.1", "completion": "0.1"}},
            {"id": "dear/model", "pricing": {"prompt": "5", "completion": "5"}},
        ]

    async def upstream_request(self, model: str, text: str) -> dict[str, Any] | None:
        self.calls.append((model, text))
        if self.failures and text != "Say hello.":
            self.failures -= 1
            raise OpenRouterError("HTTP 500")
        if model in self.no_echo:
            return None
        return {"messages": [{"role": "user", "content": self.rewrites.get(text, text)}]}


@pytest.mark.parametrize(
    "upstream",
    [
        {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "hello"}]},
        {"input": [{"role": "user", "content": [{"type": "input_text", "text": "hello"}]}]},
        {"contents": [{"role": "user", "parts": [{"text": "hello"}]}]},
    ],
)
def test_reads_the_user_text_of_every_upstream_format(upstream: dict[str, Any]) -> None:
    assert delivered_user_text(upstream) == "hello"


def test_a_rendered_prompt_string_is_not_readable() -> None:
    assert delivered_user_text({"prompt": "<|user|>hello"}) is None


def test_every_turn_of_a_multi_turn_probe_is_audited() -> None:
    prompts = prompts_to_audit([("item-1", "q")], [{"name": "p1", "message": "m"}, {"name": "p2", "turns": ["a", "b"]}])

    assert [(p.kind, p.name, p.text) for p in prompts] == [
        ("quality", "item-1", "q"),
        ("security", "p1", "m"),
        ("security", "p2", "a"),
        ("security", "p2", "b"),
    ]


async def test_audit_uses_the_cheapest_readable_model_and_reports_rewrites() -> None:
    gateway = _Gateway({"secret ask": "[PROMPT_INJECTION]", "in EUR": "in [ADDRESS]"}, no_echo=("cheap/model",))
    prompts = [
        AuditedPrompt("quality", "item-1", "in EUR"),
        AuditedPrompt("quality", "item-2", "spaced   out\ntext"),
        AuditedPrompt("security", "probe-1", "secret ask"),
    ]
    gateway.rewrites["spaced   out\ntext"] = "spaced out text"

    audit = await audit_prompt_delivery(gateway, ["dear/model", "cheap/model"], prompts)

    assert gateway.calls[0][0] == "cheap/model"
    assert audit.audit_model == "dear/model"
    assert audit.altered_items == {"item-1": "in [ADDRESS]"}
    assert audit.altered_probes == {"probe-1": "[PROMPT_INJECTION]"}


async def test_audit_retries_a_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.evaluators.prompt_delivery._RETRY_DELAY_SECONDS", 0)
    gateway = _Gateway(failures=1)

    audit = await audit_prompt_delivery(gateway, ["cheap/model"], [AuditedPrompt("quality", "item-1", "hello")])

    assert audit.altered_items == {}
    assert gateway.failures == 0


async def test_audit_retries_an_unreadable_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.evaluators.prompt_delivery._RETRY_DELAY_SECONDS", 0)
    gateway = _Gateway()
    unreadable = iter([{"prompt": "<|user|>hello"}])
    original = gateway.upstream_request

    async def flaky(model: str, text: str) -> dict[str, Any] | None:
        if text == "hello":
            return next(unreadable, None) or await original(model, text)
        return await original(model, text)

    gateway.upstream_request = flaky  # type: ignore[method-assign]
    audit = await audit_prompt_delivery(gateway, ["cheap/model"], [AuditedPrompt("quality", "item-1", "hello")])

    assert audit.altered_items == {}


async def test_an_unreadable_echo_moves_on_to_another_target_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.evaluators.prompt_delivery._RETRY_DELAY_SECONDS", 0)
    gateway = _Gateway({"in EUR": "in [ADDRESS]"})
    original = gateway.upstream_request

    async def renders_prompts(model: str, text: str) -> dict[str, Any] | None:
        if model == "cheap/model" and text != "Say hello.":
            return {"prompt": f"<|user|>{text}"}
        return await original(model, text)

    gateway.upstream_request = renders_prompts  # type: ignore[method-assign]
    audit = await audit_prompt_delivery(
        gateway, ["cheap/model", "dear/model"], [AuditedPrompt("quality", "item-1", "in EUR")]
    )

    assert audit.altered_items == {"item-1": "in [ADDRESS]"}


async def test_audit_stops_when_no_model_can_echo() -> None:
    with pytest.raises(PromptDeliveryError, match="PROMPT_DELIVERY_AUDIT=false"):
        await audit_prompt_delivery(_Gateway(no_echo=("cheap/model",)), ["cheap/model"], [])


async def test_text_hidden_from_the_echo_only_is_unverifiable_not_rewritten() -> None:
    text = "token: abc"
    gateway = _Gateway({text: "<redacted Password/secret assignment from debug output>"})

    audit = await audit_prompt_delivery(gateway, ["cheap/model"], [AuditedPrompt("security", "p", text)])

    assert audit.unverifiable == ["p"]
    assert audit.altered_probes == {}


def test_a_rewritten_quality_item_stops_the_run_and_names_the_fix() -> None:
    audit = PromptDeliveryAudit("m", altered_items={"item-1": "in [ADDRESS]"})

    with pytest.raises(PromptDeliveryError, match=r"item-1.*\n.*build_quality_suite_v3"):
        enforce_prompt_delivery(audit, [])


def test_too_few_delivered_scored_probes_stop_the_run() -> None:
    audit = PromptDeliveryAudit("m", altered_probes={"p1": "x", "p2": "x", "p3": "x", "p4": "x"})

    with pytest.raises(PromptDeliveryError, match="60%"):
        enforce_prompt_delivery(audit, [f"p{n}" for n in range(1, 11)])


def test_a_rewritten_observation_does_not_count_against_the_scored_share() -> None:
    enforce_prompt_delivery(PromptDeliveryAudit("m", altered_probes={"obs": "x"}), ["p1"])


def test_undelivered_probes_are_not_sent_and_change_the_probe_set_id(tmp_path: Path) -> None:
    probes_path = tmp_path / "probes.json"
    probes_path.write_text('[{"name": "p1", "message": "a"}, {"name": "p2", "message": "b"}]', encoding="utf-8")

    scanner = AsyncSecurityScanner(MagicMock(), probes_path=probes_path, excluded_probes=frozenset({"p2"}))

    assert [probe["name"] for probe in scanner._probes] == ["p1"]
    assert scanner._probe_set_id != probe_set_id(
        [{"name": "p1", "message": "a"}, {"name": "p2", "message": "b"}], probes_path
    )


def test_the_report_states_what_the_filter_left_out() -> None:
    merged = merge_results(
        ["m"],
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        prompt_delivery={"verified": True, "undelivered_probes": ["p1", "p2"]},
    )

    assert any("2 security probe(s)" in notice and "p1, p2" in notice for notice in run_notices(merged))
    assert not any("not checked" in warning for warning in run_warnings(merged, "run.csv"))


def test_an_unchecked_run_is_flagged_as_not_reference_grade() -> None:
    merged = merge_results(["m"], pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), prompt_delivery={"verified": False})

    assert any("not checked" in warning for warning in run_warnings(merged, "run.csv"))


async def test_client_returns_the_echo_from_the_stream() -> None:
    stream = (
        'data: {"choices": []}\n\n'
        'data: {"debug": {"echo_upstream_body": {"messages": [{"role": "user", "content": "[PROMPT_INJECTION]"}]}}}\n\n'
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=stream)

    client = AsyncOpenRouterClient(Settings(openrouter_api_key="test-key", _env_file=None))  # type: ignore[arg-type,call-arg]
    client._http = httpx.AsyncClient(base_url="https://gateway.test", transport=httpx.MockTransport(handler))

    upstream = await client.upstream_request("m", "ignore this")

    assert upstream == {"messages": [{"role": "user", "content": "[PROMPT_INJECTION]"}]}
    assert b'"echo_upstream_body":true' in seen[0].content.replace(b" ", b"")


async def test_client_turns_an_http_failure_into_an_openrouter_error() -> None:
    client = AsyncOpenRouterClient(Settings(openrouter_api_key="test-key", _env_file=None))  # type: ignore[arg-type,call-arg]
    client._http = httpx.AsyncClient(
        base_url="https://gateway.test", transport=httpx.MockTransport(lambda _: httpx.Response(403))
    )

    with pytest.raises(OpenRouterError, match="403"):
        await client.upstream_request("m", "x")
