## Why

El chat por grabación no responde preguntas que cruzan varias grabaciones de una sesión ("¿en qué reunión se cambió la fecha de entrega?"), y en grabaciones largas elige fragmentos por coincidencia literal de palabras, que falla con sinónimos. Un índice de embeddings local (`nomic-embed-text`, ya instalado) resuelve ambos casos y permite citar la fuente exacta.

## What Changes

- Índice semántico por video (`index.npz` + `index.json` en `sessions/<sid>/<vid>/`) construido al final del procesamiento y, para videos antiguos, la primera vez que se chatea.
- Nuevo chat de **sesión**: endpoints `GET`/`POST`/`DELETE` en `/api/sessions/{sid}/chat`, historial en `sessions/<sid>/chat.json`, recuperación de los fragmentos más cercanos a la pregunta en todas las grabaciones terminadas, respuesta con citas `[S1]`, `[S2]`… y lista de fuentes.
- El chat por grabación, en grabaciones largas, usa selección semántica en lugar de palabras clave cuando hay índice (con retroceso automático a palabras clave si falla).
- Nuevo tipo de evento en el flujo: `status` (p. ej. "Indexando 2 grabaciones…"). El evento `meta` gana `sources`.
- `ChatMessage` gana el campo opcional `sources` (persistido) para que las citas sigan funcionando al recargar.
- UI: botón **Chat de la sesión** en la cabecera de la sesión; fuentes como chips que abren el video en el momento citado.

## Capabilities

### New Capabilities
- `semantic-index`: troceado de artefactos, embeddings, almacenamiento, frescura y búsqueda por similitud.
- `session-chat`: conversación sobre todas las grabaciones terminadas de una sesión con fuentes citadas.

### Modified Capabilities
- `recording-chat`: se añade la selección semántica de fragmentos en modo de grabación larga y el evento `status`.

## Impact

- Código nuevo: `pipeline/domain/search/`, `pipeline/application/search/`, `pipeline/infrastructure/search/`, `pipeline/presentation/routes/session_chat_routes.py`.
- Código modificado: `pipeline/domain/chat/message.py`, `pipeline/application/chat/` (use cases, prompts, context builder), `pipeline/infrastructure/chat/json_chat_history_repository.py`, `pipeline/application/processing/process_video.py` (paso de indexado no fatal), `pipeline/presentation/composition_root.py`, `pipeline/server.py`, `pipeline/shared/config.py`, `frontend/index.html`.
- Dependencias: ninguna nueva (`numpy` 2.4.6 y `httpx` ya instalados). Modelo `nomic-embed-text` ya descargado.
- Disco: ~3 KB por fragmento (768 float32); una hora de grabación ≈ 80–100 fragmentos ≈ 300 KB.
- Requiere `add-recording-chat` aplicado y archivado.
