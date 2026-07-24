"""Ollama vision-model-backed frame description adapter.

Ports `pipeline/visual.py`'s `_describir_frame()` — same prompt text, same
error contract (raises on failure; the use case decides how to handle it,
matching today's `analizar_visual()` catching `Exception` at the call site).
"""
from __future__ import annotations

from pathlib import Path

from pipeline.infrastructure.ollama.ollama_client import OllamaClient

PROMPT_FRAME = (
    "Esta es una captura de pantalla tomada durante una grabación de escritorio/reunión. "
    "Describe en viñetas cortas: qué aplicación o ventana está activa, qué texto o datos "
    "relevantes son visibles, y qué está ocurriendo en pantalla. No inventes texto que no "
    "puedas leer con claridad. Si la pantalla está vacía o sin contenido relevante, dilo "
    "brevemente en una línea."
)


class OllamaVisionAnalysisProvider:
    def __init__(self, ollama_client: OllamaClient) -> None:
        self._client = ollama_client

    def describe(self, frame: Path, model: str) -> str:
        return self._client.chat_with_image(model, PROMPT_FRAME, frame.read_bytes())
