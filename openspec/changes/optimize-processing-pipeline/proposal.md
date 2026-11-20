## Why

El procesamiento gasta la mayor parte del tiempo en trabajo evitable: el análisis visual describe un frame cada 15 s aunque la pantalla no haya cambiado, Whisper transcribe en serie pudiendo ir por lotes, y el flujo de progreso relee y reenvía `sessions.json` cada segundo a cada cliente aunque nada cambie. Además, los avisos que explican una salida dudosa (contexto truncado, audio recuperado parcialmente, frames no extraídos) solo se imprimen en consola y el usuario nunca los ve.

## What Changes

- **Análisis visual**: se descartan los frames casi idénticos al último analizado (firma de 32×32 en gris vía ffmpeg, sin dependencias nuevas), garantizando al menos un frame cada cierto intervalo. Umbral configurable; `0` lo desactiva.
- **Transcripción**: modo por lotes opcional (`BatchedInferencePipeline` de faster-whisper 1.2.1, ya instalado) activado con `WHISPER_BATCH_SIZE`; glosario opcional de términos propios (`glossary.txt`) pasado como `hotwords`; el idioma `auto` se traduce a detección automática (hoy se pasa la cadena `"auto"` tal cual a Whisper).
- **Progreso**: el SSE `/api/progress` envía una instantánea al conectar y después solo cuando el almacén cambia; latido cada 15 s.
- **Avisos**: cada video acumula `warnings` (persistidos y expuestos en la API) con los avisos de truncado de contexto, audio parcial y fallo de extracción de frames.
- **Refactor sin cambio de comportamiento**: `ProcessVideoUseCase.execute` (~110 líneas, `task: dict`) se divide en pasos con un `ProcessingTask` tipado; `GET /api/health` deja de bloquear el event loop.

Fuera de este change: reordenar el prompt REDUCE para reutilizar la caché de Ollama. La ganancia estimada es de segundos por video y cambia la salida del modelo; no compensa sin medición.

## Capabilities

### New Capabilities
- `transcription`: modo por lotes, glosario e idioma automático.
- `progress-stream`: emisión del progreso por cambios con latido.
- `processing-warnings`: avisos por video persistidos y expuestos.

### Modified Capabilities
- `visual-analysis`: se añade la deduplicación de frames.

## Impact

- Código: `pipeline/domain/videos/` (nuevo `frame_selection.py`; `video.py`), `pipeline/application/visual_analysis/`, `pipeline/application/processing/process_video.py`, `pipeline/application/shared/` (nuevo `warning_collector.py`), `pipeline/infrastructure/visual_analysis/` (nuevo `ffmpeg_frame_signature_extractor.py`), `pipeline/infrastructure/transcription/`, `pipeline/infrastructure/ollama/ollama_client.py`, `pipeline/infrastructure/persistence/json/` (gateway + mappers), `pipeline/presentation/` (nuevo `routes/progress_routes.py`, `composition_root.py`), `pipeline/server.py`, `pipeline/shared/config.py`.
- API: los videos devueltos por `/api/sessions*` y por el SSE ganan `warnings: string[]`. Sin cambios incompatibles.
- Dependencias: ninguna nueva.
- Valores por defecto conservadores: el modo por lotes queda **apagado** y el umbral de deduplicación se fija tras calibrar con una grabación real (tareas de medición incluidas). Nada de esto está medido todavía.
- Requiere `fix-stability-and-local-security` aplicado.
