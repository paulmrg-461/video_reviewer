"""Ollama-backed map-reduce summarization adapter.

Ports `pipeline/summarize.py`'s `_trozos()` (verbatim) and the full
`resumir()` MAP/REDUCE orchestration (both the audio MAP loop and the
conditional visual-notes second MAP pass, plus the additive
REDUCE-prompt-extension logic) exactly. Input is `Transcript`/`VisualNotes`
domain objects instead of files — `transcript.plain_text()` and
`visual_notes.to_markdown()` produce the same text the original file-based
version would have chunked, so `_trozos()` operates on identical input.
Returns `Summary`/`AnalysisResult` domain objects instead of writing files
— file writing is the use case's job (`SummarizeVideoUseCase`).

Note: `summarize()` takes an explicit `model: str` param not present in the
Step 5 spec's literal port signature — see `pipeline.application.
summarization.ports.SummarizationProvider` docstring for why.
"""
from __future__ import annotations

import typing

from pipeline.domain.videos.analysis import AnalysisResult, Summary
from pipeline.domain.videos.transcript import Transcript
from pipeline.domain.videos.visual_note import VisualNotes
from pipeline.infrastructure.ollama.ollama_client import OllamaClient
from pipeline.infrastructure.summarization.prompt_templates import (
    build_prompts,
    build_visual_map_prompt,
)

PALABRAS_POR_TROZO = 3500
SOLAPE = 200


def _trozos(texto: str, palabras: int, solape: int) -> typing.Iterator[str]:
    words = texto.split()
    i = 0
    while i < len(words):
        yield " ".join(words[i:i + palabras])
        i += palabras - solape


class OllamaSummarizationProvider:
    def __init__(
        self,
        ollama_client: OllamaClient,
        palabras_por_trozo: int = PALABRAS_POR_TROZO,
        solape: int = SOLAPE,
    ) -> None:
        self._client = ollama_client
        self._palabras_por_trozo = palabras_por_trozo
        self._solape = solape

    def summarize(
        self,
        model: str,
        transcript: Transcript,
        visual_notes: VisualNotes | None,
        video_name: str,
        instructions: str | None,
    ) -> tuple[Summary, AnalysisResult]:
        sys_map, prompt_map, prompt_reduce_summary, prompt_reduce_analysis = build_prompts(
            instructions, video_name
        )

        texto = transcript.plain_text()
        trozos = list(_trozos(texto, self._palabras_por_trozo, self._solape))
        print(f"  {len(texto.split())} palabras -> {len(trozos)} trozos (MAP)")

        notas = []
        for i, ch in enumerate(trozos, 1):
            print(f"    MAP trozo {i}/{len(trozos)}")
            nota = self._client.chat(model, sys_map, prompt_map.format(chunk=ch))
            notas.append(f"### Fragmento {i}\n{nota}")
        notas_join = "\n\n".join(notas)

        notas_visuales_join = ""
        if visual_notes is not None:
            visual_texto = visual_notes.to_markdown()
            if visual_texto.strip():
                trozos_v = list(_trozos(visual_texto, self._palabras_por_trozo, self._solape))
                print(f"  {len(visual_texto.split())} palabras visuales -> {len(trozos_v)} trozos (MAP visual)")
                map_prompt_visual = build_visual_map_prompt(instructions)
                notas_visuales = []
                for i, ch in enumerate(trozos_v, 1):
                    print(f"    MAP visual trozo {i}/{len(trozos_v)}")
                    nota = self._client.chat(model, sys_map, map_prompt_visual.format(chunk=ch))
                    notas_visuales.append(f"### Fragmento visual {i}\n{nota}")
                notas_visuales_join = "\n\n".join(notas_visuales)

        reduce_summary_user = prompt_reduce_summary.format(notas=notas_join, nombre=video_name)
        reduce_analysis_user = prompt_reduce_analysis.format(notas=notas_join, nombre=video_name)

        if notas_visuales_join:
            extra = (
                "\n\n--- NOTAS DE PANTALLA (video, MAP ya aplicado) ---\n"
                f"{notas_visuales_join}\n"
                "--- FIN NOTAS DE PANTALLA ---\n\n"
                "Con esta información adicional de pantalla, agrega también una sección "
                "'## Lo mostrado en pantalla' con hallazgos visuales relevantes, y una sección "
                "final '## Síntesis' que conecte lo dicho (audio) con lo mostrado en pantalla."
            )
            reduce_summary_user += extra
            reduce_analysis_user += extra

        print("  REDUCE -> summary.md")
        summary_content = self._client.chat(model, sys_map, reduce_summary_user, num_ctx=16384)

        print("  REDUCE -> analysis.md")
        analysis_content = self._client.chat(model, sys_map, reduce_analysis_user, num_ctx=16384)
        print(f"  ✓ summary.md + analysis.md")

        return Summary(content=summary_content + "\n"), AnalysisResult(content=analysis_content + "\n")
