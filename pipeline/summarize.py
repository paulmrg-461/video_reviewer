"""
summarize.py — Resume y analiza una transcripción usando LLM local vía Ollama.

Estrategia map-reduce:
  MAP     -> trocea la transcripción; por cada trozo extrae notas estructuradas.
  REDUCE  -> combina las notas en: summary.md (resumen) + analysis.md (análisis).

Soporta instrucciones personalizadas para enfocar el análisis.

Salida:
  <out_dir>/summary.md
  <out_dir>/analysis.md

Uso:
  python summarize.py <out_dir> [--model qwen2.5:14b] [--instructions "..."]
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"
PALABRAS_POR_TROZO = 3500
SOLAPE = 200

SYS_DEFAULT = (
    "Eres un analista profesional. Revisas transcripciones de video y extraes "
    "información relevante con precisión. No inventas. Conservas nombres, cifras, "
    "fechas y datos exactos. Respondes en español."
)


def _build_prompts(instructions: str | None, nombre: str):
    if instructions:
        sys_map = (
            f"Eres un analista profesional. Tu tarea es analizar transcripciones de video "
            f"buscando específicamente lo siguiente: {instructions}. "
            f"Sé preciso, no inventes. Conserva nombres, cifras, fechas y datos exactos. "
            f"Responde en español."
        )
        prompt_map = (
            f"Este es un FRAGMENTO de la transcripción. Extrae SOLO información "
            f"relacionada con estas instrucciones: {instructions}\n\n"
            f"Organiza tus notas bajo estos encabezados (omite los vacíos):\n\n"
            f"HALLAZGOS: información relevante encontrada según las instrucciones.\n"
            f"CITAS: frases textuales importantes.\n"
            f"TEMAS: temas o tópicos mencionados.\n"
            f"DECISIONES: acuerdos o conclusiones.\n"
            f"PENDIENTES: preguntas abiertas o cosas por definir.\n\n"
            f"No resumas en prosa; usa viñetas cortas. Conserva los datos exactos.\n\n"
            f"--- FRAGMENTO ---\n"
            f"{{chunk}}\n"
            f"--- FIN FRAGMENTO ---"
        )
        prompt_reduce_summary = (
            f"NOTAS extraídas de todos los fragmentos de UNA transcripción, analizadas "
            f"bajo estas instrucciones: {instructions}\n\n"
            f"Redacta un RESUMEN EJECUTIVO en markdown:\n\n"
            f"# Resumen — {nombre}\n\n"
            f"## Tema principal\n(2-3 frases)\n\n"
            f"## Hallazgos clave según instrucciones\n(viñetas)\n\n"
            f"## Decisiones / Conclusiones\n(viñetas)\n\n"
            f"## Pendientes\n(viñetas)\n\n"
            f"Sé fiel a las notas, no inventes.\n\n"
            f"--- NOTAS ---\n"
            f"{{notas}}\n"
            f"--- FIN NOTAS ---"
        )
        prompt_reduce_analysis = (
            f"NOTAS extraídas de todos los fragmentos de UNA transcripción, analizadas "
            f"bajo estas instrucciones: {instructions}\n\n"
            f"Genera un ANÁLISIS DETALLADO en markdown:\n\n"
            f"# Análisis — {nombre}\n\n"
            f"## Instrucciones de análisis\n{instructions}\n\n"
            f"## Hallazgos detallados\nOrganiza por tema o categoría. Incluye citas textuales "
            f"cuando aplique. Sé exhaustivo.\n\n"
            f"## Temas identificados\n(lista de temas/tópicos encontrados)\n\n"
            f"## Conclusiones y recomendaciones\n(viñetas)\n\n"
            f"Fusiona duplicados. No inventes información que no esté en las notas.\n\n"
            f"--- NOTAS ---\n"
            f"{{notas}}\n"
            f"--- FIN NOTAS ---"
        )
    else:
        sys_map = SYS_DEFAULT
        prompt_map = (
            "Este es un FRAGMENTO de la transcripción. Extrae información relevante "
            "en notas concisas bajo estos encabezados (omite los vacíos):\n\n"
            "TEMAS: temas o tópicos principales discutidos.\n"
            "PUNTOS CLAVE: información importante, datos, cifras.\n"
            "DECISIONES: acuerdos o conclusiones.\n"
            "ACCIONES: tareas o siguientes pasos mencionados.\n"
            "PENDIENTES: preguntas abiertas o cosas por definir.\n\n"
            "No resumas en prosa; usa viñetas cortas. Conserva los datos exactos.\n\n"
            "--- FRAGMENTO ---\n"
            "{chunk}\n"
            "--- FIN FRAGMENTO ---"
        )
        prompt_reduce_summary = (
            "NOTAS extraídas de todos los fragmentos de UNA transcripción. "
            "Redacta un RESUMEN EJECUTIVO en markdown:\n\n"
            f"# Resumen — {{nombre}}\n\n"
            "## Tema principal\n(2-3 frases)\n\n"
            "## Puntos clave\n(viñetas)\n\n"
            "## Decisiones / Conclusiones\n(viñetas)\n\n"
            "## Pendientes\n(viñetas)\n\n"
            "Sé fiel a las notas, no inventes.\n\n"
            "--- NOTAS ---\n"
            "{notas}\n"
            "--- FIN NOTAS ---"
        )
        prompt_reduce_analysis = (
            "NOTAS extraídas de todos los fragmentos de UNA transcripción. "
            "Genera un ANÁLISIS DETALLADO en markdown:\n\n"
            f"# Análisis — {{nombre}}\n\n"
            "## Temas identificados\n(Organiza por categoría)\n\n"
            "## Puntos detallados por tema\n(viñetas con contexto)\n\n"
            "## Conclusiones\n(viñetas)\n\n"
            "Fusiona duplicados. No inventes.\n\n"
            "--- NOTAS ---\n"
            "{notas}\n"
            "--- FIN NOTAS ---"
        )

    return sys_map, prompt_map, prompt_reduce_summary, prompt_reduce_analysis


def _ollama_chat(model: str, system: str, user: str, num_ctx: int = 8192) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": 0.2},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["message"]["content"].strip()


def _trozos(texto: str, palabras: int, solape: int):
    words = texto.split()
    i = 0
    while i < len(words):
        yield " ".join(words[i:i + palabras])
        i += palabras - solape


def resumir(out_dir: Path, model: str, nombre: str,
            instructions: str | None = None) -> None:
    txt_path = out_dir / "transcript.txt"
    if not txt_path.exists():
        print(f"  ERROR: falta {txt_path}", file=sys.stderr)
        return

    summary_path = out_dir / "summary.md"
    analysis_path = out_dir / "analysis.md"
    if summary_path.exists() and analysis_path.exists():
        print(f"  [skip] resumen ya existe en {out_dir}")
        return

    sys_map, prompt_map, prompt_reduce_summary, prompt_reduce_analysis = _build_prompts(
        instructions, nombre
    )

    texto = txt_path.read_text(encoding="utf-8")
    trozos = list(_trozos(texto, PALABRAS_POR_TROZO, SOLAPE))
    print(f"  {len(texto.split())} palabras -> {len(trozos)} trozos (MAP)")

    notas = []
    for i, ch in enumerate(trozos, 1):
        print(f"    MAP trozo {i}/{len(trozos)}")
        nota = _ollama_chat(model, sys_map, prompt_map.format(chunk=ch))
        notas.append(f"### Fragmento {i}\n{nota}")
    notas_join = "\n\n".join(notas)

    print("  REDUCE -> summary.md")
    summary = _ollama_chat(
        model, sys_map,
        prompt_reduce_summary.format(notas=notas_join, nombre=nombre),
        num_ctx=16384,
    )
    summary_path.write_text(summary + "\n", encoding="utf-8")

    print("  REDUCE -> analysis.md")
    analysis = _ollama_chat(
        model, sys_map,
        prompt_reduce_analysis.format(notas=notas_join, nombre=nombre),
        num_ctx=16384,
    )
    analysis_path.write_text(analysis + "\n", encoding="utf-8")
    print(f"  ✓ summary.md + analysis.md")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--nombre", default=None)
    ap.add_argument("--instructions", default=None,
                    help="Instrucciones personalizadas para el análisis")
    args = ap.parse_args()
    nombre = args.nombre or args.out_dir.name
    resumir(args.out_dir, args.model, nombre, args.instructions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
