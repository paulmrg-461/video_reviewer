Comando de tests en todo el documento: `.venv/bin/python -m pytest pipeline/tests -q` (desde la raíz). Línea base: 105 pasan.

## 1. Preparación

- [ ] 1.1 Leer `openspec/ROADMAP.md` completo y ejecutar su "Paso 0"
- [ ] 1.2 Crear rama `feature/fix-stability-and-local-security` desde `develop`
- [ ] 1.3 Crear `pipeline/tests/presentation/__init__.py` vacío

## 2. PathPolicy (design D2, D3)

- [ ] 2.1 Crear `pipeline/application/shared/exceptions.py` con `PathNotAllowedError(Exception)` que guarda `path: str` y `reason: str` y cuyo `str()` es `f"{reason}: {path}"`
- [ ] 2.2 Escribir `pipeline/tests/application/test_path_policy.py` con `tmp_path` como raíz. Tests de `check_input_file`: archivo `.mp4` válido devuelve ruta resuelta; inexistente → `no existe`; `.txt` → `tipo de archivo no permitido`; archivo `.mp4` en otro `tmp` fuera de la raíz → `fuera de las carpetas permitidas`; `raiz/../otro/v.mp4` → `fuera de las carpetas permitidas`; symlink dentro de la raíz que apunta fuera → `fuera de las carpetas permitidas`; cadena vacía → `ruta vacía`; extensión en mayúsculas `.MP4` aceptada. Tests de `check_export_dir`: carpeta bajo raíz (exista o no) devuelve ruta y NO la crea; fuera de raíz → `fuera de las carpetas permitidas`; `raiz/.ssh` → `carpeta oculta no permitida`; ruta que es un archivo → `no es una carpeta`. Ejecutar: deben fallar por `ModuleNotFoundError`
- [ ] 2.3 Crear `pipeline/application/shared/path_policy.py` con `MEDIA_EXTENSIONS` y `PathPolicy` según design D2 (orden de reglas exacto). Cada método ≤ 20 líneas; extraer `_is_under(path, roots)` como función privada
- [ ] 2.4 Añadir a `pipeline/shared/config.py` `_roots_from_env`, `INPUT_ROOTS` y `EXPORT_ROOTS` según design D3 (añadir `import os`)
- [ ] 2.5 Tests en verde

## 3. Alta de videos con rechazos (design D4)

- [ ] 3.1 En `pipeline/tests/application/test_video_use_cases.py`: añadir un helper `_policy(tmp_path)` que devuelva `PathPolicy((tmp_path,), (tmp_path,))`; pasarla como quinto argumento en cada construcción de `AddVideosToSessionUseCase`; cambiar cada `added = asyncio.run(...)` por `result = asyncio.run(...)` y usar `result.added`; los archivos de prueba deben tener extensión `.mp4`
- [ ] 3.2 Añadir tests: ruta inexistente aparece en `result.rejected` con `reason == "no existe"`; archivo `.txt` existente → rechazado y `enqueue` no se llama; ruta `"   "` no aparece ni en `added` ni en `rejected`; el `Video` añadido tiene `original_path` igual a la ruta resuelta
- [ ] 3.3 En `pipeline/application/videos/use_cases.py`: añadir `RejectedPath`, `AddVideosResult`, el parámetro `path_policy` y la lógica de D4. Extraer la creación del video a `_build_video(...)` y el dict de la tarea a `_task_for(video, ...)` para dejar `execute` ≤ 20 líneas
- [ ] 3.4 En `pipeline/presentation/composition_root.py`: crear `_path_policy = PathPolicy(INPUT_ROOTS, EXPORT_ROOTS)` (importar desde `pipeline.shared.config`) y pasarlo a `AddVideosToSessionUseCase`
- [ ] 3.5 En `pipeline/presentation/routes/videos_routes.py` `add_video`: usar `result.added` y devolver `{"added": [...], "rejected": [{"path": r.path, "reason": r.reason} for r in result.rejected]}`
- [ ] 3.6 Buscar otros llamadores: `grep -rn "add_videos_use_case\|AddVideosToSessionUseCase" pipeline/ --include=*.py` y adaptar cada uno (p. ej. `run_all.py` o rutas de grabación) al nuevo retorno
- [ ] 3.7 Tests en verde

## 4. Exportación segura (design D5)

- [ ] 4.1 Añadir a `pipeline/application/videos/exceptions.py` `InvalidArtifactNameError(Exception)` con atributo `name` y `VideoBusyError(Exception)` con `session_id`, `video_id`
- [ ] 4.2 Tests en `test_video_use_cases.py` para `SaveArtifactsUseCase`: destino bajo raíz copia y devuelve rutas; destino fuera de raíz lanza `PathNotAllowedError` y no crea el directorio; `files=["summary.md", "../../x"]` lanza `InvalidArtifactNameError` y **no copia `summary.md`**; destino `raiz/.oculta` lanza `PathNotAllowedError`. Actualizar los tests existentes de este caso de uso para pasar la política
- [ ] 4.3 Implementar en `SaveArtifactsUseCase`: constante de módulo `EXPORTABLE_FILES`, tercer parámetro de constructor `path_policy`, validación de nombres antes de cualquier copia, `check_export_dir` antes de `mkdir`
- [ ] 4.4 `composition_root.py`: pasar `_path_policy` a `SaveArtifactsUseCase`
- [ ] 4.5 `videos_routes.py` `save_output`: capturar `PathNotAllowedError` → `HTTPException(403, f"Destino no permitido: {exc.reason}")`; `InvalidArtifactNameError` → `HTTPException(422, f"Archivo no exportable: {exc.name}")`
- [ ] 4.6 Tests en verde

## 5. Validación de ids (design D6)

- [ ] 5.1 Crear `pipeline/presentation/routes/params.py` con `ID_PATTERN`, `SessionIdParam`, `VideoIdParam`
- [ ] 5.2 Escribir `pipeline/tests/presentation/test_route_params.py`: construir una `FastAPI()` mínima que incluya `videos_routes.router` y usar `fastapi.testclient.TestClient`. Casos: `GET /api/sessions/%2e%2e/videos/%2e%2e/transcript` → 422; `GET /api/sessions/abcdef123456/videos/abcdef123456/transcript` → 404; `GET /api/sessions/a.b/videos/x/summary` → 422
- [ ] 5.3 Reemplazar `sid: str` → `sid: SessionIdParam` y `vid: str` → `vid: VideoIdParam` en todas las funciones de `sessions_routes.py`, `videos_routes.py` y `recording_routes.py`. No tocar `rid`
- [ ] 5.4 Tests en verde

## 6. No borrar en proceso (design D9)

- [ ] 6.1 Tests en `test_video_use_cases.py`: un video en `TRANSCRIBING` → `DeleteVideoUseCase.execute` lanza `VideoBusyError`, el repo lo sigue teniendo y la carpeta existe; `QUEUED`, `DONE` y `ERROR` → se borra; id inexistente → no lanza (comportamiento actual)
- [ ] 6.2 Implementar la comprobación en `DeleteVideoUseCase.execute` con una constante de módulo `_BUSY_STATUSES`
- [ ] 6.3 `videos_routes.py` `delete_video`: capturar `VideoBusyError` → `HTTPException(409, "El video se está procesando. Espera a que termine para eliminarlo.")`
- [ ] 6.4 Tests en verde

## 7. Persistencia atómica (design D8)

- [ ] 7.1 Tests en `pipeline/tests/infrastructure/test_json_repositories.py` (o archivo nuevo `test_sessions_json_gateway.py`): tras `create_session` no existe `sessions.json.tmp`; con `monkeypatch` de `os.replace` para que lance `OSError`, `sessions.json` conserva el contenido previo; archivo con `{"sessions": {` → `list_sessions()` lanza `SessionsFileCorruptError` y el archivo no cambia; archivo inexistente → `[]`
- [ ] 7.2 En `sessions_json_gateway.py`: añadir `class SessionsFileCorruptError(RuntimeError)`, reescribir `_save` (tmp + `flush` + `os.fsync` + `os.replace`) y `_load` (capturar `json.JSONDecodeError`) según D8
- [ ] 7.3 Tests en verde

## 8. Lifespan y apagado (design D7)

- [ ] 8.1 Escribir `pipeline/tests/presentation/test_server_lifecycle.py`: `from pipeline import server`; con `monkeypatch.setattr(server.stop_recording_use_case, "stop_all_recorders", espía)`; dentro de `asyncio.run`, hacer `async with server.lifespan(server.app): pass`; afirmar que el espía se llamó 1 vez y que no hubo excepción. Segundo test: capturar la tarea del worker (monkeypatch de `server.worker` por una corrutina que hace `await asyncio.Event().wait()` y registra su `asyncio.current_task()`) y afirmar `task.done()` tras salir del contexto
- [ ] 8.2 En `pipeline/server.py`: añadir `stop_recording_use_case` al import de `composition_root`; añadir `import contextlib` y `from contextlib import asynccontextmanager`; implementar `lifespan` según D7; pasar `lifespan=lifespan` a `FastAPI(...)`; borrar las funciones `startup` y `shutdown`
- [ ] 8.3 Tests en verde. Además: `cd pipeline && ../.venv/bin/python -c "import server"` no debe imprimir errores ni `DeprecationWarning` de `on_event`

## 9. Errores de ffmpeg en frames (design D10)

- [ ] 9.1 Añadir `class FrameExtractionError(RuntimeError)` a `pipeline/application/visual_analysis/ports.py`
- [ ] 9.2 Tests en `pipeline/tests/infrastructure/test_ffmpeg_frame_extractor.py`: con `monkeypatch` de `subprocess.run` devolviendo `returncode=1, stderr="l1\nl2\nInvalid data found\n"` → lanza `FrameExtractionError` cuyo mensaje contiene `Invalid data found`; con `returncode=0` → devuelve los frames. Test en `pipeline/tests/application/test_analyze_visual_use_case.py`: extractor falso que lanza `FrameExtractionError` → `execute` devuelve `None` y no existe `visual_notes.md`
- [ ] 9.3 Implementar en `ffmpeg_frame_extractor.py` (guardar el resultado de `subprocess.run`, comprobar `returncode`) y en `analyze_visual.py` (try/except alrededor de `extract_frames`)
- [ ] 9.4 Tests en verde

## 10. Host por defecto y frontend (design D1)

- [ ] 10.1 Editar `pipeline/run.sh`: añadir `HOST="${VIDEO_REVIEWER_HOST:-127.0.0.1}"`, la advertencia a stderr cuando `HOST` no sea `127.0.0.1` ni `localhost`, y usar `--host "$HOST"`. Verificar con `bash -n pipeline/run.sh`
- [ ] 10.2 En `frontend/index.html`, función `addVideos()`: tras la respuesta, si `res.rejected.length > 0` llamar `setFieldError(input, '#videoPathsError', ...)` con una línea por rechazo (`ruta — motivo`, texto pasado por `escapeHtml` si se inserta como HTML), dejar en `input.value` las rutas rechazadas separadas por salto de línea y llamar `autoGrow(input)`; el toast pasa a ser `N video(s) agregados` (tipo `success`) solo si `res.added.length > 0`, y `toast('Ninguna ruta válida', 'error')` si es 0
- [ ] 10.3 Actualizar `README.md`: sección "Seguridad y acceso" que documente `VIDEO_REVIEWER_HOST`, `VIDEO_REVIEWER_INPUT_ROOTS`, `VIDEO_REVIEWER_EXPORT_ROOTS` (separador `:`), las extensiones aceptadas y el 409 al borrar en proceso

## 11. Verificación final

- [ ] 11.1 Suite completa en verde; anotar aquí el número de tests
- [ ] 11.2 Arrancar `./pipeline/run.sh server` y comprobar con `ss -ltnp | grep 8000` que escucha en `127.0.0.1:8000`
- [ ] 11.3 Manual: añadir una ruta inexistente y un `.mp4` real → la UI muestra 1 agregado y 1 rechazado con motivo
- [ ] 11.4 Manual: `curl -s -X POST localhost:8000/api/sessions/<sid>/videos/<vid>/save -H 'Content-Type: application/json' -d '{"target_dir":"/etc/x","files":["summary.md"]}'` → 403 y `/etc/x` no existe
- [ ] 11.5 Manual: Ctrl+C en el servidor → sale sin traceback de `NameError`
- [ ] 11.6 `openspec validate fix-stability-and-local-security --strict` sin errores
