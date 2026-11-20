## ADDED Requirements

### Requirement: Los fallos de extracción de frames son visibles y no detienen el video
Cuando ffmpeg termina con código distinto de cero al extraer frames, el extractor SHALL lanzar `FrameExtractionError` con las últimas líneas de stderr, y el caso de uso de análisis visual SHALL registrar el fallo y devolver `None` para que el video continúe sin notas de pantalla.

#### Scenario: ffmpeg falla
- **WHEN** ffmpeg devuelve `returncode` 1 con stderr `Invalid data found`
- **THEN** `FfmpegFrameExtractor.extract_frames` lanza `FrameExtractionError` cuyo mensaje contiene `Invalid data found`

#### Scenario: El video continúa
- **WHEN** el extractor lanza `FrameExtractionError` dentro de `AnalyzeVisualUseCase.execute`
- **THEN** el caso de uso devuelve `None`, no crea `visual_notes.md` y no propaga la excepción

#### Scenario: ffmpeg correcto
- **WHEN** ffmpeg devuelve `returncode` 0
- **THEN** se devuelve la lista ordenada de `frame_*.jpg` como hasta ahora
