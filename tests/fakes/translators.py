"""In-memory FakeMachineTranslator and FakeLLMTranslator for Phase 2 contract tests."""

from __future__ import annotations


class FakeMachineTranslator:
    """Wraps inputs as `[mt:...]` so tests can verify which path produced output.

    Structurally satisfies `app.application.ports.MachineTranslator`.
    """

    async def translate(self, text: str, src: str, tgt: str) -> str:
        return f"[mt:{text}]"

    async def translate_batch(self, texts: list[str], src: str, tgt: str) -> list[str]:
        return [f"[mt:{t}]" for t in texts]


class FakeLLMTranslator:
    """Wraps content as `[llm:...]` so tests can verify the LLM path.

    Structurally satisfies `app.application.ports.LLMTranslator`.
    """

    async def translate_section(self, content: str, system_instruction: str) -> str:
        return f"[llm:{content}]"
