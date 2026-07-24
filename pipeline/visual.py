"""visual.py — Extrae frames de un video y los analiza con un modelo de visión vía Ollama.

Salida:
  <out_dir>/visual_notes.md   (una descripción por frame, con timestamp)

Uso:
  python visual.py <video.mp4> <out_dir> [--model gemma4:e4b] [--intervalo 15]

Variables de entorno:
  VISUAL_FRAME_INTERVAL_SEG   segundos entre frames muestreados (default: 15)

Nota de arquitectura (Step 5 de la migración hexagonal): este módulo es un
shim delgado. La lógica real vive en:
  - pipeline.infrastructure.visual_analysis.ffmpeg_frame_extractor.FfmpegFrameExtractor
  - pipeline.infrastructure.visual_analysis.ollama_vision_provider.OllamaVisionAnalysisProvider
  - pipeline.application.visual_analysis.analyze_visual.AnalyzeVisualUseCase
`analizar_visual()` conserva exactamente la misma firma y comportamiento de
cara a `server.py` (que sigue haciendo `from visual import analizar_visual`
sin ningún cambio), incluyendo su contrato de retorno original (`Path` en
skip/éxito, `None` si no se extrajeron frames) — el `AnalyzeVisualUseCase`
subyacente devuelve `None` también en el caso "skip" (ver su docstring para
el porqué), así que este shim reconstruye el `Path` a partir de la
existencia del archivo tras llamar al use case.
"""
import argparse
import os
import sys
from pathlib import Path

# See transcribe.py for why this is needed (same lazy-import/cwd situation).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.application.visual_analysis.analyze_visual import AnalyzeVisualUseCase
from pipeline.infrastructure.ollama.ollama_client import OllamaClient
from pipeline.infrastructure.visual_analysis.ffmpeg_frame_extractor import (
    FfmpegFrameExtractor,
)
from pipeline.infrastructure.visual_analysis.ollama_vision_provider import (
    OllamaVisionAnalysisProvider,
)

INTERVALO_SEG = int(os.environ.get("VISUAL_FRAME_INTERVAL_SEG", "15"))


def extraer_frames(video: Path, out_dir: Path, intervalo: int = INTERVALO_SEG) -> list[Path]:
    """ffmpeg: 1 frame cada `intervalo` segundos -> out_dir/frame_00001.jpg, ..."""
    return FfmpegFrameExtractor().extract_frames(video, out_dir, intervalo)


def _describir_frame(model: str, frame: Path) -> str:
    return OllamaVisionAnalysisProvider(OllamaClient()).describe(frame, model)


def analizar_visual(video: Path, out_dir: Path, vision_model: str = "gemma4:e4b",
                    intervalo: int = INTERVALO_SEG) -> Path | None:
    """Extrae frames y genera <out_dir>/visual_notes.md. Devuelve None si no hay frames."""
    notes_path = out_dir / "visual_notes.md"
    use_case = AnalyzeVisualUseCase(
        FfmpegFrameExtractor(), OllamaVisionAnalysisProvider(OllamaClient())
    )
    use_case.execute(video, out_dir, vision_model, intervalo)
    return notes_path if notes_path.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--model", default="gemma4:e4b")
    ap.add_argument("--intervalo", type=int, default=INTERVALO_SEG)
    args = ap.parse_args()

    if not args.video.exists():
        print(f"ERROR: no existe {args.video}", file=sys.stderr)
        return 1
    analizar_visual(args.video, args.out_dir, args.model, args.intervalo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
