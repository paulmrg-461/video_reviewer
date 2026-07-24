"""Use case: transcribe a video's audio track.

Ports the orchestration that used to live inline in
`pipeline/transcribe.py`'s `transcribir()`: skip-if-both-outputs-exist,
extract audio into a temp wav, run the transcription provider, then write
`transcript.txt`/`transcript.srt` via the `Transcript` domain object's
`plain_text()`/`to_srt()` (already unit-tested in Step 1 to match today's
exact byte format).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from pipeline.application.transcription.ports import (
    AudioExtractionPort,
    TranscriptionProvider,
)
from pipeline.domain.videos.transcript import Transcript


class TranscribeVideoUseCase:
    def __init__(
        self,
        audio_extractor: AudioExtractionPort,
        provider: TranscriptionProvider,
    ) -> None:
        self._audio_extractor = audio_extractor
        self._provider = provider

    def execute(
        self,
        video: Path,
        out_dir: Path,
        model_name: str,
        device: str,
        compute_type: str,
        language: str = "es",
    ) -> Transcript | None:
        out_dir.mkdir(parents=True, exist_ok=True)
        txt_path = out_dir / "transcript.txt"
        srt_path = out_dir / "transcript.srt"

        if txt_path.exists() and srt_path.exists():
            print(f"  [skip] transcripción ya existe en {out_dir}")
            return None

        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            print(f"  extrayendo audio -> {wav.name}")
            self._audio_extractor.extract(video, wav)

            transcript = self._provider.transcribe(
                wav, language, model_name, device, compute_type
            )

        txt_path.write_text(transcript.plain_text(), encoding="utf-8")
        srt_path.write_text(transcript.to_srt(), encoding="utf-8")
        print(f"  ✓ {txt_path.name} ({len(transcript.segments)} segmentos)  +  {srt_path.name}")

        return transcript
