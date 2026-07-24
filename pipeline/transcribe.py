"""
transcribe.py — Extrae audio de un video y lo transcribe con faster-whisper (GPU).

Salida por video:
  <out_dir>/transcript.txt   (texto plano)
  <out_dir>/transcript.srt   (subtítulos con timestamps)

Uso:
  python transcribe.py <video.mp4> <out_dir> [--model large-v3] [--device cuda]

Nota de arquitectura (Step 5 de la migración hexagonal): este módulo es un
shim delgado. La lógica real vive en:
  - pipeline.infrastructure.transcription.ffmpeg_audio_extractor.FfmpegAudioExtractor
  - pipeline.infrastructure.transcription.faster_whisper_provider.FasterWhisperProvider
  - pipeline.application.transcription.transcribe_video.TranscribeVideoUseCase
`transcribir()` conserva exactamente la misma firma y comportamiento de cara
a `server.py` y `run_all.py` (ambos siguen haciendo `from transcribe import
transcribir` sin ningún cambio).
"""
import argparse
import sys
from pathlib import Path

# This module is imported both as `from transcribe import transcribir` with
# cwd=pipeline/ (server.py, run_all.py, both via run.sh) and run directly as
# `python transcribe.py ...` (its own documented CLI usage) — in both cases
# only pipeline/'s own directory ends up on sys.path, not the repo root that
# the `pipeline.*` absolute imports below need. Mirrors the same fix already
# applied in server.py.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.application.transcription.transcribe_video import TranscribeVideoUseCase
from pipeline.infrastructure.transcription.faster_whisper_provider import (
    FasterWhisperProvider,
)
from pipeline.infrastructure.transcription.ffmpeg_audio_extractor import (
    FfmpegAudioExtractor,
)


def extraer_audio(video: Path, wav: Path) -> None:
    """ffmpeg: a 16kHz mono PCM. Ver `FfmpegAudioExtractor.extract` para la
    implementación real (3 estrategias con fallback de codec dañado)."""
    FfmpegAudioExtractor().extract(video, wav)


def transcribir(video: Path, out_dir: Path, model_name: str, device: str,
                compute_type: str, language: str = "es") -> None:
    use_case = TranscribeVideoUseCase(FfmpegAudioExtractor(), FasterWhisperProvider())
    use_case.execute(video, out_dir, model_name, device, compute_type, language)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="int8_float16")
    ap.add_argument("--language", default="es")
    args = ap.parse_args()

    if not args.video.exists():
        print(f"ERROR: no existe {args.video}", file=sys.stderr)
        return 1
    transcribir(args.video, args.out_dir, args.model, args.device,
                args.compute_type, args.language)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
