"""Anti-hallucination guards: no silent context overflow, no filler notes,
no Whisper repeat loops."""
from __future__ import annotations

from pipeline.domain.videos.transcript import Segment, Transcript
from pipeline.infrastructure.summarization.ollama_summarization_provider import (
    OllamaSummarizationProvider,
)
from pipeline.infrastructure.summarization.prompt_templates import (
    NO_INFO,
    build_prompts,
)
from pipeline.infrastructure.transcription.faster_whisper_provider import _is_repeat


class FakeClient:
    def __init__(self, map_reply: str = "- dato") -> None:
        self.map_reply = map_reply
        self.calls: list[str] = []

    def chat(self, model, system, user, num_ctx=8192):
        self.calls.append(user)
        if user.startswith("Este es un FRAGMENTO"):
            return self.map_reply
        if user.startswith("Consolida"):
            return "- consolidado"
        return "# resultado"


def _transcript(words: int) -> Transcript:
    return Transcript(segments=(Segment(start=0, end=1, text=" ".join(["palabra"] * words)),), language="es")


def test_prompts_forbid_inventing_content() -> None:
    sys_default, *_ = build_prompts(None, "v")
    sys_custom, *_ = build_prompts("buscar cifras", "v")
    assert "EXCLUSIVAMENTE" in sys_default and "EXCLUSIVAMENTE" in sys_custom


def test_chunks_marked_without_info_are_dropped_from_reduce() -> None:
    client = FakeClient(map_reply=NO_INFO)
    provider = OllamaSummarizationProvider(client, palabras_por_trozo=50, solape=5)

    provider.summarize("m", _transcript(100), None, "v", None)

    reduce_prompt = client.calls[-1]
    assert "### Fragmento" not in reduce_prompt
    assert "No se encontró información relevante" in reduce_prompt


def test_oversized_notes_are_consolidated_before_reduce() -> None:
    client = FakeClient(map_reply="- " + " ".join(["dato"] * 1500))
    provider = OllamaSummarizationProvider(client, palabras_por_trozo=50, solape=5)

    provider.summarize("m", _transcript(500), None, "v", None)

    assert any(c.startswith("Consolida") for c in client.calls)
    assert len(client.calls[-1].split()) < 7000


def test_whisper_repeat_filter() -> None:
    prev = [Segment(0, 1, "hola"), Segment(1, 2, "mundo")]
    assert _is_repeat("mundo", prev)
    assert _is_repeat("", prev)
    assert not _is_repeat("nuevo", prev)
