"""
transcribe.py — Extrae audio de un video y lo transcribe con faster-whisper (GPU).

Salida por video:
  <out_dir>/transcript.txt   (texto plano)
  <out_dir>/transcript.srt   (subtítulos con timestamps)

Uso:
  python transcribe.py <video.mp4> <out_dir> [--model large-v3] [--device cuda]
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def extraer_audio(video: Path, wav: Path) -> None:
    """ffmpeg: a 16kHz mono PCM (formato óptimo para Whisper)."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _fmt_ts(segundos: float) -> str:
    """Segundos -> 'HH:MM:SS,mmm' (formato SRT)."""
    ms = int(round(segundos * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribir(video: Path, out_dir: Path, model_name: str, device: str,
                compute_type: str, language: str = "es") -> None:
    from faster_whisper import WhisperModel

    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / "transcript.txt"
    srt_path = out_dir / "transcript.srt"

    if txt_path.exists() and srt_path.exists():
        print(f"  [skip] transcripción ya existe en {out_dir}")
        return

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        print(f"  extrayendo audio -> {wav.name}")
        extraer_audio(video, wav)

        print(f"  cargando modelo {model_name} ({device}/{compute_type})")
        model = WhisperModel(model_name, device=device, compute_type=compute_type)

        print("  transcribiendo (VAD activo)...")
        segments, info = model.transcribe(
            str(wav),
            language=language,
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=True,
        )
        print(f"  idioma={info.language} prob={info.language_probability:.2f} "
              f"dur={info.duration/60:.1f}min")

        txt_lines, srt_lines = [], []
        for i, seg in enumerate(segments, start=1):
            text = seg.text.strip()
            txt_lines.append(text)
            srt_lines.append(
                f"{i}\n{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}\n{text}\n"
            )
            if i % 50 == 0:
                print(f"    ...{i} segmentos ({seg.end/60:.1f}min)")

        txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        print(f"  ✓ {txt_path.name} ({len(txt_lines)} segmentos)  +  {srt_path.name}")


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
