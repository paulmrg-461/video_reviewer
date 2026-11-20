Requisito previo: `fix-stability-and-local-security` aplicado y archivado. Tests: `.venv/bin/python -m pytest pipeline/tests -q`.

## 1. Preparación

- [ ] 1.1 Rama `feature/optimize-processing-pipeline` desde `develop`; suite en verde; anotar el total

## 2. Refactor de ProcessVideoUseCase, sin cambio de comportamiento (design D1)

- [ ] 2.1 Tests nuevos en `pipeline/tests/application/test_process_video_use_case.py` solo para `ProcessingTask.from_dict`: valores por defecto; claves desconocidas ignoradas; `frame_interval` ausente → `None`
- [ ] 2.2 Añadir `ProcessingTask` y dividir `execute` en `_load_video`, `_prepare_output`, `_transcribe`, `_analyze_visual`, `_summarize`, `_finish` (≤ 20 líneas cada uno). **No modificar ningún test existente**: si alguno falla, el refactor cambió el comportamiento → corregir el código, no el test
- [ ] 2.3 Suite en verde con el mismo total + los tests de 2.1

## 3. Deduplicación de frames (design D2)

- [ ] 3.1 Tests en `pipeline/tests/domain/test_frame_selection.py`: `frame_difference(b"\x00"*4, b"\x0a"*4) == 10.0`; longitudes distintas → `ValueError`; y los escenarios "Pantalla estática", "Cambio de pantalla", "Cambio gradual", "Intervalo máximo" y "Desactivada" (umbral 0 → todos los índices) de `specs/visual-analysis/spec.md`; lista vacía → `[]`
- [ ] 3.2 Implementar `pipeline/domain/videos/frame_selection.py`
- [ ] 3.3 Tests en `pipeline/tests/infrastructure/test_ffmpeg_frame_signature_extractor.py` con `monkeypatch` de `subprocess.run`: 3072 bytes → 3 firmas; 2500 bytes → 2 firmas; `returncode=1` → `FrameExtractionError`; el comando contiene `fps=1/15,scale=32:32,format=gray` y `rawvideo`
- [ ] 3.4 Añadir `FrameSignaturePort` a `pipeline/application/visual_analysis/ports.py` e implementar `pipeline/infrastructure/visual_analysis/ffmpeg_frame_signature_extractor.py`
- [ ] 3.5 Tests en `pipeline/tests/application/test_analyze_visual_use_case.py`: con `dedup` y firmas `[A, A, A, B, B]` solo se describen los frames 0 y 3 y `visual_notes.md` contiene `### [00:00:00]` y `### [00:00:45]` (intervalo 15); sin `dedup` se describen todos (tests existentes intactos); nº de firmas distinto al de frames → se describen todos; firmas que lanzan `FrameExtractionError` → se describen todos; umbral 0 → no se llama a `signatures`
- [ ] 3.6 Implementar `FrameDedup` y la selección en `AnalyzeVisualUseCase` (extraer `_indexes_to_describe(video, frames, interval)`)
- [ ] 3.7 `pipeline/shared/config.py`: `VISUAL_DEDUP_THRESHOLD` (por defecto `0`), `VISUAL_MAX_GAP_FRAMES`. `composition_root.py`: construir `FrameDedup(FfmpegFrameSignatureExtractor(), DedupPolicy(...))` y pasarlo a `AnalyzeVisualUseCase`
- [ ] 3.8 **Calibración (pedir al usuario una grabación real de pantalla de ≥ 10 min).** Escribir en el scratchpad (no en el repo) un script que obtenga las firmas con el adaptador e imprima, para umbrales 1, 2, 3, 5 y 8, cuántos frames se conservarían de cuántos, y la lista de diferencias consecutivas ordenada. Pegar la salida aquí debajo. Proponer al usuario un umbral por defecto y **esperar su respuesta** antes de cambiar el valor por defecto en `config.py`. Si el usuario no responde, dejar `0`
- [ ] 3.9 Suite en verde

## 4. Transcripción: idioma auto, lotes y glosario (design D3)

- [ ] 4.1 Tests en `pipeline/tests/infrastructure/test_faster_whisper_provider.py` (archivo nuevo). Sustituir `_load_model` y `_batched` del proveedor con `monkeypatch` por fakes que registran `kwargs` y devuelven `(iter([seg...]), info)` donde `seg` e `info` son `types.SimpleNamespace`. Casos: los escenarios de "Idioma automático", "Transcripción por lotes opcional" y el filtro de repeticiones de `specs/transcription/spec.md`; `hotwords` configurado llega al modelo en ambos modos
- [ ] 4.2 Refactorizar `FasterWhisperProvider`: `WhisperOptions`, `_load_model`, `_batched`, `_decode_options(language)`; `transcribe` ≤ 20 líneas (extraer `_collect_segments(segments_iter)`)
- [ ] 4.3 Tests en `pipeline/tests/infrastructure/test_glossary.py`: los tres escenarios de "Glosario de términos propios"; archivo solo con comentarios → `None`
- [ ] 4.4 Implementar `pipeline/infrastructure/transcription/glossary.py`
- [ ] 4.5 `config.py`: `WHISPER_BATCH_SIZE` (por defecto `0`), `GLOSSARY_FILE`. `composition_root.py`: `FasterWhisperProvider(WhisperOptions(WHISPER_BATCH_SIZE, load_hotwords(GLOSSARY_FILE)))`
- [ ] 4.6 Crear `glossary.example.txt` en la raíz (comentarios de uso + 5 términos de ejemplo genéricos) y añadir `/glossary.txt` a `.gitignore`
- [ ] 4.7 Suite en verde
- [ ] 4.8 **Medición (pedir al usuario un audio/video real de ≥ 10 min).** Transcribirlo dos veces borrando antes solo los `transcript.*` de una carpeta de prueba creada para ello (nunca de una sesión real): con `WHISPER_BATCH_SIZE=0` y con `=8`. Anotar aquí: segundos de cada modo, VRAM máxima (`nvidia-smi --query-gpu=memory.used --format=csv -l 1` en otra terminal), nº de palabras de cada transcripción y un `diff` resumido. Presentar los datos al usuario y **esperar su decisión** sobre el valor por defecto. Si falla por memoria con 8, repetir con 4

## 5. Progreso por cambios (design D4)

- [ ] 5.1 Tests en `test_sessions_json_gateway.py` (o `test_json_repositories.py`): `revision` aumenta tras `create_session`, `update_video`, `remove_video`, `delete_session`; no cambia tras `list_sessions`/`get_session`
- [ ] 5.2 Implementar `_revision` y la propiedad `revision` en `SessionsJsonGateway`
- [ ] 5.3 Tests en `pipeline/tests/presentation/test_progress_routes.py` con una fuente falsa (`revision` mutable, `snapshot()` devuelve una lista) e `interval=0`: primer elemento es `data: ...`; sin cambios durante 5 iteraciones no hay más `data:`; al cambiar `revision` llega un `data:` nuevo; tras 15 iteraciones sin cambios llega `: ping\n\n`; cuando `is_disconnected()` devuelve `True` el generador termina. Consumir con un helper que tome N elementos y haga `aclose()`
- [ ] 5.4 Implementar `pipeline/presentation/routes/progress_routes.py` (`ProgressSource`, `progress_events`, `_GatewaySource`, router con `GET /api/progress`); borrar la ruta de `server.py` e incluir el router nuevo
- [ ] 5.5 Suite en verde

## 6. Avisos por video (design D5)

- [ ] 6.1 Tests en `pipeline/tests/domain/test_video.py`: `add_warning` añade; ignora vacío y duplicado; tope de 10; `requeue()` vacía `warnings`
- [ ] 6.2 Implementar en `pipeline/domain/videos/video.py`
- [ ] 6.3 Tests de mappers en `test_json_repositories.py`: ida y vuelta de `warnings`; dict sin la clave → `[]`
- [ ] 6.4 Implementar en `pipeline/infrastructure/persistence/json/mappers.py`; añadir `"warnings"` al dict construido en `add_video` (`videos_routes.py`)
- [ ] 6.5 Tests en `pipeline/tests/application/test_warning_collector.py`: `add` + `drain` devuelve en orden y vacía; `drain` sin avisos → `[]`
- [ ] 6.6 Implementar `pipeline/application/shared/warning_collector.py`
- [ ] 6.7 Tests: `OllamaClient(on_warning=espía)` con respuesta `prompt_eval_count >= num_ctx - 32` → el espía recibe el texto exacto del design; sin desbordar → no se llama; sin `on_warning` → no falla. `FfmpegAudioExtractor(on_warning=espía)` en la rama de audio parcial → recibe el texto exacto (reutilizar el montaje de `test_ffmpeg_audio_extractor.py`). `AnalyzeVisualUseCase(..., on_warning=espía)` con `FrameExtractionError` → recibe el texto exacto
- [ ] 6.8 Implementar el parámetro `on_warning` en los tres componentes
- [ ] 6.9 Tests en `test_process_video_use_case.py`: escenarios de "Los avisos no se mezclan entre videos" y "Video que termina en error" de `specs/processing-warnings/spec.md`, usando un `WarningCollector` real al que un fake de resumen añade un aviso
- [ ] 6.10 Implementar el recolector en `ProcessVideoUseCase` (`drain` al inicio; volcado en `_finish` y en el `except`) y el wiring en `composition_root.py` (una instancia compartida)
- [ ] 6.11 Suite en verde

## 7. Health sin bloqueo (design D6)

- [ ] 7.1 En `pipeline/server.py`: extraer `_command_ok(cmd)` y llamar con `await asyncio.to_thread(_command_ok, [...])`. El JSON de respuesta no cambia
- [ ] 7.2 Suite en verde

## 8. Verificación final

- [ ] 8.1 Suite completa en verde; anotar el total
- [ ] 8.2 Manual: abrir la app, dejarla 30 s sin actividad con las herramientas de red del navegador abiertas → en `/api/progress` hay una instantánea inicial y luego solo `: ping`; al añadir un video llegan eventos por cada cambio de estado y la UI se actualiza igual que antes
- [ ] 8.3 Manual: procesar un video con idioma `Auto` → termina `done` y el log muestra el idioma detectado
- [ ] 8.4 Manual: procesar una grabación con análisis visual y `VISUAL_DEDUP_THRESHOLD` en el valor acordado en 3.8 → el log muestra `N de M frames tras deduplicar` con N < M; revisar `visual_notes.md` y confirmar con el usuario que no falta ningún cambio de pantalla relevante
- [ ] 8.5 Manual: `curl -s localhost:8000/api/sessions | python -m json.tool | grep -c warnings` → mayor que 0
- [ ] 8.6 Actualizar `README.md`: variables `VISUAL_DEDUP_THRESHOLD`, `VISUAL_MAX_GAP_FRAMES`, `WHISPER_BATCH_SIZE`, `VIDEO_REVIEWER_GLOSSARY`, y uso de `glossary.txt` (requiere reinicio)
- [ ] 8.7 `openspec validate optimize-processing-pipeline --strict` sin errores
