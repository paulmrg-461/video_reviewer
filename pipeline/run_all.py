"""
run_all.py — Orquesta el pipeline completo sobre todos los videos.

Por cada videos/*.mp4:
  1) transcribe  -> output/<slug>/transcript.{txt,srt}
  2) summarize   -> output/<slug>/{summary.md, rules.md}

Reanudable: si una salida ya existe, la salta.

Uso (vía wrapper):  ./pipeline/run.sh
O directo:          python pipeline/run_all.py [--only SUBSTR] [--skip-summary]
"""
import argparse
import re
import time
from pathlib import Path

from transcribe import transcribir
from summarize import resumir

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT / "videos"
OUT_DIR = ROOT / "output"


def slug(nombre: str) -> str:
    s = re.sub(r"\.mp4$", "", nombre)
    s = re.sub(r"[^\w\-]+", "_", s)
    return s.strip("_")


def liberar_ollama(modelo: str) -> None:
    """Descarga el modelo de Ollama de la VRAM (keep_alive=0) para dejar sitio a whisper."""
    import subprocess
    try:
        subprocess.run(["ollama", "stop", modelo], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  (ollama stop {modelo}: VRAM liberada)")
    except FileNotFoundError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="procesa solo videos cuyo nombre contenga este texto")
    ap.add_argument("--whisper-model", default="large-v3")
    ap.add_argument("--llm-model", default="qwen2.5:14b")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="int8_float16")
    ap.add_argument("--skip-summary", action="store_true")
    ap.add_argument("--skip-transcribe", action="store_true")
    args = ap.parse_args()

    videos = sorted(VIDEOS_DIR.glob("*.mp4"))
    if args.only:
        videos = [v for v in videos if args.only in v.name]
    if not videos:
        print("No hay videos que procesar.")
        return 1

    print(f"{len(videos)} video(s) a procesar.\n")
    t0 = time.time()

    # FASE 1 — Transcripción (solo whisper en VRAM).
    # Se separa de la fase 2 porque whisper (~3GB) + qwen2.5:14b (~9GB) no
    # caben juntos en 12GB; correrlos a la vez da CUDA out of memory.
    if not args.skip_transcribe:
        print("===== FASE 1: transcripción (GPU: whisper) =====")
        liberar_ollama(args.llm_model)  # descarga el LLM de VRAM si quedó residente
        for i, video in enumerate(videos, 1):
            out = OUT_DIR / slug(video.name)
            print(f"[{i}/{len(videos)}] {video.name}  ->  output/{out.name}/")
            tv = time.time()
            try:
                transcribir(video, out, args.whisper_model, args.device,
                            args.compute_type, language="es")
            except Exception as exc:
                print(f"  ✗ ERROR transcribiendo {video.name}: {exc}")
            print(f"  ({(time.time()-tv)/60:.1f} min)\n")

    # FASE 2 — Resumen/extracción (solo qwen en VRAM).
    if not args.skip_summary:
        print("===== FASE 2: resumen + reglas (GPU: qwen2.5:14b) =====")
        for i, video in enumerate(videos, 1):
            out = OUT_DIR / slug(video.name)
            print(f"[{i}/{len(videos)}] {video.name}")
            tv = time.time()
            try:
                resumir(out, args.llm_model, nombre=video.stem)
            except Exception as exc:
                print(f"  ✗ ERROR resumiendo {video.name}: {exc}")
            print(f"  ({(time.time()-tv)/60:.1f} min)\n")

    print(f"==== LISTO en {(time.time()-t0)/60:.1f} min. Salidas en output/ ====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
