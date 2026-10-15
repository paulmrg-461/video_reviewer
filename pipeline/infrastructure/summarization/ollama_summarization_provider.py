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
    NO_INFO,
    build_prompts,
    build_visual_map_prompt,
)

# ~2200 palabras de español ≈ 4-5k tokens: cabe en num_ctx=8192 junto con el prompt.
PALABRAS_POR_TROZO = 2200
# Si las notas superan esto, el REDUCE desbordaría num_ctx=16384: se consolidan antes.
MAX_PALABRAS_REDUCE = 6000
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
            if NO_INFO not in nota:
                notas.append(f"### Fragmento {i}\n{nota}")
        notas_join = self._fit_for_reduce(model, sys_map, notas)

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
                    if NO_INFO not in nota:
                        notas_visuales.append(f"### Fragmento visual {i}\n{nota}")
                notas_visuales_join = self._fit_for_reduce(model, sys_map, notas_visuales)

        if not notas_join.strip():
            notas_join = "(No se encontró información relevante en la transcripción.)"

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

    def _fit_for_reduce(self, model: str, system: str, notas: list[str]) -> str:
        """Join notes; while they would overflow the REDUCE context, consolidate
        them in groups (extra MAP level) instead of letting Ollama truncate."""
        joined = "\n\n".join(notas)
        while len(joined.split()) > MAX_PALABRAS_REDUCE and len(notas) > 1:
            print(f"  consolidando {len(notas)} bloques de notas (demasiado largas para REDUCE)")
            groups = [notas[i:i + 4] for i in range(0, len(notas), 4)]
            notas = [
                self._client.chat(
                    model, system,
                    "Consolida estas notas fusionando duplicados. Conserva TODOS los datos "
                    "exactos (cifras, nombres, fechas, decisiones) y no agregues nada nuevo.\n\n"
                    + "\n\n".join(g),
                )
                for g in groups
            ]
            joined = "\n\n".join(notas)
        return joined
