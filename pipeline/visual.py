"""visual.py — Extrae frames de un video y los analiza con un modelo de visión vía Ollama.

Salida:
  <out_dir>/visual_notes.md   (una descripción por frame, con timestamp)

Uso:
  python visual.py <video.mp4> <out_dir> [--model gemma4:e4b] [--intervalo 15]

Variables de entorno:
  VISUAL_FRAME_INTERVAL_SEG   segundos entre frames muestreados (default: 15)
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"
INTERVALO_SEG = int(os.environ.get("VISUAL_FRAME_INTERVAL_SEG", "15"))

PROMPT_FRAME = (
    "Esta es una captura de pantalla tomada durante una grabación de escritorio/reunión. "
    "Describe en viñetas cortas: qué aplicación o ventana está activa, qué texto o datos "
    "relevantes son visibles, y qué está ocurriendo en pantalla. No inventes texto que no "
    "puedas leer con claridad. Si la pantalla está vacía o sin contenido relevante, dilo "
    "brevemente en una línea."
)


def _fmt_ts(segundos: float) -> str:
    """Segundos -> 'HH:MM:SS'."""
    s = int(segundos)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def extraer_frames(video: Path, out_dir: Path, intervalo: int = INTERVALO_SEG) -> list[Path]:
    """ffmpeg: 1 frame cada `intervalo` segundos -> out_dir/frame_00001.jpg, ..."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "frame_%05d.jpg"
    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-vf", f"fps=1/{intervalo}",
        "-q:v", "3",
        str(pattern),
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    return sorted(out_dir.glob("frame_*.jpg"))


def _describir_frame(model: str, frame: Path) -> str:
    b64 = base64.b64encode(frame.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT_FRAME, "images": [b64]}],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["message"]["content"].strip()


def analizar_visual(video: Path, out_dir: Path, vision_model: str = "gemma4:e4b",
                    intervalo: int = INTERVALO_SEG) -> Path | None:
    """Extrae frames y genera <out_dir>/visual_notes.md. Devuelve None si no hay frames."""
    notes_path = out_dir / "visual_notes.md"
    if notes_path.exists():
        print(f"  [skip] notas visuales ya existen en {out_dir}")
        return notes_path

    with tempfile.TemporaryDirectory() as tmp:
        print(f"  extrayendo frames cada {intervalo}s...")
        frames = extraer_frames(video, Path(tmp), intervalo)
        if not frames:
            print("  (sin frames extraídos, se omite análisis visual)")
            return None

        print(f"  {len(frames)} frames a analizar con {vision_model}")
        lines = []
        for i, frame in enumerate(frames):
            ts = _fmt_ts(i * intervalo)
            print(f"    VISION frame {i + 1}/{len(frames)} [{ts}]")
            try:
                desc = _describir_frame(vision_model, frame)
            except Exception as exc:
                desc = f"(error analizando frame: {exc})"
            lines.append(f"### [{ts}]\n{desc}")

        notes_path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
        print(f"  ✓ {notes_path.name} ({len(frames)} frames)")
        return notes_path


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
