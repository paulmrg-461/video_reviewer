Requisito previo: `add-recording-chat` aplicado y archivado. Tests: `.venv/bin/python -m pytest pipeline/tests -q`.

## 1. Preparación y verificación de la API (design D0)

- [ ] 1.1 Rama `feature/add-session-rag-chat` desde `develop`; suite en verde
- [ ] 1.2 Ejecutar el `curl` de design D0. Anotar aquí debajo: nombre de la clave de respuesta y dimensión del vector. Si no coincide con `{"embeddings": [[...]]}`, PARAR y preguntar
- [ ] 1.3 Crear paquetes vacíos: `pipeline/domain/search/__init__.py`, `pipeline/application/search/__init__.py`, `pipeline/infrastructure/search/__init__.py`

## 2. Mover VideoArtifacts al dominio (design D2)

- [ ] 2.1 Crear `pipeline/domain/videos/artifacts.py` con el dataclass `VideoArtifacts` (idéntico al actual)
- [ ] 2.2 En `pipeline/application/chat/context_builder.py` borrar la definición e importar desde el dominio. Suite en verde sin tocar ningún test

## 3. Dominio: troceado y huella (design D2)

- [ ] 3.1 Tests en `pipeline/tests/domain/test_search_chunk.py`: los cinco escenarios de "Troceado de artefactos" de `specs/semantic-index/spec.md`; además `fingerprint` es estable para la misma entrada y cambia si cambia cualquier artefacto; `visual_notes=None` y `visual_notes=""` producen la MISMA huella (intencional: fijarlo en un test)
- [ ] 3.2 Implementar `pipeline/domain/search/chunk.py`: `IndexedChunk`, `chunk_video`, `fingerprint`. Funciones privadas `_transcript_chunks`, `_visual_chunks`, `_section_chunks(kind, markdown)`, `_split_words(text, size)`
- [ ] 3.3 Tests en verde

## 4. Aplicación: ports y casos de uso de búsqueda (design D3, D5)

- [ ] 4.1 Crear `pipeline/application/search/ports.py`: `ScoredChunk`, `IndexEntry`, `SearchQuery`, `EmbeddingPort`, `SemanticIndexPort`, `EmbeddingError`
- [ ] 4.2 Tests en `pipeline/tests/application/test_index_video_use_case.py` con `_FakeReader`, `_FakeEmbedder` (devuelve `[[float(i)] ...]` y registra llamadas), `_FakeIndex` (en memoria): sin artefactos → 0 y no llama al embedder; índice fresco → 0 y no llama al embedder; caso normal → llama `embed(textos, "document")` una vez, `write` recibe mismos nº de chunks y vectores, devuelve ese número; 0 chunks → escribe índice vacío y devuelve 0
- [ ] 4.3 Implementar `pipeline/application/search/index_video.py`
- [ ] 4.4 Tests en `pipeline/tests/application/test_retrieve_chunks_use_case.py`: llama `embed([pregunta], "query")`, pasa el vector y `top_k` a `index.search`, devuelve su resultado tal cual
- [ ] 4.5 Implementar `pipeline/application/search/retrieve.py` (`RetrievalRequest`, `RetrieveChunksUseCase`)
- [ ] 4.6 Tests en verde

## 5. Infraestructura (design D4)

- [ ] 5.1 Tests en `pipeline/tests/infrastructure/test_ollama_embedding_provider.py` con `httpx.MockTransport`: los cuatro escenarios de "Embeddings locales con prefijos de tarea"; además los documentos llevan `keep_alive: "1m"` y el modelo configurado
- [ ] 5.2 Implementar `pipeline/infrastructure/search/ollama_embedding_provider.py`
- [ ] 5.3 Tests en `pipeline/tests/infrastructure/test_npz_semantic_index.py` con `tmp_path`: escenarios de "Índice por video con control de frescura" y "Búsqueda por similitud"; además los vectores guardados tienen norma 1 (`np.allclose`), `write` con 0 chunks produce un índice legible y `search` sobre él devuelve `[]`, y un `index.npz` truncado se ignora sin excepción
- [ ] 5.4 Implementar `pipeline/infrastructure/search/npz_semantic_index.py` (funciones privadas `_load(session_id, video_id) -> tuple[list[IndexedChunk], np.ndarray] | None`, `_normalize(matrix)`, `_atomic_write(path, writer)`)
- [ ] 5.5 Tests en verde

## 6. Indexado al procesar (design D6)

- [ ] 6.1 Tests en `pipeline/tests/application/test_process_video_use_case.py`: con `index_video` espía → se llama una vez con `(session_id, video_id)` y antes de que el video quede `DONE`; con `index_video` que lanza → el video termina `DONE`; con `index_video=None` → comportamiento actual intacto
- [ ] 6.2 Implementar el parámetro opcional y `_index_safely` en `pipeline/application/processing/process_video.py`
- [ ] 6.3 `pipeline/shared/config.py`: `EMBED_MODEL`, `RETRIEVAL_TOP_K`. `composition_root.py`: crear `_embedder`, `_semantic_index`, `index_video_use_case`, `retrieve_chunks_use_case`; pasar `index_video_use_case.execute` a `ProcessVideoUseCase`
- [ ] 6.4 Tests en verde

## 7. Historial con fuentes (design D10)

- [ ] 7.1 Tests: `ChatMessage(...)` sin `sources` → `()`; repo: guardar mensaje con `sources` y recargar conserva la lista; mensaje sin `sources` no escribe la clave; archivo antiguo sin la clave se lee con `sources == ()`
- [ ] 7.2 Implementar en `pipeline/domain/chat/message.py` y `pipeline/infrastructure/chat/json_chat_history_repository.py`. En `chat_routes.py`, la serialización del mensaje incluye `sources` solo si no está vacío (extraer `message_to_dict` a un helper compartido en `pipeline/presentation/routes/chat_serialization.py`)
- [ ] 7.3 Tests en verde

## 8. Selección semántica en el chat por grabación (design D9)

- [ ] 8.1 Extraer `_validate_message` a `pipeline/application/chat/validation.py` (función pública `validate_message`); suite en verde
- [ ] 8.2 Tests en `test_chat_context_builder.py`: `build_excerpts(artifacts, windows)` produce el mismo formato que el modo `excerpts` y respeta el presupuesto
- [ ] 8.3 Tests en `test_chat_use_cases.py`: los cuatro escenarios de "Selección semántica…" de `specs/recording-chat/spec.md`, con `_FakeRetrieve` y `_FakeIndexVideo`; verificar además que solo se usan chunks `kind == "transcript"` y que quedan en orden cronológico
- [ ] 8.4 Implementar: `ChatContextBuilder.build_excerpts`, campo `artifacts` en `PreparedChat`, campos `retrieve` e `index_video` en `ChatDeps`, y el método privado `_semantic_context(prepared)` en `ChatWithVideoUseCase` que devuelve `ChatContext | None`
- [ ] 8.5 `composition_root.py`: pasar `retrieve_chunks_use_case` e `index_video_use_case` a `ChatDeps`
- [ ] 8.6 Tests en verde

## 9. Chat de sesión: aplicación (design D7, D8)

- [ ] 9.1 Añadir `NoAnalyzedVideosError` a `pipeline/application/chat/exceptions.py`
- [ ] 9.2 Tests en `pipeline/tests/application/test_session_chat_context.py` para una función pura `build_session_context(summaries, scored, video_names) -> tuple[str, list[dict]]` (en `pipeline/application/chat/session_context.py`): escenarios "Etiquetas de fuente", "Presupuesto" y "Muchas grabaciones" de `specs/session-chat/spec.md`; formato exacto de la cabecera de cada fragmento (D8); `preview` de 160 caracteres como máximo; fragmentos sin `start` muestran `resumen` o `análisis`
- [ ] 9.3 Implementar `session_context.py` y `SESSION_SYSTEM_TEMPLATE` + `build_session_messages(...)` en `prompts.py` (texto EXACTO de D8). Test: el system contiene las 7 reglas y los dos bloques
- [ ] 9.4 Tests en `pipeline/tests/application/test_session_chat_use_cases.py`: **prepare** → mensaje inválido, sesión inexistente, sin videos `done`, GPU ocupada, caso feliz. **run** → sin índices pendientes no hay `status`; con 2 pendientes hay `status` con el texto exacto y se llama `index_video` 2 veces; `meta` trae `context_mode: "retrieval"` y `sources`; `done` persiste `[user, assistant]` y el asistente lleva `sources`; `EmbeddingError` → evento `error` y candado libre; un `index_video` que lanza no aborta el chat; cancelación (`aclose`) libera el candado
- [ ] 9.5 Implementar `pipeline/application/chat/session_use_cases.py` (`SessionChatDeps`, `PreparedSessionChat`, `ChatWithSessionUseCase`). Métodos ≤ 20 líneas: extraer `_ensure_indexes`, `_retrieve`, `_stream_answer`
- [ ] 9.6 Tests en verde

## 10. Chat de sesión: rutas y wiring (design D11)

- [ ] 10.1 Tests en `pipeline/tests/presentation/test_session_chat_routes.py`: 200 con orden de eventos; 404; 409 (sin videos y GPU ocupada, con sus textos); 422; GET con `sources`; DELETE
- [ ] 10.2 Implementar `pipeline/presentation/routes/session_chat_routes.py` reutilizando `_sse` (moverlo a `chat_serialization.py`) y `SessionIdParam`
- [ ] 10.3 `composition_root.py`: `chat_with_session_use_case`; reutilizar `get_chat_history_use_case` / `clear_chat_history_use_case` con `ChatKey(sid, None)`. `server.py`: incluir el router
- [ ] 10.4 Tests en verde

## 11. Frontend (design D12)

- [ ] 11.1 `state.detailMode`; `chatEndpoint()`; adaptar `loadChat`, `sendChat`, `clearChat`, `loadDetailContent`, `openDetail`, `closeDetail`
- [ ] 11.2 Botón `#btnSessionChat` en `renderSessionView` y función `openSessionChat()`; estado deshabilitado sin videos `done`; el botón debe sobrevivir a los repintados por SSE (si `renderSessionView` no se repinta con SSE, actualizar su `disabled` desde `refreshVideoList`)
- [ ] 11.3 `handleChatEvent`: eventos `status` y `meta.sources`; chips de contexto `retrieval` y `semantic`
- [ ] 11.4 `renderSources`, `linkifySources`, `openSourceRef`; hacer que `selectVideo` devuelva la promesa de `openDetail`; listener delegado para `.src-link` y `.src-chip`
- [ ] 11.5 Sugerencias y placeholder del modo sesión; estilos nuevos con tokens; reglas móviles
- [ ] 11.6 Comprobar el contrato JS (ROADMAP §6) con `grep`

## 12. Verificación final

- [ ] 12.1 Suite completa en verde; anotar el total
- [ ] 12.2 Manual: sesión con ≥ 2 videos `done` anteriores a este change → `Chat de la sesión` → primera pregunta muestra `Indexando N grabación(es)…` y luego responde; existen `index.npz`/`index.json` en cada carpeta
- [ ] 12.3 Manual: hacer 5 preguntas reales cuyo dato esté en una grabación concreta. Anotar aquí cuántas respuestas citan la grabación correcta y las 10 puntuaciones de similitud de una de ellas (salen por consola). Si aciertan menos de 4 de 5, reportarlo al usuario antes de archivar
- [ ] 12.4 Manual: pulsar una cita `[S#]` de transcripción → abre el video correcto en el cue correcto; una de resumen → pestaña Resumen
- [ ] 12.5 Manual: durante una respuesta, `ollama ps` → anotar modelos cargados y que el LLM figura `100% GPU`. Si aparece reparto CPU/GPU, reportarlo
- [ ] 12.6 Manual: procesar un video nuevo → al quedar `done` ya tiene índice (el primer chat no muestra `Indexando`)
- [ ] 12.7 Manual: grabación larga (transcripción > 5200 palabras, si existe alguna) → chip `Fragmentos por significado`
- [ ] 12.8 Manual, teclado y 375 px: abrir chat de sesión, enviar, recorrer chips de fuentes con Tab, Enter abre la grabación; Esc cierra
- [ ] 12.9 `openspec validate add-session-rag-chat --strict` sin errores
