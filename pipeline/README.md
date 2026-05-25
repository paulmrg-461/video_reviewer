# Pipeline de resumen de reuniones (local, GPU)

Transcribe y resume reuniones (cliente + desarrollador discutiendo reglas de
negocio) de `videos/*.mp4`, 100% local en la RTX 5070.

## Flujo

```
videos/*.mp4
   │  ffmpeg (audio 16kHz mono)
   ▼
faster-whisper large-v3 (GPU, int8_float16, español)
   │  -> transcript.txt + transcript.srt
   ▼
qwen2.5:14b vía Ollama (map-reduce)
   │  MAP: notas por trozo  ·  REDUCE: consolida
   ▼
output/<video>/  summary.md  +  rules.md
```

## Salida por video — `output/<slug>/`

| Archivo | Contenido |
|---------|-----------|
| `transcript.txt` | transcripción en texto plano |
| `transcript.srt` | transcripción con timestamps |
| `summary.md` | resumen ejecutivo (tema, puntos, decisiones, pendientes) |
| `rules.md` | reglas de negocio + umbrales + escenarios, consolidados |

## Uso

```bash
# Todos los videos (reanudable: salta lo ya hecho)
./pipeline/run.sh

# Solo algunos (filtra por substring del nombre)
./pipeline/run.sh --only 05-08

# Re-resumir sin re-transcribir (p.ej. tras ajustar prompts)
./pipeline/run.sh --skip-transcribe
```

## Stack / requisitos (ya instalados)

- **ffmpeg** — extracción de audio
- **.venv** (Python 3.12, uv) — `faster-whisper`, `ctranslate2`, libs CUDA 12
  (cuBLAS/cuDNN vía pip; `run.sh` las pone en `LD_LIBRARY_PATH`)
- **Ollama** + modelo `qwen2.5:14b` — resumen/extracción

> Nota Blackwell (sm_120): la GPU funciona con `ctranslate2 4.7.2`. El único
> ajuste necesario fue exportar `LD_LIBRARY_PATH` hacia las libs CUDA del venv
> (lo hace `run.sh`).

## Rendimiento (medido)

- Transcripción ≈ **6× tiempo real** (7.5 h de audio ≈ 75 min en GPU).
- VRAM: whisper ~3 GB · qwen2.5:14b ~9 GB (no corren a la vez en el pipeline).

## Ajustes

- Modelo whisper: `--whisper-model medium` (más rápido, menos preciso).
- LLM: `--llm-model llama3.1:8b`.
- Tamaño de trozo / prompts: editar `summarize.py`.
