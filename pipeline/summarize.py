"""
summarize.py — Resume y analiza una transcripción usando LLM local vía Ollama.

Estrategia map-reduce:
  MAP     -> trocea la transcripción; por cada trozo extrae notas estructuradas.
  REDUCE  -> combina las notas en: summary.md (resumen) + analysis.md (análisis).

Soporta instrucciones personalizadas para enfocar el análisis.

Salida:
  <out_dir>/summary.md
  <out_dir>/analysis.md

Uso:
  python summarize.py <out_dir> [--model qwen2.5:14b] [--instructions "..."]

Nota de arquitectura (Step 5 de la migración hexagonal): este módulo es un
shim delgado. La lógica real vive en:
  - pipeline.infrastructure.ollama.ollama_client.OllamaClient
  - pipeline.infrastructure.summarization.prompt_templates
  - pipeline.infrastructure.summarization.ollama_summarization_provider.OllamaSummarizationProvider
  - pipeline.application.summarization.summarize_video.SummarizeVideoUseCase
`resumir()` conserva exactamente la misma firma y comportamiento de cara a
`server.py` y `run_all.py` (ambos siguen haciendo `from summarize import
resumir` sin ningún cambio). Como esos call sites solo pasan `out_dir` (no
objetos `Transcript`/`VisualNotes` ya en memoria), este shim reconstruye esos
objetos de dominio a partir de `transcript.txt`/`visual_notes.md` en disco —
ver `_read_transcript`/`_read_visual_notes` — de forma que
`transcript.plain_text()`/`visual_notes.to_markdown()` reproducen el
contenido original byte a byte, para que `OllamaSummarizationProvider`
trocee exactamente el mismo texto que la versión original basada en
archivos.
"""
import argparse
import sys
from pathlib import Path

# See transcribe.py for why this is needed (same lazy-import/cwd situation).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.application.summarization.summarize_video import SummarizeVideoUseCase
from pipeline.domain.videos.transcript import Segment, Transcript
from pipeline.domain.videos.visual_note import VisualNote, VisualNotes
from pipeline.infrastructure.ollama.ollama_client import OllamaClient
from pipeline.infrastructure.summarization.ollama_summarization_provider import (
    OllamaSummarizationProvider,
)


def _read_transcript(txt_path: Path) -> Transcript:
    """Rebuilds a `Transcript` whose `.plain_text()` reproduces `txt_path`'s
    content byte-for-byte. `Transcript.plain_text()` is `"\\n".join(seg.text
    for seg in segments) + "\\n"` — a *free-form* join, so a single `Segment`
    whose `text` is the file's content minus its single trailing "\\n"
    round-trips exactly, regardless of how many original whisper segments
    it contains (their per-segment boundaries aren't needed downstream —
    only the joined text is chunked by `_trozos()`)."""
    content = txt_path.read_text(encoding="utf-8")
    text = content[:-1] if content.endswith("\n") else content
    return Transcript(segments=(Segment(start=0.0, end=0.0, text=text),), language="")


def _read_visual_notes(visual_path: Path) -> VisualNotes | None:
    """Rebuilds a `VisualNotes` whose `.to_markdown()` reproduces
    `visual_path`'s content byte-for-byte, or `None` if the file doesn't
    exist or is blank (matching `resumir()`'s original
    `if visual_texto.strip():` gate).

    Unlike `Transcript.plain_text()`, `VisualNotes.to_markdown()` always
    prepends `"### [HH:MM:SS]\\n"` to each note, so a single-note wrap isn't
    generally invertible — *except* that `analizar_visual()` always numbers
    frames starting at index 0, so the very first note's timestamp is
    always `00:00:00`. That invariant lets a single `VisualNote` round-trip
    the whole file: strip the guaranteed `"### [00:00:00]\\n"` prefix and
    use the remainder (minus its own trailing "\\n") as that note's
    description.
    """
    if not visual_path.exists():
        return None
    content = visual_path.read_text(encoding="utf-8")
    if not content.strip():
        return None

    prefix = "### [00:00:00]\n"
    if content.startswith(prefix):
        description = content[len(prefix):]
        description = description[:-1] if description.endswith("\n") else description
    else:
        # Defensive fallback: shouldn't happen for files written by
        # `analizar_visual()` (frame 0 is always timestamp 0), but don't
        # silently drop content if some other producer wrote this file.
        description = content[:-1] if content.endswith("\n") else content

    return VisualNotes(notes=(VisualNote(timestamp_seconds=0, description=description),))


def resumir(out_dir: Path, model: str, nombre: str,
            instructions: str | None = None) -> None:
    txt_path = out_dir / "transcript.txt"
    if not txt_path.exists():
        print(f"  ERROR: falta {txt_path}", file=sys.stderr)
        return

    transcript = _read_transcript(txt_path)
    visual_notes = _read_visual_notes(out_dir / "visual_notes.md")

    provider = OllamaSummarizationProvider(OllamaClient())
    use_case = SummarizeVideoUseCase(provider)
    use_case.execute(out_dir, model, transcript, visual_notes, nombre, instructions)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--nombre", default=None)
    ap.add_argument("--instructions", default=None,
                    help="Instrucciones personalizadas para el análisis")
    args = ap.parse_args()
    nombre = args.nombre or args.out_dir.name
    resumir(args.out_dir, args.model, nombre, args.instructions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
