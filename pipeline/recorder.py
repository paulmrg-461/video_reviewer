"""recorder.py — Control de gpu-screen-recorder para grabación de pantalla bajo demanda.

Captura video (portal: selector nativo de pantalla/ventana) + audio mezclado
(salida del sistema, para voces de reunión + micrófono propio).
"""
import shutil
import signal
import subprocess
import time
from pathlib import Path

MIN_FREE_BYTES = 2 * 1024**3
STARTUP_GRACE_SECONDS = 1.5


class RecorderError(Exception):
    """Recorder could not start (no disk space, process died on launch)."""

AUDIO_INPUT = "default_output|default_input"


def iniciar(output: Path, capture: str = "portal", codec: str = "h264") -> subprocess.Popen:
    """Lanza gpu-screen-recorder grabando a `output`. Devuelve el proceso (sigue corriendo)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < MIN_FREE_BYTES:
        raise RecorderError("Espacio en disco insuficiente (mínimo 2 GB libres)")
    cmd = [
        "gpu-screen-recorder",
        "-w", capture,
        "-a", AUDIO_INPUT,
        "-k", codec,
        "-o", str(output),
    ]
    # Never PIPE without draining: a full pipe blocks the recorder, it then
    # ignores SIGINT and the mp4 is never finalized (stop hangs / 500).
    log_path = output.with_suffix(".log")
    with log_path.open("wb") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log)
    time.sleep(STARTUP_GRACE_SECONDS)
    if proc.poll() is not None:
        raise RecorderError(f"gpu-screen-recorder terminó al iniciar: {_log_tail(log_path)}")
    return proc


def _log_tail(log_path: Path, lines: int = 3) -> str:
    try:
        text = log_path.read_text(errors="replace").strip().splitlines()
    except OSError:
        return "sin log"
    return " | ".join(text[-lines:]) or "sin salida"


def esta_vivo(proc: subprocess.Popen) -> bool:
    return proc.poll() is None


def detener(proc: subprocess.Popen, timeout: float = 45.0) -> bool:
    """SIGINT para que gpu-screen-recorder finalice el mp4 limpiamente. True si cerró ok."""
    if proc.poll() is not None:
        return True
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return False
