## Context

Verificado en el código y en el entorno:

- `AnalyzeVisualUseCase` describe **todos** los frames extraídos (`fps=1/interval`, por defecto 15 s) con una llamada al modelo de visión por frame. El tiempo del frame se calcula como `índice × intervalo`.
- `FasterWhisperProvider.transcribe` usa `WhisperModel.transcribe` en serie. `BatchedInferencePipeline.transcribe` (faster-whisper 1.2.1 instalado) acepta los mismos argumentos que ya se usan (`vad_filter`, `condition_on_previous_text`, `no_speech_threshold`, `compression_ratio_threshold`, `log_prob_threshold`, `hallucination_silence_threshold`, `word_timestamps`, `hotwords`, `beam_size`, `temperature`) más `batch_size`.
- La UI ofrece idioma `auto` y ese valor llega sin traducir a `model.transcribe(language="auto")`. faster-whisper espera `None` para autodetección. No se ha ejecutado para confirmar el fallo: la tarea 4.1 lo confirma con un test antes de corregir.
- `/api/progress` hace `list_sessions()` (lee y parsea `sessions.json`) cada segundo por cliente y envía siempre.
- Avisos existentes que solo van a consola: `OllamaClient.chat` (`posible truncado`), `FfmpegAudioExtractor` (`audio parcialmente recuperado`), `AnalyzeVisualUseCase` (fallo de extracción, desde el change 1).
- `ProcessVideoUseCase.execute` supera con mucho el límite de 20 líneas y recibe `task: dict`.

## Goals / Non-Goals

**Goals:**
- Reducir llamadas al modelo de visión sin perder cambios de pantalla.
- Permitir transcripción por lotes sin imponerla hasta medir.
- Dejar de emitir progreso cuando no hay cambios.
- Hacer visibles en datos los avisos de calidad.

**Non-Goals:**
- Cambiar prompts o modelos (ver `add-diarization-and-model-eval`).
- Mostrar los avisos en la UI (va en `improve-ui-ux`).
- Progreso porcentual dentro de cada etapa (va en `improve-ui-ux`).
- Reducir la resolución de los frames (riesgo de perder texto pequeño; sin medir).

## Decisions

### D1. Refactor previo de `ProcessVideoUseCase` (sin cambio de comportamiento)
Se hace **primero**, con la suite existente como red (`test_process_video_use_case.py`, 291 líneas).

```python
@dataclass(frozen=True)
class ProcessingTask:
    session_id: str
    video_id: str
    instructions: str = ""
    whisper_model: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "int8_float16"
    llm_model: str = "qwen2.5:14b"
    vision_model: str = "gemma4:e4b"
    frame_interval: int | None = None
    analyze_visual: bool = False

    @classmethod
    def from_dict(cls, raw: dict) -> "ProcessingTask"     # ignora claves desconocidas (p. ej. "language")
```

`execute(self, task: dict)` conserva su firma pública (la cola sigue transportando dicts) y delega en métodos privados, cada uno ≤ 20 líneas: `_load_video`, `_prepare_output`, `_transcribe`, `_analyze_visual`, `_summarize`, `_finish`. El orden de llamadas a `gpu_scheduler.release` y a `video_repo.update` debe quedar **idéntico** (los tests existentes lo comprueban). Los dos helpers `_read_*_from_disk` no se tocan.

### D2. Deduplicación de frames

**Dominio puro** — `pipeline/domain/videos/frame_selection.py`:

```python
def frame_difference(a: bytes, b: bytes) -> float
    # media de |a[i] - b[i]|, rango 0–255. Longitudes distintas → ValueError.

def select_distinct_frames(signatures: list[bytes], policy: DedupPolicy) -> list[int]

@dataclass(frozen=True)
class DedupPolicy:
    threshold: float      # diferencia mínima para considerar "cambió". <= 0 desactiva (se conservan todos)
    max_gap: int          # nº máximo de frames consecutivos descartados + 1
```

Algoritmo: conservar el índice 0. Para cada `i > 0`: conservar si `frame_difference(sig[i], sig[último_conservado]) >= threshold` **o** si `i - último_conservado >= max_gap`. Se compara contra el último **conservado**, no contra el anterior, para no perder cambios graduales (scroll lento).

**Port** — añadir a `pipeline/application/visual_analysis/ports.py`:

```python
class FrameSignaturePort(typing.Protocol):
    def signatures(self, video: Path, interval_seconds: int) -> list[bytes]: ...
```

**Adaptador** — `pipeline/infrastructure/visual_analysis/ffmpeg_frame_signature_extractor.py`:

```
ffmpeg -v error -i <video> -vf fps=1/<N>,scale=32:32,format=gray -f rawvideo -
```

`subprocess.run(cmd, capture_output=True)`; si `returncode != 0` → `FrameExtractionError`. Partir `stdout` en bloques de 1024 bytes (32×32); descartar un bloque final incompleto.

**Caso de uso** — `AnalyzeVisualUseCase.__init__` gana dos parámetros opcionales agrupados: `dedup: FrameDedup | None = None`, donde

```python
@dataclass(frozen=True)
class FrameDedup:
    signatures: FrameSignaturePort
    policy: DedupPolicy
```

En `execute`, tras extraer los frames:
1. Si `dedup is None` o `policy.threshold <= 0` → todos los índices.
2. Obtener firmas. Si `len(firmas) != len(frames)` o se lanza `FrameExtractionError` → imprimir `  ⚠ deduplicación omitida (<motivo>)` y usar todos los índices.
3. `keep = select_distinct_frames(...)`; imprimir `  {len(keep)} de {len(frames)} frames tras deduplicar`.
4. Describir solo `frames[i] for i in keep`, con `ts = i × interval_seconds` (**el índice original**, no la posición en `keep`).

El formato de `visual_notes.md` no cambia.

**Configuración** (`pipeline/shared/config.py`):

```python
VISUAL_DEDUP_THRESHOLD = float(os.environ.get("VISUAL_DEDUP_THRESHOLD", "0"))   # se fija tras la calibración (tarea 3.8)
VISUAL_MAX_GAP_FRAMES = int(os.environ.get("VISUAL_MAX_GAP_FRAMES", "8"))        # 8 × 15 s = 2 min
```

El valor por defecto del umbral queda en `0` (desactivado) hasta calibrar: la tarea 3.8 mide las diferencias reales entre frames de una grabación y propone un valor al usuario. *Por qué no fijarlo ahora*: no hay datos; un umbral alto se saltaría cambios de texto pequeños (escribir en un documento mueve pocos píxeles a 32×32).

*Alternativas descartadas*: `mpdecimate` de ffmpeg (pierde el índice original del frame ⇒ tiempos incorrectos); hash perceptual con Pillow/imagehash (dependencia nueva).

### D3. Transcripción

`FasterWhisperProvider.__init__(self, options: WhisperOptions = WhisperOptions())`:

```python
@dataclass(frozen=True)
class WhisperOptions:
    batch_size: int = 0            # <= 1 → modo en serie actual
    hotwords: str | None = None
```

En `transcribe`:
- `language_arg = None if language in ("auto", "") else language`.
- `kwargs = {...los argumentos actuales..., "language": language_arg, "hotwords": self._options.hotwords}` construidos en un método `_decode_options(language)`.
- Si `batch_size > 1`: `BatchedInferencePipeline(model=model).transcribe(str(audio), batch_size=batch_size, **kwargs)`; si no: `model.transcribe(str(audio), **kwargs)`.
- El bucle de segmentos y `_is_repeat` no cambian.

Para poder testear sin GPU: el constructor del modelo se obtiene por un método `_load_model(model_name, device, compute_type)` y el de la tubería por `_batched(model)`; los tests los sustituyen con `monkeypatch` por fakes que registran los argumentos. El `import faster_whisper` sigue siendo local a esos métodos (arranque rápido).

**Glosario** — `pipeline/infrastructure/transcription/glossary.py`:

```python
MAX_GLOSSARY_TERMS = 100
def load_hotwords(path: Path) -> str | None
```

Archivo inexistente → `None`. Se ignoran líneas vacías y las que empiezan por `#`; términos sin duplicados (comparación sin distinguir mayúsculas), máximo `MAX_GLOSSARY_TERMS` (si hay más, imprimir aviso y truncar); se unen con `", "`. Resultado vacío → `None`.

Configuración: `WHISPER_BATCH_SIZE = int(os.environ.get("WHISPER_BATCH_SIZE", "0"))`, `GLOSSARY_FILE = Path(os.environ.get("VIDEO_REVIEWER_GLOSSARY", ROOT / "glossary.txt"))`. Añadir `glossary.example.txt` en la raíz con 5 líneas de ejemplo y comentarios; añadir `/glossary.txt` a `.gitignore` (puede contener nombres propios de la empresa).

El glosario se lee una vez al construir el proveedor en `composition_root.py`; cambiarlo requiere reiniciar el servidor (documentar en README).

### D4. Progreso por cambios

`SessionsJsonGateway`: atributo `self._revision = 0`, incrementado al final de `_save`; propiedad de solo lectura `revision`.

Nuevo `pipeline/presentation/routes/progress_routes.py`:

```python
HEARTBEAT_EVERY = 15      # iteraciones sin envío

async def progress_events(source: ProgressSource, is_disconnected, interval: float = 1.0) -> AsyncIterator[str]
```

`ProgressSource` es un Protocol con `revision: int` y `async def snapshot() -> list[dict]`. Lógica: enviar `snapshot()` al empezar; después, cada `interval`: si `await is_disconnected()` → terminar; si `source.revision != última` → enviar `data: <json>\n\n` y reiniciar el contador; si no, incrementar el contador y al llegar a `HEARTBEAT_EVERY` enviar `: ping\n\n` y reiniciarlo.

La ruta `GET /api/progress` se muda de `server.py` a este módulo (router propio) y usa un adaptador `_GatewaySource(gateway)` cuyo `snapshot()` es `gateway.list_sessions()`. El frontend no cambia: `EventSource` ignora las líneas de comentario.

*Nota para `improve-ui-ux`*: su registro de progreso en memoria tendrá su propia revisión; `ProgressSource.revision` se definirá entonces como la suma de ambas.

### D5. Avisos por video

**Dominio** — `Video`: atributo `self.warnings: list[str] = []` en `__init__`; método

```python
MAX_WARNINGS = 10
def add_warning(self, message: str) -> None     # ignora vacíos y duplicados; conserva como máximo MAX_WARNINGS (los primeros)
```

`requeue()` vacía `warnings`.

**Mappers** — `video_dict_to_domain`: `video.warnings = list(d.get("warnings", []))`; `video_domain_to_dict`: `"warnings": list(video.warnings)`. Las rutas que construyen el dict de video a mano (`add_video` en `videos_routes.py`) añaden `"warnings": v.warnings`.

**Recolector** — `pipeline/application/shared/warning_collector.py`:

```python
class WarningCollector:
    def add(self, message: str) -> None
    def drain(self) -> list[str]        # devuelve y vacía
```

Una sola instancia en `composition_root.py`, inyectada como `on_warning=collector.add` (parámetro opcional `Callable[[str], None] | None`, por defecto `None`) en:
- `OllamaClient.__init__` → en el aviso de truncado, además del `print`: `"El texto no cupo en el contexto del modelo; parte del análisis puede faltar o ser impreciso."`
- `FfmpegAudioExtractor.__init__` → `"El audio estaba dañado y se recuperó solo en parte; la transcripción puede estar incompleta."`
- `AnalyzeVisualUseCase.__init__` → al capturar `FrameExtractionError`: `"No se pudieron extraer imágenes del video; el análisis no incluye lo mostrado en pantalla."`

`ProcessVideoUseCase` recibe el recolector (`warnings: WarningCollector`): `drain()` al empezar `execute` (descarta restos), y en `_finish` y en el `except`: `for w in self._warnings.drain(): video.add_warning(w)` antes del `update` final.

Es seguro con un único recolector porque el worker procesa un video a la vez y el chat no usa `OllamaClient`.

### D6. Health sin bloqueo
En `server.py`, `health()`: ejecutar cada `subprocess.run` con `await asyncio.to_thread(...)`. Extraer `_command_ok(cmd: list[str]) -> bool`.

## Risks / Trade-offs

- [La deduplicación se salta un cambio de pantalla pequeño] → comparación contra el último frame conservado, `max_gap` como red, umbral por defecto desactivado hasta calibrar, y `VISUAL_DEDUP_THRESHOLD=0` como interruptor.
- [Segundo pase de ffmpeg para las firmas] → decodificar a 32×32 es mucho más barato que una sola llamada de visión; si el recuento no cuadra, se analiza todo como hoy.
- [Modo por lotes de Whisper cambia la segmentación y puede usar más VRAM] → apagado por defecto; la tarea 4.8 mide tiempo, VRAM y diferencia de texto antes de proponer activarlo.
- [`hotwords` puede inducir a Whisper a "oír" un término del glosario donde no está] → glosario opcional y limitado a 100 términos; documentado.
- [Refactor de `ProcessVideoUseCase` introduce regresión] → se hace aislado, primero, sin tocar tests.

## Migration Plan

`sessions.json` existente no tiene `warnings`: se lee como lista vacía. Rollback sin migración.

## Open Questions

- Valor por defecto de `VISUAL_DEDUP_THRESHOLD` y de `WHISPER_BATCH_SIZE`: se deciden con el usuario con los datos de las tareas 3.8 y 4.8.
