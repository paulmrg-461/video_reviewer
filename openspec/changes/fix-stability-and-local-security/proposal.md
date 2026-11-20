## Why

El servidor escucha en `0.0.0.0` sin autenticación y dos endpoints aceptan rutas arbitrarias del disco: cualquier equipo de la LAN puede leer archivos (vía `paths`) o escribir en cualquier carpeta (vía `target_dir`). Además hay cuatro defectos de robustez verificados en el código actual: `NameError` al apagar el servidor, escritura no atómica de `sessions.json`, un video borrado durante su procesamiento reaparece, y los fallos de ffmpeg al extraer frames se tragan en silencio.

## What Changes

- **BREAKING**: el servidor escucha en `127.0.0.1` por defecto. Para exponerlo a la LAN hay que exportar `VIDEO_REVIEWER_HOST=0.0.0.0` (imprime advertencia).
- **BREAKING**: `POST /api/sessions/{sid}/videos` solo acepta archivos multimedia dentro de raíces permitidas; la respuesta añade `rejected: [{path, reason}]` (antes las rutas inválidas se descartaban sin avisar).
- **BREAKING**: `POST /api/sessions/{sid}/videos/{vid}/save` rechaza con 403 destinos fuera de las raíces de exportación y con 422 nombres de archivo que no estén en la lista de artefactos exportables.
- Los parámetros de ruta `sid` y `vid` se validan contra `^[A-Za-z0-9_-]{1,64}$` en todas las rutas (422 si no cumplen).
- `pipeline/server.py`: importar `stop_recording_use_case` (hoy `NameError` en shutdown) y migrar `@app.on_event` a `lifespan`, cancelando el worker al salir.
- `SessionsJsonGateway._save`: escritura atómica (archivo temporal + `os.replace`); un `sessions.json` corrupto produce un error claro y no se sobrescribe.
- `DELETE /api/sessions/{sid}/videos/{vid}` responde 409 si el video está en proceso (hoy el worker lo vuelve a insertar al terminar).
- `FfmpegFrameExtractor`: si ffmpeg termina con error se lanza `FrameExtractionError` con el final de stderr; el caso de uso lo registra y continúa sin análisis visual.
- Frontend: `addVideos()` muestra las rutas rechazadas y su motivo.

## Capabilities

### New Capabilities
- `local-access-control`: interfaz de red por defecto, raíces permitidas de lectura y exportación, validación de ids de ruta.
- `session-store-durability`: escritura atómica y detección de corrupción de `sessions.json`.
- `server-lifecycle`: arranque y apagado limpios (worker y grabadoras).
- `video-management`: reglas de alta y baja de videos en una sesión (rechazos explícitos, no borrar en proceso).
- `visual-analysis`: comportamiento del análisis de pantalla ante fallos de extracción de frames.

### Modified Capabilities
<!-- Ninguna: openspec/specs/ está vacío. -->

## Impact

- Código: `pipeline/run.sh`, `pipeline/server.py`, `pipeline/shared/config.py`, `pipeline/application/shared/` (nuevo `path_policy.py`, `exceptions.py`), `pipeline/application/videos/use_cases.py`, `pipeline/presentation/routes/*.py` (+ nuevo `params.py`), `pipeline/presentation/composition_root.py`, `pipeline/infrastructure/persistence/json/sessions_json_gateway.py`, `pipeline/infrastructure/visual_analysis/ffmpeg_frame_extractor.py`, `pipeline/application/visual_analysis/analyze_visual.py`, `frontend/index.html` (`addVideos`).
- Tests: se actualizan `pipeline/tests/application/test_video_use_cases.py` (cambia el tipo de retorno de `AddVideosToSessionUseCase`) y se añaden tests en `pipeline/tests/application/`, `pipeline/tests/infrastructure/` y el nuevo `pipeline/tests/presentation/`.
- Dependencias: ninguna nueva.
- Usuarios: quien abra la app desde otro dispositivo de la LAN debe exportar `VIDEO_REVIEWER_HOST=0.0.0.0`. Videos fuera de `$HOME` requieren `VIDEO_REVIEWER_INPUT_ROOTS`.
