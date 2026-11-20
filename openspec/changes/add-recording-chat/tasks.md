Requisito previo: change `fix-stability-and-local-security` aplicado y archivado. Tests: `.venv/bin/python -m pytest pipeline/tests -q`.

Estilo de tests: fakes escritos a mano (ver `pipeline/tests/application/test_summarize_video_use_case.py`), `asyncio.run(...)` para código async, `tmp_path` para disco. Para consumir un generador asíncrono en un test: `async def _collect(agen): return [x async for x in agen]` y `asyncio.run(_collect(...))`.

## 1. Preparación

- [ ] 1.1 Rama `feature/add-recording-chat` desde `develop`; suite en verde
- [ ] 1.2 Crear paquetes vacíos: `pipeline/domain/chat/__init__.py`, `pipeline/application/chat/__init__.py`, `pipeline/infrastructure/chat/__init__.py`

## 2. Dominio: SRT → transcripción con tiempos (design D2)

- [ ] 2.1 Tests en `pipeline/tests/domain/test_transcript.py`: `from_srt(t.to_srt()).segments == t.segments` con 3 segmentos (tiempos `0.0–1.5`, `61.25–65.0`, `3600.0–3601.0`); bloque sin `-->` ignorado; texto en dos líneas unido con espacio; `fmt_hms(3725.9) == "01:02:05"`; `timed_lines()` produce `"[00:00:00] hola\n[00:01:01] mundo"`; SRT vacío → `segments == ()`
- [ ] 2.2 Implementar `_parse_ts`, `fmt_hms`, `Transcript.from_srt`, `Transcript.timed_lines` en `pipeline/domain/videos/transcript.py` sin modificar `plain_text`, `to_srt` ni `_fmt_ts`
- [ ] 2.3 Tests en verde

## 3. Dominio: mensajes y selección de contexto (design D2)

- [ ] 3.1 Crear `pipeline/domain/chat/message.py` con `ChatRole` y `ChatMessage`
- [ ] 3.2 Tests en `pipeline/tests/domain/test_chat_context.py`:
  `count_words("a b  c") == 3`;
  `window_segments` con 10 segmentos de 50 palabras y `max_words=120` → ventanas de 3 segmentos (150 palabras: el tercero cruza el límite y cierra la ventana) con `start`/`end` correctos — fijar el comportamiento exacto en el test y respetarlo;
  `query_terms("¿Qué se dijo del Presupuesto y la planeación?") == ["presupuesto", "planeacion"]`;
  `select_windows` incluye la única ventana con el término buscado; devuelve en orden cronológico; respeta `budget_words`; sin coincidencias devuelve ventanas equiespaciadas no vacías; lista de ventanas vacía → `[]`;
  `trim_history` conserva pares completos más recientes; presupuesto 0 → `[]`; nunca empieza por un mensaje de asistente
- [ ] 3.3 Implementar `pipeline/domain/chat/context.py` según D2. Extraer `_normalize(text)` y `_score(window_text, terms)` como privadas
- [ ] 3.4 Tests en verde

## 4. Aplicación: presupuesto, ports, prompt y constructor de contexto (design D3–D6)

- [ ] 4.1 Crear `pipeline/application/chat/budget.py` (constantes de D3) y `pipeline/application/chat/exceptions.py` (D6)
- [ ] 4.2 Crear `pipeline/application/chat/ports.py` con `ChatKey`, `ChatModelPort`, `ChatHistoryRepository`, `VideoArtifactsReader`
- [ ] 4.3 Tests en `pipeline/tests/application/test_chat_context_builder.py`: SRT de 3000 palabras → `mode == "full"` y contiene `## TRANSCRIPCIÓN`; SRT de 20000 palabras → `mode == "excerpts"`, contiene `## RESUMEN Y ANÁLISIS` y `## FRAGMENTOS DE LA TRANSCRIPCIÓN`, y `count_words(text) <= CONTEXT_BUDGET_WORDS + 20`; en `full` con notas visuales pequeñas aparece `## NOTAS DE PANTALLA`; con notas que no caben no aparece; en `excerpts` un resumen de 5000 palabras se recorta a `SUMMARY_BUDGET_WORDS`. Generar los SRT de prueba con un helper `_srt(n_segmentos, palabras_por_segmento)` basado en `Transcript.to_srt()`
- [ ] 4.4 Implementar `pipeline/application/chat/context_builder.py` (D4)
- [ ] 4.5 Tests en `pipeline/tests/application/test_chat_prompts.py`: `build_messages` devuelve primero `system`, último `user` con la pregunta, historial intermedio en orden; el `system` contiene `--- CONTENIDO (nombre) ---`, el contexto y `--- FIN CONTENIDO ---`; con `mode == "excerpts"` contiene `Solo ves el resumen`; con `full` no
- [ ] 4.6 Implementar `pipeline/application/chat/prompts.py` (D5) con el texto EXACTO del design
- [ ] 4.7 Tests en verde

## 5. Candado de GPU (design D7)

- [ ] 5.1 Tests en `pipeline/tests/application/test_gpu_lock.py`: `try_acquire("chat")` → `True` y `owner == "chat"`; segundo `try_acquire` → `False`; `release()` → `owner is None`; `acquire("processing")` espera hasta `release()` (lanzar con `asyncio.create_task`, `await asyncio.sleep(0)`, comprobar `not task.done()`, liberar, `await task`, comprobar `owner == "processing"`)
- [ ] 5.2 Implementar `pipeline/application/gpu/gpu_lock.py`
- [ ] 5.3 Tests en verde

## 6. Aplicación: casos de uso de chat (design D8)

- [ ] 6.1 Tests en `pipeline/tests/application/test_chat_use_cases.py` con fakes `_FakeVideoRepo`, `_FakeArtifactsReader`, `_FakeHistoryRepo` (lista en memoria), `_FakeChatModel(chunks | error)`, `_FakeClock`:
  **prepare**: mensaje vacío → `InvalidChatMessageError`; 3001 caracteres → `InvalidChatMessageError`; video inexistente → `VideoNotFoundError`; video `TRANSCRIBING` → `VideoNotReadyError`; lector devuelve `None` → `VideoNotReadyError`; candado ocupado → `GpuBusyError`; caso feliz devuelve `PreparedChat` con contexto e historial recortado.
  **run**: eventos = `meta`, un `token` por fragmento, `done`; `done.message.content` == concatenación; el repo de historial recibe `[user, assistant]`; tras terminar `gpu_lock.owner is None`.
  **run con error**: modelo lanza `ChatModelError("x")` tras 1 fragmento → último evento `error`, historial vacío, candado libre.
  **run con respuesta vacía**: modelo emite solo `"  "` → evento `error`, historial vacío.
  **run con candado ocupado**: tomar el candado entre `prepare` y `run` → un solo evento `error` con `GPU ocupada`, y el candado sigue siendo del otro propietario.
  **cancelación**: consumir 1 evento y llamar `await agen.aclose()` → candado libre e historial vacío.
  **GetChatHistoryUseCase / ClearChatHistoryUseCase**: delegan en el repo
- [ ] 6.2 Implementar `pipeline/application/chat/use_cases.py` (`ChatDeps`, `PreparedChat`, tres casos de uso). `prepare` y `run` ≤ 20 líneas cada uno: extraer `_validate_message`, `_load_ready_video`, `_persist`
- [ ] 6.3 Tests en verde

## 7. Infraestructura (design D9)

- [ ] 7.1 Tests en `pipeline/tests/infrastructure/test_ollama_chat_stream.py` con `httpx.MockTransport`: respuesta NDJSON de 3 líneas (`{"message":{"content":"Ho"}}`, `{"message":{"content":"la"}}`, `{"done":true,"prompt_eval_count":10}`) → produce `["Ho","la"]`; el payload capturado tiene `stream: True`, `keep_alive: "10m"`, `options.num_ctx`, `temperature 0.0`, `seed 42` y los mensajes; línea `{"error":"model not found"}` → `ChatModelError`; status 500 → `ChatModelError`; handler que lanza `httpx.ConnectError` → `ChatModelError("No se pudo conectar con Ollama")`; líneas vacías ignoradas
- [ ] 7.2 Implementar `pipeline/infrastructure/chat/ollama_chat_stream.py`
- [ ] 7.3 Tests en `pipeline/tests/infrastructure/test_json_chat_history_repository.py`: `load` sin archivo → `[]`; `append` crea `sessions/<sid>/<vid>/chat.json` con la forma de D9; `append` + `load` ida y vuelta; con `video_id=None` usa `sessions/<sid>/chat.json`; tope de `MAX_HISTORY_MESSAGES` (añadir 202 → quedan 200, los más recientes); JSON inválido → `load` devuelve `[]`; `clear` borra el archivo y no falla si no existe; no queda `chat.json.tmp`
- [ ] 7.4 Implementar `pipeline/infrastructure/chat/json_chat_history_repository.py`
- [ ] 7.5 Tests en `pipeline/tests/infrastructure/test_filesystem_video_artifacts_reader.py`: sin `transcript.srt` → `None`; con srt y sin el resto → `summary == ""`, `analysis == ""`, `visual_notes is None`; con todo → contenidos exactos
- [ ] 7.6 Implementar `pipeline/infrastructure/chat/filesystem_video_artifacts_reader.py`
- [ ] 7.7 Tests en verde

## 8. Wiring, worker y rutas (design D7, D10)

- [ ] 8.1 `pipeline/shared/config.py`: añadir `CHAT_MODEL`
- [ ] 8.2 `pipeline/presentation/composition_root.py`: crear `gpu_lock = GpuLock()`, `_chat_deps = ChatDeps(...)`, `chat_with_video_use_case`, `get_chat_history_use_case`, `clear_chat_history_use_case`. Reescribir `worker()`:
  ```python
  async def worker() -> None:
      while True:
          task = await processing_queue.get()
          await gpu_lock.acquire("processing")
          try:
              await asyncio.to_thread(_gpu_scheduler.release, CHAT_MODEL)
              await process_video_use_case.execute(task)
          finally:
              gpu_lock.release()
              processing_queue.task_done()
  ```
- [ ] 8.3 Tests en `pipeline/tests/presentation/test_chat_routes.py`: app FastAPI mínima con `chat_routes.router`, sustituyendo los casos de uso del módulo de rutas por fakes con `monkeypatch.setattr(chat_routes, "chat_with_video_use_case", fake)`. Casos: POST feliz → 200, `content-type` empieza por `text/event-stream`, el cuerpo contiene líneas `data: {...}` en orden `meta`, `token`, `done`; `VideoNotFoundError` → 404; `VideoNotReadyError` → 409; `GpuBusyError` → 409; `InvalidChatMessageError` → 422; cuerpo `{"message": 5}` → 422; `sid` `a.b` → 422; GET devuelve `{"messages": [...]}`; DELETE devuelve `{"ok": true}`
- [ ] 8.4 Implementar `pipeline/presentation/routes/chat_routes.py` con `SessionIdParam`/`VideoIdParam` y un helper `_sse(events)` que formatea `data: <json>\n\n`
- [ ] 8.5 `pipeline/server.py`: `app.include_router(chat_routes.router)`; en `health()` añadir `"gpu_owner": gpu_lock.owner` (importar `gpu_lock` de `composition_root`)
- [ ] 8.6 Test en `pipeline/tests/presentation/test_worker_gpu_lock.py`: con `monkeypatch` sobre `composition_root.process_video_use_case` (fake cuyo `execute` registra `gpu_lock.owner` y luego lanza `RuntimeError`) y sobre `_gpu_scheduler` (fake que registra `release`), encolar una tarea, arrancar `worker()` como tarea, esperar `processing_queue.join()`, cancelar; afirmar que durante `execute` el propietario era `"processing"`, que se llamó `release(CHAT_MODEL)` y que al final `gpu_lock.owner is None`
- [ ] 8.7 Tests en verde

## 9. Frontend (design D11)

- [ ] 9.1 Añadir el botón `#tab-chat` (`data-tab="chat"`) entre `#tab-visual` y `#tab-save`; si no existe un símbolo adecuado en el sprite SVG, añadir `#i-chat`
- [ ] 9.2 Añadir `chat: {...}` y `health: {}` a `state`; en `checkHealth()` guardar la respuesta en `state.health`
- [ ] 9.3 CSS: clases de D11 usando solo tokens existentes; columna flex, compositor `sticky` abajo; reglas móviles (`max-width: 899px`) con objetivos táctiles de 44 px; `prefers-reduced-motion`
- [ ] 9.4 Implementar `chatViewHtml`, `loadChat`, `renderChatLog`, `renderChatSuggestions`, `updateChatAvailability` y la rama `chat` en `loadDetailContent`
- [ ] 9.5 Implementar `onChatKey`, `sendChat`, `readChatStream`, `handleChatEvent`, `scheduleChatRender`, `stopChat`, `clearChat`
- [ ] 9.6 `parseSrtHtml`: añadir `data-start` (segundos) y `tabindex="-1"` a cada `.srt-cue`. Hacer que `switchDetailTab` devuelva la promesa de `loadDetailContent`. Implementar `linkifyTimestamps` y `jumpToTimestamp`, con un listener delegado de `click` en `#detailContent` para `.ts-link`
- [ ] 9.7 Llamar a `stopChat()` (si `state.chat.streaming`) al inicio de `switchDetailTab`, `openDetail` y `closeDetail`
- [ ] 9.8 Comprobar que no se rompió el contrato JS de `openspec/ROADMAP.md` §6: `grep -n "saveFilesGroup\|btnCopyContent\|detailToolbar\|btn-record" frontend/index.html` sigue encontrando los mismos elementos

## 10. Verificación final

- [ ] 10.1 Suite completa en verde; anotar el total
- [ ] 10.2 Manual, con servidor y Ollama activos y un video `done` corto: pestaña Chat → sugerencia → la respuesta se pinta en streaming; el chip dice `Grabación completa`; hay al menos una cita `[HH:MM:SS]`; al pulsarla se abre SRT con el cue resaltado
- [ ] 10.3 Manual: recargar la página → el historial sigue ahí; `Borrar conversación` pide confirmación y lo vacía
- [ ] 10.4 Manual: durante una respuesta pulsar `Detener` → la pregunta vuelve al campo; `curl -s localhost:8000/api/health` muestra `"gpu_owner": null`
- [ ] 10.5 Manual: encolar un video y, mientras se procesa, abrir el chat de otro video `done` → compositor deshabilitado con `GPU ocupada procesando videos`; `curl -X POST .../chat` devuelve 409
- [ ] 10.6 Manual: preguntar algo que no está en la grabación → respuesta `No aparece en la grabación.`
- [ ] 10.7 Manual: enviar `<img src=x onerror=alert(1)>` como pregunta → se ve como texto, sin alerta
- [ ] 10.8 Manual, solo teclado: Tab hasta la pestaña Chat, escribir, Enter, Tab hasta una cita, Enter → foco en el cue. En ancho 375 px el compositor no queda tapado y no hay scroll horizontal
- [ ] 10.9 `openspec validate add-recording-chat --strict` sin errores
