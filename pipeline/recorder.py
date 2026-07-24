"""recorder.py — Control de gpu-screen-recorder para grabación de pantalla bajo demanda.

Captura video (portal: selector nativo de pantalla/ventana) + audio mezclado
(salida del sistema, para voces de reunión + micrófono propio).
"""
import signal
import subprocess
from pathlib import Path

AUDIO_INPUT = "default_output|default_input"


def iniciar(output: Path, capture: str = "portal", codec: str = "h264") -> subprocess.Popen:
    """Lanza gpu-screen-recorder grabando a `output`. Devuelve el proceso (sigue corriendo)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gpu-screen-recorder",
        "-w", capture,
        "-a", AUDIO_INPUT,
        "-k", codec,
        "-o", str(output),
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def detener(proc: subprocess.Popen, timeout: float = 15.0) -> bool:
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
