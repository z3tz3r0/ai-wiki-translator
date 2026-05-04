"""Tests for `LiteValidatorAdapter` · multi-key google-genai validator."""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from app.application.dto import (
    LanguageRuleSet,
    RuleEntry,
    TransliterationCandidate,
)
from app.application.ports import TransliterationValidator
from app.infrastructure.lite_validator import LiteValidatorAdapter, _retry_delay_seconds

_JUDGE_TEMPLATE = "fake judge template"


def _ruleset() -> LanguageRuleSet:
    return LanguageRuleSet(
        lang="en",
        title="rules-en",
        url="https://th.wikipedia.org/wiki/rules-en",
        scraped_at=datetime.datetime(2026, 5, 4, 12, 0, 0),
        entries=(RuleEntry(grapheme="A", thai="เอ"),),
        excerpt="| A | เอ |",
    )


def _candidate(thai: str, latin: str | None = None) -> TransliterationCandidate:
    return TransliterationCandidate(thai=thai, context="ctx", latin_hint=latin)


def _make_fake_client(
    response_text: str | None = "[]",
) -> tuple[Any, list[dict[str, Any]]]:
    """Return a `(fake_client, calls)` pair mimicking `genai.Client.aio.models`."""
    calls: list[dict[str, Any]] = []

    async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        calls.append({"model": model, "contents": contents, "config": config})
        return SimpleNamespace(text=response_text)

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    return client, calls


def test_satisfies_protocol() -> None:
    client, _ = _make_fake_client()
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    assert isinstance(adapter, TransliterationValidator)


def test_empty_clients_raises() -> None:
    with pytest.raises(ValueError, match="clients"):
        LiteValidatorAdapter(clients=[], judge_template=_JUDGE_TEMPLATE)


def test_empty_template_raises() -> None:
    client, _ = _make_fake_client()
    with pytest.raises(ValueError, match="judge_template"):
        LiteValidatorAdapter(clients=[client], judge_template="   ")


async def test_empty_candidates_returns_empty_without_calling_client() -> None:
    client, calls = _make_fake_client()
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    out = await adapter.validate((), _ruleset())
    assert out == ()
    assert calls == []


async def test_validate_parses_well_formed_json() -> None:
    payload = json.dumps(
        [
            {
                "thai": "แอนเดอส์ เฮลส์เบิร์ก",
                "status": "approved",
                "rule_citation": "rule line",
                "suggested": "",
                "reason": "matches",
            }
        ],
        ensure_ascii=False,
    )
    client, _ = _make_fake_client(response_text=payload)
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    out = await adapter.validate(
        (_candidate("แอนเดอส์ เฮลส์เบิร์ก", "Anders Hejlsberg"),),
        _ruleset(),
    )
    assert len(out) == 1
    assert out[0].status == "approved"
    assert out[0].rule_citation == "rule line"
    assert out[0].candidate.thai == "แอนเดอส์ เฮลส์เบิร์ก"


async def test_validate_falls_back_to_uncertain_on_malformed_json() -> None:
    client, _ = _make_fake_client(response_text="not json")
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    out = await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
    assert len(out) == 1
    assert out[0].status == "uncertain"
    assert "parseable JSON" in out[0].reason


async def test_validate_falls_back_when_response_length_mismatch() -> None:
    payload = json.dumps([{"thai": "x", "status": "approved"}])  # 1 item for 2 candidates
    client, _ = _make_fake_client(response_text=payload)
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    out = await adapter.validate(
        (_candidate("ก ก ก"), _candidate("ข ข ข")),
        _ruleset(),
    )
    assert len(out) == 2
    assert all(v.status == "uncertain" for v in out)


async def test_validate_falls_back_when_json_is_not_list() -> None:
    payload = json.dumps({"status": "approved"})
    client, _ = _make_fake_client(response_text=payload)
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    out = await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
    assert len(out) == 1
    assert out[0].status == "uncertain"


async def test_validate_falls_back_when_item_is_not_object() -> None:
    payload = json.dumps([1])
    client, _ = _make_fake_client(response_text=payload)
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    out = await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
    assert len(out) == 1
    assert out[0].status == "uncertain"


async def test_validate_coerces_unknown_status_to_uncertain() -> None:
    payload = json.dumps([{"status": "totally_invalid", "reason": "x"}])
    client, _ = _make_fake_client(response_text=payload)
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    out = await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
    assert out[0].status == "uncertain"


async def test_validate_passes_judge_template_as_system_instruction() -> None:
    payload = json.dumps([{"status": "approved"}])
    client, calls = _make_fake_client(response_text=payload)
    adapter = LiteValidatorAdapter(clients=[client], judge_template="my judge")
    await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
    assert len(calls) == 1
    assert calls[0]["config"].system_instruction == "my judge"


async def test_validate_requests_json_mime_type() -> None:
    payload = json.dumps([{"status": "approved"}])
    client, calls = _make_fake_client(response_text=payload)
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
    assert calls[0]["config"].response_mime_type == "application/json"


async def test_validate_uses_configured_model() -> None:
    payload = json.dumps([{"status": "approved"}])
    client, calls = _make_fake_client(response_text=payload)
    adapter = LiteValidatorAdapter(
        clients=[client],
        judge_template=_JUDGE_TEMPLATE,
        model="custom-model",
    )
    await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
    assert calls[0]["model"] == "custom-model"


async def test_validate_load_balances_across_keys() -> None:
    """Two clients · second call must hit the freshest (least-recently-used) key."""
    payload = json.dumps([{"status": "approved"}])

    def make_marked_client(label: str) -> tuple[Any, list[str]]:
        hits: list[str] = []

        async def generate_content(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
            hits.append(label)
            return SimpleNamespace(text=payload)

        return (
            SimpleNamespace(
                aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
            ),
            hits,
        )

    c1, hits1 = make_marked_client("k1")
    c2, hits2 = make_marked_client("k2")
    adapter = LiteValidatorAdapter(clients=[c1, c2], judge_template=_JUDGE_TEMPLATE)

    cand = (_candidate("แอนเดอส์ เฮลส์เบิร์ก"),)
    await adapter.validate(cand, _ruleset())
    await adapter.validate(cand, _ruleset())

    assert len(hits1) == 1
    assert len(hits2) == 1


async def test_validate_429_falls_back_to_uncertain() -> None:
    class RateLimit(Exception):
        code: ClassVar[int] = 429
        details: ClassVar[list[dict[str, Any]]] = [
            {"@type": "google.rpc.RetryInfo", "retryDelay": "0s"}
        ]

    async def always_429(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        raise RateLimit("rate limited")

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=always_429))
    )
    adapter = LiteValidatorAdapter(
        clients=[client],
        judge_template=_JUDGE_TEMPLATE,
        max_retries=1,
    )
    out = await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())
    # All 429s exhausted · adapter falls back to all-uncertain (not raise).
    assert len(out) == 1
    assert out[0].status == "uncertain"
    assert "validator call failed" in out[0].reason


async def test_validate_non_retriable_exception_propagates() -> None:
    async def boom(*, model: str, contents: Any, config: Any) -> SimpleNamespace:
        raise RuntimeError("something else")

    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=boom)))
    adapter = LiteValidatorAdapter(clients=[client], judge_template=_JUDGE_TEMPLATE)
    with pytest.raises(RuntimeError, match="something else"):
        await adapter.validate((_candidate("แอนเดอส์ เฮลส์เบิร์ก"),), _ruleset())


def test_retry_delay_503_uses_exponential_backoff() -> None:
    class Unavailable(Exception):
        code: ClassVar[int] = 503

    assert _retry_delay_seconds(Unavailable(), attempt=2) == 4.0


def test_retry_delay_429_non_list_details_defaults_to_60() -> None:
    class RateLimit(Exception):
        code: ClassVar[int] = 429
        details: ClassVar[object] = "bad"

    assert _retry_delay_seconds(RateLimit()) == 60.0


def test_retry_delay_429_ignores_non_dict_details() -> None:
    class RateLimit(Exception):
        code: ClassVar[int] = 429
        details: ClassVar[list[object]] = [object()]

    assert _retry_delay_seconds(RateLimit()) == 60.0


def test_retry_delay_429_ignores_non_retryinfo_details() -> None:
    class RateLimit(Exception):
        code: ClassVar[int] = 429
        details: ClassVar[list[dict[str, str]]] = [{"@type": "google.rpc.DebugInfo"}]

    assert _retry_delay_seconds(RateLimit()) == 60.0


def test_retry_delay_429_bad_retry_delay_defaults_to_60() -> None:
    class RateLimit(Exception):
        code: ClassVar[int] = 429
        details: ClassVar[list[dict[str, str]]] = [
            {"@type": "google.rpc.RetryInfo", "retryDelay": "oops"}
        ]

    assert _retry_delay_seconds(RateLimit()) == 60.0
