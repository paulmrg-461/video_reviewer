## Context

Estado actual verificado en el código:

- `pipeline/run.sh:23` lanza uvicorn con `--host 0.0.0.0`. No hay autenticación.
- `AddVideosToSessionUseCase.execute` (`pipeline/application/videos/use_cases.py`) acepta cualquier ruta existente y descarta en silencio las que no existen.
- `SaveArtifactsUseCase.execute` hace `Path(target_dir).mkdir(parents=True)` sobre cualquier ruta y copia `out_dir / fname` con `fname` sin validar (`../../x` sale del directorio del video).
- Las rutas GET de artefactos construyen `ROOT / "sessions" / sid / vid` con `sid`/`vid` sin validar (`%2e%2e` llega decodificado como `..`).
- `pipeline/server.py:72` usa `stop_recording_use_case` pero solo importa `gateway`, `processing_queue`, `worker` → `NameError` al apagar; las grabadoras quedan vivas.
- `SessionsJsonGateway._save` usa `Path.write_text`: un corte a mitad deja JSON truncado.
- `SessionsJsonGateway.update_video` hace upsert: si se borra un video en proceso, el siguiente `video_repo.update()` del worker lo reinserta.
- `FfmpegFrameExtractor.extract_frames` ignora `returncode`.

Restricciones: herramienta local de un solo usuario; sin dependencias nuevas; no cambiar el formato de `sessions.json`.

## Goals / Non-Goals

**Goals:**
- Que un equipo de la LAN no pueda leer ni escribir archivos arbitrarios, ni siquiera cuando el usuario expone el servidor.
- Apagado limpio, persistencia que no se corrompe, borrado coherente, fallos de ffmpeg visibles en el log.

**Non-Goals:**
- Autenticación / usuarios / HTTPS.
- Migrar `sessions.json` a SQLite.
- Cancelar un procesamiento en curso (solo se impide borrarlo).
- Mostrar avisos de procesamiento en la UI (eso es el change `optimize-processing-pipeline`).

## Decisions

### D1. Host configurable, loopback por defecto
`run.sh`: `HOST="${VIDEO_REVIEWER_HOST:-127.0.0.1}"` y `--host "$HOST"`. Si `HOST` no es `127.0.0.1` ni `localhost`, imprimir a stderr: `ADVERTENCIA: servidor expuesto en $HOST sin autenticación`.
*Alternativa descartada*: token de acceso — añade fricción a una herramienta local y no es lo pedido.

### D2. `PathPolicy` en la capa de aplicación
Archivo nuevo `pipeline/application/shared/path_policy.py`:

```python
MEDIA_EXTENSIONS = frozenset({".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v",
                              ".mp3", ".m4a", ".wav", ".ogg", ".flac", ".opus"})

class PathPolicy:
    def __init__(self, input_roots: tuple[Path, ...], export_roots: tuple[Path, ...]) -> None: ...
    def check_input_file(self, raw: str) -> Path:      # devuelve la ruta resuelta o lanza PathNotAllowedError
    def check_export_dir(self, raw: str) -> Path:      # idem; NO crea el directorio
```

Reglas (en este orden; el primer incumplimiento define `reason`):

`check_input_file`:
1. `raw.strip()` vacío → `"ruta vacía"`.
2. `Path(raw).expanduser().resolve()` (resuelve symlinks y `..`).
3. No existe o no es archivo → `"no existe"`.
4. Sufijo en minúsculas fuera de `MEDIA_EXTENSIONS` → `"tipo de archivo no permitido"`.
5. No está bajo ninguna raíz (`resolved.is_relative_to(root)`) → `"fuera de las carpetas permitidas"`.

`check_export_dir`:
1. Vacío → `"ruta vacía"`.
2. `expanduser().resolve()`.
3. No está bajo ninguna raíz de exportación → `"fuera de las carpetas permitidas"`.
4. Algún componente de la ruta **relativa a la raíz** empieza por `.` → `"carpeta oculta no permitida"` (impide `~/.ssh`, `~/.config`).
5. Existe y no es directorio → `"no es una carpeta"`.

`PathNotAllowedError(path: str, reason: str)` vive en `pipeline/application/shared/exceptions.py` (archivo nuevo).

Las raíces se resuelven una vez (`root.expanduser().resolve()`) en el constructor.

*Por qué en application y no en la ruta HTTP*: la regla es de negocio y la reutilizarán el explorador de archivos (change `improve-ui-ux`) y el CLI.

### D3. Configuración de raíces
En `pipeline/shared/config.py`:

```python
def _roots_from_env(name: str, default: tuple[Path, ...]) -> tuple[Path, ...]:
    raw = os.environ.get(name, "")
    parts = [Path(p) for p in raw.split(os.pathsep) if p.strip()]
    return tuple(parts) or default

INPUT_ROOTS = _roots_from_env("VIDEO_REVIEWER_INPUT_ROOTS", (Path.home(), ROOT / "videos", ROOT / "sessions"))
EXPORT_ROOTS = _roots_from_env("VIDEO_REVIEWER_EXPORT_ROOTS", (Path.home(),))
```

`ROOT / "sessions"` está en las raíces de entrada porque las grabaciones propias viven en `sessions/<sid>/`.

### D4. `AddVideosToSessionUseCase` devuelve un resultado explícito
Nuevo dataclass en `pipeline/application/videos/use_cases.py`:

```python
@dataclass(frozen=True)
class RejectedPath:
    path: str
    reason: str

@dataclass(frozen=True)
class AddVideosResult:
    added: list[Video]
    rejected: list[RejectedPath]
```

El constructor recibe un quinto parámetro `path_policy: PathPolicy`. Por cada ruta no vacía: `check_input_file`; si lanza, se acumula en `rejected`; si no, se crea el `Video` usando la ruta **resuelta**. Las rutas vacías se siguen ignorando sin reportar.

Esto cambia el tipo de retorno: los tests existentes de `test_video_use_cases.py` que hacen `added = asyncio.run(...)` pasan a usar `result.added`.

### D5. `SaveArtifactsUseCase`
- Constante `EXPORTABLE_FILES = ("summary.md", "analysis.md", "transcript.txt", "transcript.srt", "visual_notes.md")`.
- Si algún `fname` no está en la constante → `InvalidArtifactNameError(fname)` (nuevo, en `pipeline/application/videos/exceptions.py`) **antes** de copiar nada.
- `target = path_policy.check_export_dir(target_dir)`; después `target.mkdir(parents=True, exist_ok=True)`.
- Ruta HTTP: `PathNotAllowedError` → 403 con `detail = f"Destino no permitido: {reason}"`; `InvalidArtifactNameError` → 422.

### D6. Validación de ids
Archivo nuevo `pipeline/presentation/routes/params.py`:

```python
ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
SessionIdParam = Annotated[str, Path(pattern=ID_PATTERN)]
VideoIdParam = Annotated[str, Path(pattern=ID_PATTERN)]
```

Sustituir `sid: str` / `vid: str` por estos tipos en `sessions_routes.py`, `videos_routes.py` y `recording_routes.py` (solo `sid` y `vid`; no tocar `rid`). FastAPI devuelve 422 solo.
*Por qué no `^[a-f0-9]{12}$`*: `sessions.json` existente podría contener ids de versiones anteriores; el patrón amplio bloquea `.`, `/` y `%`, que es lo que importa.

### D7. Lifespan
En `pipeline/server.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(worker())
    try:
        yield
    finally:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        await asyncio.to_thread(stop_recording_use_case.stop_all_recorders)

app = FastAPI(title="Video Reviewer", version="1.0.0", lifespan=lifespan)
```

Añadir `stop_recording_use_case` al import de `composition_root`. Eliminar las dos funciones `@app.on_event`.

### D8. Escritura atómica
`SessionsJsonGateway._save`: escribir en `self.path.with_name(self.path.name + ".tmp")`, `flush` + `os.fsync`, luego `os.replace(tmp, self.path)`. Mismo directorio ⇒ mismo sistema de archivos ⇒ `replace` atómico.
`_load`: si `json.JSONDecodeError`, lanzar `SessionsFileCorruptError(path)` (nuevo, en el mismo módulo) con mensaje `sessions.json está corrupto: <path>. Restaurar desde copia o corregir a mano.` — nunca devolver `{"sessions": {}}` en ese caso, porque el siguiente `_save` borraría todo.

### D9. No borrar videos en proceso
`DeleteVideoUseCase.execute`: obtener el video; si su `status` está en `{EXTRACTING_AUDIO, TRANSCRIBING, ANALYZING_VISUAL, SUMMARIZING}` lanzar `VideoBusyError(session_id, video_id)` (nuevo, en `pipeline/application/videos/exceptions.py`). Ruta → 409 `"El video se está procesando. Espera a que termine para eliminarlo."`. Si el video no existe se conserva el comportamiento permisivo actual (no lanza). Un video `queued` sí se puede borrar: el worker ya ignora tareas cuyo video no existe.
*Alternativa descartada*: cancelar el hilo de Whisper/Ollama — no hay forma segura de interrumpir `run_in_executor`.

### D10. Errores de ffmpeg en frames
`FfmpegFrameExtractor.extract_frames`: si `result.returncode != 0`, lanzar `FrameExtractionError` (nuevo, en `pipeline/application/visual_analysis/ports.py`, hereda de `RuntimeError`) con las últimas 5 líneas de `stderr`. `AnalyzeVisualUseCase.execute` envuelve la llamada: captura `FrameExtractionError`, imprime `  ⚠ extracción de frames falló: <msg>` y devuelve `None` (mismo resultado que "cero frames": el video continúa sin notas visuales).

## Risks / Trade-offs

- [Usuarios que abren la app desde el móvil dejan de poder entrar] → documentado en README y en el mensaje de arranque; una variable de entorno lo restaura.
- [Videos en discos externos (`/run/media/...`) quedan fuera de `$HOME`] → el motivo `"fuera de las carpetas permitidas"` aparece en la UI; README explica `VIDEO_REVIEWER_INPUT_ROOTS`.
- [`resolve()` sigue symlinks: un symlink dentro de `$HOME` hacia fuera queda rechazado] → comportamiento deseado.
- [Cambiar el retorno de `AddVideosToSessionUseCase` rompe tests existentes] → la tarea 3.1 los actualiza explícitamente.

## Migration Plan

Sin migración de datos. Rollback: `git revert` del merge; `sessions.json` no cambia de formato.

## Open Questions

Ninguna.
