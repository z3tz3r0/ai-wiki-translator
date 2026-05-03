"""Tests for `SelfConsistentLLMTranslator` · the N-sample voting wrapper."""

from __future__ import annotations

from app.application.ports import LLMTranslator
from app.infrastructure.self_consistent_llm import SelfConsistentLLMTranslator, pick_best


class _FixedLLM:
    """Stub `LLMTranslator` that returns successive canned outputs."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls: int = 0

    async def translate_section(self, content: str, system_instruction: str) -> str:
        idx = self.calls
        self.calls += 1
        if idx < len(self._outputs):
            return self._outputs[idx]
        return self._outputs[-1] if self._outputs else ""


# --- Protocol satisfaction -------------------------------------------------


def test_satisfies_llm_translator_protocol() -> None:
    inner = _FixedLLM(["x"])
    adapter = SelfConsistentLLMTranslator(inner=inner)
    assert isinstance(adapter, LLMTranslator)


# --- samples<=1 zero-overhead passthrough ----------------------------------


async def test_samples_one_returns_inner_output_unchanged() -> None:
    inner = _FixedLLM(["one"])
    adapter = SelfConsistentLLMTranslator(inner=inner, samples=1)
    out = await adapter.translate_section("source", "sys")
    assert out == "one"
    assert inner.calls == 1


async def test_samples_zero_treated_as_one() -> None:
    inner = _FixedLLM(["one"])
    adapter = SelfConsistentLLMTranslator(inner=inner, samples=0)
    out = await adapter.translate_section("source", "sys")
    assert out == "one"
    assert inner.calls == 1


# --- N-sample fanout -------------------------------------------------------


async def test_samples_three_calls_inner_three_times() -> None:
    inner = _FixedLLM(["a", "b", "c"])
    adapter = SelfConsistentLLMTranslator(inner=inner, samples=3)
    await adapter.translate_section("source", "sys")
    assert inner.calls == 3


async def test_samples_three_returns_best_by_ref_match() -> None:
    """Source has 2 refs; candidate that preserves both wins."""
    source = "alpha [[REF_1]] beta [[REF_2]] gamma"
    candidates = [
        "alpha [[REF_1]] beta",
        "alpha [[REF_1]] beta [[REF_2]] gamma",
        "alpha beta gamma",
    ]
    inner = _FixedLLM(candidates)
    adapter = SelfConsistentLLMTranslator(inner=inner, samples=3)
    out = await adapter.translate_section(source, "sys")
    assert out == "alpha [[REF_1]] beta [[REF_2]] gamma"


# --- pick_best (pure) ------------------------------------------------------


def test_pick_best_empty_candidates_returns_empty_string() -> None:
    assert pick_best("source", []) == ""


def test_pick_best_all_empty_returns_first_candidate() -> None:
    """Caller still gets something to inspect even if all samples were blank."""
    assert pick_best("source", ["", "   ", "\n"]) == ""


def test_pick_best_prefers_matching_ref_count_over_length() -> None:
    """Even a longer candidate loses if it drops a ref marker."""
    source = "[[REF_1]] [[REF_2]] [[REF_3]]"
    candidates = [
        "[[REF_1]] [[REF_2]]",
        "padding padding padding [[REF_1]] [[REF_2]] [[REF_3]] padding",
    ]
    assert pick_best(source, candidates) == candidates[1]


def test_pick_best_ties_on_refs_break_via_median_length() -> None:
    """When multiple candidates match ref count, the one closest to median length wins."""
    source = "[[REF_1]]"
    candidates = [
        "[[REF_1]] short",
        "[[REF_1]] medium length here",
        "[[REF_1]] this is a very very very long candidate text",
    ]
    out = pick_best(source, candidates)
    assert out == candidates[1], f"expected median-length candidate; got len {len(out)}"


def test_pick_best_skips_empty_when_others_are_present() -> None:
    source = "[[REF_1]]"
    candidates = ["", "[[REF_1]] real translation"]
    assert pick_best(source, candidates) == "[[REF_1]] real translation"
