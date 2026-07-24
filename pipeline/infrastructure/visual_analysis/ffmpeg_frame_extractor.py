"""ffmpeg-based frame extraction adapter.

Ports `pipeline/visual.py`'s original `extraer_frames()` verbatim.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class FfmpegFrameExtractor:
    def extract_frames(self, video: Path, out_dir: Path, interval_seconds: int) -> list[Path]:
        """ffmpeg: 1 frame cada `interval_seconds` segundos ->
        out_dir/frame_00001.jpg, ..."""
        out_dir.mkdir(parents=True, exist_ok=True)
        pattern = out_dir / "frame_%05d.jpg"
        cmd = [
            "ffmpeg", "-y", "-i", str(video),
            "-vf", f"fps=1/{interval_seconds}",
            "-q:v", "3",
            str(pattern),
        ]
        subprocess.run(cmd, capture_output=True, text=True)
        return sorted(out_dir.glob("frame_*.jpg"))
