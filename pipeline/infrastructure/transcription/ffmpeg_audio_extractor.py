"""ffmpeg-based audio extraction adapter.

Ports `pipeline/transcribe.py`'s original `extraer_audio()` verbatim: same
3 ffmpeg strategies (1 primary + AAC-reencode fallback), same usability
check, same `RuntimeError` on total failure.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class FfmpegAudioExtractor:
    def extract(self, video: Path, wav_out: Path) -> None:
        """ffmpeg: a 16kHz mono PCM.

        Prueba 3 estrategias en orden hasta obtener audio usable.
        Si el codec está muy dañado, acepta audio parcial con advertencia."""
        def _usable(w: Path) -> bool:
            return w.exists() and w.stat().st_size >= 16_000

        def _try(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, capture_output=True, text=True)

        strategies = [
            ["ffmpeg", "-y", "-err_detect", "ignore_err", "-fflags", "+genpts+igndts",
             "-i", str(video), "-vn",
             "-af", "aformat=sample_fmts=s16:sample_rates=16000:channel_layouts=mono",
             "-c:a", "pcm_s16le", "-map_metadata", "-1",
             "-max_muxing_queue_size", "9999", str(wav_out)],
        ]

        for cmd in strategies:
            _try(cmd)
            if _usable(wav_out):
                return

        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
            tmp_m4a = Path(tmp.name)

        try:
            _try(["ffmpeg", "-y", "-err_detect", "ignore_err", "-fflags", "+genpts+igndts",
                  "-i", str(video), "-vn",
                  "-c:a", "aac", "-b:a", "256k", "-ac", "2", "-ar", "44100",
                  "-map_metadata", "-1", str(tmp_m4a)])
            if tmp_m4a.exists() and tmp_m4a.stat().st_size > 1000:
                _try(["ffmpeg", "-y", "-i", str(tmp_m4a), "-vn",
                      "-af", "aformat=sample_fmts=s16:sample_rates=16000:channel_layouts=mono",
                      "-c:a", "pcm_s16le", "-map_metadata", "-1", str(wav_out)])
        finally:
            tmp_m4a.unlink(missing_ok=True)

        if _usable(wav_out):
            print(f"  ⚠  audio parcialmente recuperado (codec dañado)")
            return

        raise RuntimeError(
            "No se pudo extraer audio. El codec de audio puede estar corrupto o ser incompatible."
        )
