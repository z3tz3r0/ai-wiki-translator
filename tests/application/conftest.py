"""Phase 2 contract-test fixtures · parametrized to extend in Phase 4."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes.repos import FakeGlossaryRepo, FakePromptRepo
from tests.fakes.storage import InMemoryDraftStorage
from tests.fakes.translators import FakeLLMTranslator, FakeMachineTranslator
from tests.fakes.wikidata import FakeWikidataReader
from tests.fakes.wikipedia import FakeWikipediaReader


@pytest.fixture(params=["fakes"], ids=["fakes"])
def adapters(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Adapter set keyed by port name.

    Phase 4 extends `params` to include `"real"` and wires httpx-backed
    adapters into the same dict shape, so test bodies never change.
    """
    if request.param == "fakes":
        return {
            "wikipedia": FakeWikipediaReader(),
            "wikidata": FakeWikidataReader(),
            "machine": FakeMachineTranslator(),
            "llm": FakeLLMTranslator(),
            "prompt_repo": FakePromptRepo(),
            "glossary_repo": FakeGlossaryRepo(),
            "storage": InMemoryDraftStorage(),
        }
    pytest.fail(f"unknown adapter set: {request.param}")
