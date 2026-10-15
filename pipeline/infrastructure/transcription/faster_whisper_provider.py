"""faster-whisper-backed transcription adapter.

Ports the `WhisperModel(...)` load + `.transcribe(...)` + segment-building
loop that used to live inline in `pipeline/transcribe.py`'s `transcribir()`.
Builds `Segment`/`Transcript` domain objects instead of writing files
directly — file writing is the use case's job (`TranscribeVideoUseCase`).
"""
from __future__ import annotations

from pathlib import Path

from pipeline.domain.videos.transcript import Segment, Transcript


class FasterWhisperProvider:
    def transcribe(
        self,
        audio: Path,
        language: str,
        model_name: str,
        device: str,
        compute_type: str,
    ) -> Transcript:
        # Kept as a local import (not module top) to preserve the
        # lazy-GPU-load / fast-startup behavior of the original code —
        # confirmed load-bearing in every prior step of this migration.
        from faster_whisper import WhisperModel

        print(f"  cargando modelo {model_name} ({device}/{compute_type})")
        model = WhisperModel(model_name, device=device, compute_type=compute_type)

        print("  transcribiendo (VAD activo)...")
        segments_iter, info = model.transcribe(
            str(audio),
            language=language,
            vad_filter=True,
            beam_size=5,
            # Whisper loops / invents text ("Subtítulos por...") in silence or
            # noise, and conditioning on previous text propagates it.
            condition_on_previous_text=False,
            temperature=0.0,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            hallucination_silence_threshold=2.0,
            word_timestamps=True,
        )
        print(f"  idioma={info.language} prob={info.language_probability:.2f} "
              f"dur={info.duration/60:.1f}min")

        segments: list[Segment] = []
        for i, seg in enumerate(segments_iter, start=1):
            text = seg.text.strip()
            if _is_repeat(text, segments):
                continue
            segments.append(Segment(start=seg.start, end=seg.end, text=text))
            if i % 50 == 0:
                print(f"    ...{i} segmentos ({seg.end/60:.1f}min)")

        return Transcript(segments=tuple(segments), language=info.language)


def _is_repeat(text: str, previous: list[Segment], window: int = 3) -> bool:
    """Drop empty segments and verbatim repeats of the last few segments
    (classic Whisper hallucination loop)."""
    if not text:
        return True
    return any(seg.text == text for seg in previous[-window:])
