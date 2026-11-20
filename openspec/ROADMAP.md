# ROADMAP — Video Reviewer

Guía de ejecución para quien implemente (humano o modelo). Leer completa antes de tocar código.

## 1. Orden de ejecución (obligatorio)

| # | Change | Qué entrega | Depende de |
|---|--------|-------------|------------|
| 1 | `fix-stability-and-local-security` | Bugs reales + cierre de lectura/escritura arbitraria | — |
| 2 | `add-recording-chat` | Chat con streaming sobre UNA grabación | 1 |
| 3 | `add-session-rag-chat` | Índice de embeddings + chat sobre toda la sesión con citas | 2 |
| 4 | `optimize-processing-pipeline` | Menos frames a visión, Whisper por lotes, SSE por cambios, avisos | 1 |
| 5 | `improve-ui-ux` | Explorador de archivos, progreso real, buscar en transcripción, zip, re-análisis | 1, 2, 4 |
| 6 | `add-diarization-and-model-eval` | Banco de evaluación de modelos + hablantes (con spike previo) | 4 |

Un change a la vez. No empezar el siguiente hasta cerrar el anterior (sección 4).
El change 4 puede hacerse antes que 2 y 3 si se prefiere velocidad antes que chat; el resto del orden es fijo.

## 2. Paso 0 — antes del primer change

1. `git status`. Hay un diff sin commit en `frontend/index.html` (+1083/−373) previo a este plan.
   **No descartarlo ni sobrescribirlo.** Preguntar al usuario si se commitea o se descarta, y esperar respuesta.
2. Línea base de tests: `.venv/bin/python -m pytest pipeline/tests -q` → deben pasar **105**. Si no, parar y reportar.
3. Confirmar que Ollama responde: `ollama list` debe mostrar `qwen2.5:14b`, `gemma4:e4b`, `nomic-embed-text`.

## 3. Cómo aplicar cada change

1. Leer en este orden: `proposal.md` → `design.md` → `specs/**/spec.md` → `tasks.md`.
2. Crear rama desde `develop`: `git checkout -b feature/<nombre-del-change>`.
3. Ejecutar `tasks.md` de arriba hacia abajo, sin saltar ni reordenar. Marcar `- [x]` al terminar cada tarea.
4. En cada grupo: primero los tests (deben FALLAR por la razón correcta), luego el código hasta que pasen.
5. Tras cada grupo: `.venv/bin/python -m pytest pipeline/tests -q`. Cero fallos antes de seguir.
6. Si una tarea no se puede cumplir tal como está escrita (API distinta a la descrita, archivo que cambió),
   **parar**, anotar el hallazgo bajo la tarea en `tasks.md` y preguntar. No improvisar una alternativa.
7. Commits: uno por grupo de tareas, formato `Feat: ...` / `Fix: ...` (estilo actual del repo). Solo si el usuario
   autorizó commitear. Nunca `git push` sin permiso explícito.

## 4. Definición de terminado (por change)

- Todas las tareas `- [x]`.
- Suite completa en verde y sin tests saltados.
- `openspec validate <change> --strict` sin errores.
- Verificación manual del grupo final de `tasks.md` ejecutada y con resultado anotado.
- `openspec archive <change> --yes` (mueve el change a `archive/` y actualiza `openspec/specs/`).

## 5. Reglas duras

- **No borrar** `sessions/`, `sessions.json`, `videos/`, `output/` ni artefactos generados. Las pruebas usan `tmp_path`.
- **No descargar modelos** (`ollama pull`, HuggingFace) sin aprobación del usuario: pesan GB.
- **No instalar dependencias** que el `design.md` del change no nombre. Instalar con `uv pip install <pkg>` dentro de `.venv`.
- Los tests no llaman a Ollama, ffmpeg ni GPU reales: fakes escritos a mano (ver `pipeline/tests/` para el estilo).
- Tests async: `asyncio.run(...)` dentro de un test síncrono. No añadir `pytest-asyncio`.
- `pipeline/presentation/composition_root.py` no importa de `pipeline/server.py`.
- Capas: `domain` no importa nada de fuera; `application` solo importa `domain`; `infrastructure` implementa ports.
- Funciones nuevas ≤ 20 líneas. Si crece, extraer función con nombre claro.

## 6. Contrato JS del frontend (no romper)

`frontend/index.html` es un único archivo. Estos nombres los usa el JS existente; no renombrarlos:

- `#saveFiles` / `#saveFilesGroup`, `#detailToolbar` (se muestra/oculta con `style.display`), `#detailContent`,
  `#detailPanel`, `#detailTitle`, `#detailSubtitle`, `#videoList`, `#mainContent`, `#sidebar`, `#liveStatus`, `#recStatus`.
- `copyContent` usa `#btnCopyContent`; `stopRecording` consulta `.btn-record`; las tarjetas se generan en `renderVideoCards`.
- Helpers a reutilizar (no duplicar): `api()`, `toast()`, `confirmDialog()`, `escapeHtml()`, `icon()`, `announce()`,
  `setBusy()`, `setFieldError()`, `autoGrow()`, `captureFocus()`.
- Pestañas del detalle: botones `role="tab"` con `data-tab`, estado en `state.activeDetailTab`, carga en `loadDetailContent(tab)`.
- Todo color, espacio y radio sale de los tokens CSS de `:root` (`--accent`, `--surface`, `--radius`, `--fs-*`…). No hex sueltos.
- Rejilla de 8pt; objetivo táctil mínimo 44×44 px en móvil; foco visible con `--focus-ring`; contraste AA.
- Markdown del modelo se pinta SIEMPRE con `marked.parse()` (el renderer ya escapa HTML crudo). Texto de usuario con `escapeHtml()`.

## 7. Datos de referencia

- Ids de sesión y video: 12 hex (`uuid4().hex[:12]`).
- Estados de video: `queued → extracting_audio → transcribing → [analyzing_visual] → summarizing → done | error`.
- Presupuesto de contexto: ~2 tokens por palabra en español. `num_ctx` 8192 (MAP) y 16384 (REDUCE y chat).
- Ollama trunca en silencio lo que no cabe en `num_ctx` (descarta el inicio: system prompt). Siempre medir palabras antes de enviar.
- La GPU no aguanta dos modelos grandes: cualquier uso nuevo de Ollama pasa por el candado de GPU (change 2).
