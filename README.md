# Video Reviewer

Transcripción y análisis de reuniones de negocio con IA 100% local en GPU.

Toma grabaciones `.mp4` (reuniones Levapan sobre segmentación de panaderías),
extrae audio, transcribe con **faster-whisper** en GPU, y produce resúmenes
ejecutivos + reglas de negocio con **qwen2.5:14b** vía Ollama.

Dos interfaces: **CLI** (batch) y **Web** (SPA con sesiones y SSE).

---

## Estructura

```
├── pipeline/
│   ├── run.sh          # Wrapper (LD_LIBRARY_PATH + launch)
│   ├── run_all.py      # Orquestador CLI
│   ├── server.py       # FastAPI + REST + SSE
│   ├── transcribe.py   # Extracción audio + faster-whisper
│   └── summarize.py    # Map-reduce con Ollama
├── frontend/
│   └── index.html      # SPA (HTML+CSS+JS, marked.js)
├── videos/             # Input *.mp4 (gitignored)
├── output/             # Salidas CLI (gitignored)
├── sessions/           # Salidas Web (gitignored)
└── docs/               # Reglas de negocio Levapan (gitignored)
```

## Flujo

```
videos/*.mp4
   │  ffmpeg → WAV 16kHz mono
   ▼
faster-whisper large-v3 (GPU, int8_float16, español)
   │  → transcript.txt + transcript.srt
   ▼
qwen2.5:14b vía Ollama (map-reduce)
   │  MAP: notas por trozo (3500 palabras, solape 200)
   │  REDUCE: summary.md + analysis.md
   ▼
output/<video>/  o  sessions/<sid>/<vid>/
```

## Requisitos

- **Python 3.12** + uv
- **ffmpeg** (extracción de audio)
- **NVIDIA GPU** con CUDA 12 (VRAM ≥ 12 GB recomendado)
- **Ollama** corriendo con `qwen2.5:14b`

## Instalación

```bash
# 1. Crear venv e instalar dependencias
uv venv --python 3.12
source .venv/bin/activate
uv pip install faster-whisper nvidia-cublas-cu12 nvidia-cudnn-cu12
uv pip install fastapi uvicorn aiofiles

# 2. Bajar modelo Ollama
ollama pull qwen2.5:14b

# 3. Colocar videos en videos/
```

## Uso

### CLI — Batch de todos los videos

```bash
# Todos los videos (reanudable)
./pipeline/run.sh

# Filtrar por nombre
./pipeline/run.sh --only 05-08

# Re-resumir sin re-transcribir
./pipeline/run.sh --skip-transcribe

# Cambiar modelos
./pipeline/run.sh --whisper-model medium --llm-model llama3.1:8b
```

### Web — UI con sesiones

```bash
# Puerto por defecto 8000
./pipeline/run.sh server

# Puerto personalizado
./pipeline/run.sh server --port 8080

# Abrir http://localhost:8000
```

### Acceso programático (sin run.sh)

```bash
source .venv/bin/activate
export LD_LIBRARY_PATH=.venv/lib/python3.12/site-packages/nvidia/cublas/lib:$LD_LIBRARY_PATH

python pipeline/run_all.py
python pipeline/server.py
```

## API REST

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET`  | `/` | SPA frontend |
| `GET`  | `/api/health` | Estado (ollama + ffmpeg) |
| **Sesiones** |||
| `GET`  | `/api/sessions` | Listar sesiones |
| `POST` | `/api/sessions` | Crear sesión `{"name": "...", "instructions": "..."}` |
| `GET`  | `/api/sessions/{sid}` | Detalle de sesión |
| `DELETE` | `/api/sessions/{sid}` | Eliminar sesión |
| **Videos** |||
| `POST` | `/api/sessions/{sid}/videos` | Agregar videos `{"paths": [...], "language": "es"}` |
| `POST` | `/api/sessions/{sid}/videos/{vid}/retry` | Reintentar video fallido |
| `DELETE` | `/api/sessions/{sid}/videos/{vid}` | Eliminar video |
| **Resultados** |||
| `GET`  | `/api/sessions/{sid}/videos/{vid}/transcript` | Transcripción |
| `GET`  | `/api/sessions/{sid}/videos/{vid}/srt` | Subtítulos SRT |
| `GET`  | `/api/sessions/{sid}/videos/{vid}/summary` | Resumen ejecutivo (MD) |
| `GET`  | `/api/sessions/{sid}/videos/{vid}/analysis` | Análisis detallado (MD) |
| `POST` | `/api/sessions/{sid}/videos/{vid}/save` | Exportar a directorio |
| **Streaming** |||
| `GET`  | `/api/progress` | SSE — estado en tiempo real (1s) |

## Salida por video

| Archivo | Contenido |
|---------|-----------|
| `transcript.txt` | Transcripción texto plano |
| `transcript.srt` | Subtítulos con timestamps |
| `summary.md` | Resumen ejecutivo (tema, puntos, decisiones, pendientes) |
| `analysis.md` | Reglas de negocio + umbrales + escenarios |

## Rendimiento (RTX 5070, 12 GB VRAM)

- Transcripción: ≈ **6× tiempo real** (7.5 h audio ≈ 75 min)
- VRAM: whisper ~3 GB · qwen2.5:14b ~9 GB
- Ambos modelos se ejecutan secuencialmente para evitar OOM

## Stack

| Componente | Tecnología |
|-----------|-----------|
| Transcripción | faster-whisper large-v3 (ctranslate2, CUDA) |
| Análisis | Ollama + qwen2.5:14b (map-reduce, 16K ctx) |
| Backend | Python 3.12, FastAPI, uvicorn, aiofiles |
| Frontend | HTML+CSS+JS vanilla, marked.js |
| Persistencia | sessions.json + sistema de archivos |

## Ajustes

- Modelo Whisper: `--whisper-model medium` (más rápido)
- LLM: `--llm-model llama3.1:8b` (menos VRAM)
- Tamaño trozo: editar `PALABRAS_POR_TROZO` / `SOLAPE` en `summarize.py`
- Temperatura LLM: `0.2` (configurable en `pipeline/summarize.py`)
- Instrucciones personalizadas por sesión vía Web UI
