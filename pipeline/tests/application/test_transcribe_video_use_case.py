"""Tests for `TranscribeVideoUseCase` (Step 5) using fake ports — no ffmpeg,
no faster-whisper involved."""
from __future__ import annotations

from pathlib import Path

from pipeline.application.transcription.transcribe_video import TranscribeVideoUseCase
from pipeline.domain.videos.transcript import Segment, Transcript


class _FakeAudioExtractor:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path]] = []

    def extract(self, video: Path, wav_out: Path) -> None:
        self.calls.append((video, wav_out))
        wav_out.write_bytes(b"fake wav bytes")


class _FakeTranscriptionProvider:
    def __init__(self, transcript: Transcript) -> None:
        self._transcript = transcript
        self.calls: list[tuple] = []

    def transcribe(self, audio, language, model_name, device, compute_type):
        self.calls.append((audio, language, model_name, device, compute_type))
        return self._transcript


def _sample_transcript() -> Transcript:
    return Transcript(
        segments=(
            Segment(start=0.0, end=1.5, text="Hola"),
            Segment(start=1.5, end=3.25, text="mundo"),
        ),
        language="es",
    )


def test_execute_writes_txt_and_srt_matching_transcript_domain_methods(tmp_path):
    transcript = _sample_transcript()
    extractor = _FakeAudioExtractor()
    provider = _FakeTranscriptionProvider(transcript)
    use_case = TranscribeVideoUseCase(extractor, provider)

    result = use_case.execute(
        tmp_path / "video.mp4", tmp_path, "large-v3", "cuda", "int8_float16", "es"
    )

    assert result is transcript
    assert (tmp_path / "transcript.txt").read_text(encoding="utf-8") == transcript.plain_text()
    assert (tmp_path / "transcript.srt").read_text(encoding="utf-8") == transcript.to_srt()
    assert len(extractor.calls) == 1
    assert provider.calls[0][1:] == ("es", "large-v3", "cuda", "int8_float16")


def test_execute_skips_when_both_outputs_already_exist(tmp_path):
    (tmp_path / "transcript.txt").write_text("ya existe\n", encoding="utf-8")
    (tmp_path / "transcript.srt").write_text("ya existe\n", encoding="utf-8")
    extractor = _FakeAudioExtractor()
    provider = _FakeTranscriptionProvider(_sample_transcript())
    use_case = TranscribeVideoUseCase(extractor, provider)

    result = use_case.execute(
        tmp_path / "video.mp4", tmp_path, "large-v3", "cuda", "int8_float16"
    )

    assert result is None
    assert extractor.calls == []  # never touched audio extraction on skip
    assert provider.calls == []


def test_execute_creates_out_dir_if_missing(tmp_path):
    out_dir = tmp_path / "nested" / "out"
    extractor = _FakeAudioExtractor()
    provider = _FakeTranscriptionProvider(_sample_transcript())
    use_case = TranscribeVideoUseCase(extractor, provider)

    use_case.execute(tmp_path / "video.mp4", out_dir, "large-v3", "cuda", "int8_float16")

    assert out_dir.exists()
    assert (out_dir / "transcript.txt").exists()
