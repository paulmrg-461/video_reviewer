## Why

Hoy el usuario solo obtiene un resumen y un análisis fijos por grabación; para cualquier otra pregunta ("¿qué se acordó sobre el presupuesto?", "¿en qué minuto se habló de X?") debe releer la transcripción. Un chat sobre la grabación responde esas preguntas con cita de tiempo, usando el modelo local ya instalado.

## What Changes

- Nueva pestaña **Chat** en el panel de detalle de cada video terminado: preguntas en lenguaje natural, respuesta en streaming, citas `[HH:MM:SS]` que saltan al momento de la transcripción.
- Nuevos endpoints: `GET`, `POST` (streaming `text/event-stream`) y `DELETE` en `/api/sessions/{sid}/videos/{vid}/chat`.
- Historial persistido por video en `sessions/<sid>/<vid>/chat.json`.
- Construcción de contexto con presupuesto de palabras: transcripción completa con tiempos si cabe; si no, resumen + análisis + fragmentos elegidos por palabras clave de la pregunta.
- Nuevo candado de GPU compartido entre el worker de procesamiento y el chat: nunca corren a la vez. El chat responde 409 si la GPU está procesando.
- `GET /api/health` añade `gpu_owner` (`null`, `"processing"` o `"chat"`).
- Nuevo cliente de streaming para Ollama basado en `httpx` (ya instalado). El `OllamaClient` existente no cambia.
- `Transcript` gana `from_srt()` y `timed_lines()`.

## Capabilities

### New Capabilities
- `recording-chat`: conversación con streaming sobre una grabación, contexto acotado, citas de tiempo, historial.
- `gpu-arbitration`: exclusión mutua de la GPU entre procesamiento y chat, y su exposición en health.

### Modified Capabilities
<!-- Ninguna. -->

## Impact

- Código nuevo: `pipeline/domain/chat/`, `pipeline/application/chat/`, `pipeline/application/gpu/gpu_lock.py`, `pipeline/infrastructure/chat/`, `pipeline/presentation/routes/chat_routes.py`.
- Código modificado: `pipeline/domain/videos/transcript.py`, `pipeline/presentation/composition_root.py` (wiring + `worker()`), `pipeline/server.py` (router + health), `pipeline/shared/config.py` (`CHAT_MODEL`), `frontend/index.html` (pestaña, vista de chat, `parseSrtHtml`).
- Dependencias: ninguna nueva (`httpx` 0.28.1 ya está en `.venv`).
- GPU: el chat usa el mismo modelo que el resumen (`qwen2.5:14b`, `num_ctx` 16384, combinación ya usada en REDUCE). No se descarga nada.
- Requiere el change `fix-stability-and-local-security` aplicado (usa `SessionIdParam`/`VideoIdParam` y `lifespan`).
