"""
summarize.py — Resume y extrae reglas de negocio de una transcripción usando
un LLM local vía Ollama (qwen2.5:14b por defecto).

Estrategia map-reduce (la reunión no cabe en una sola ventana de contexto):
  MAP     -> trocea la transcripción; por cada trozo extrae notas estructuradas.
  REDUCE  -> combina las notas en: summary.md (resumen) + rules.md (reglas).

Salida por video:
  <out_dir>/summary.md
  <out_dir>/rules.md

Uso:
  python summarize.py <out_dir> [--model qwen2.5:14b]
  (lee <out_dir>/transcript.txt)
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"
PALABRAS_POR_TROZO = 3500
SOLAPE = 200

SYS_MAP = (
    "Eres analista de negocio. Extraes información de una reunión donde un CLIENTE "
    "y un DESARROLLADOR discuten reglas de negocio y escenarios para un sistema de "
    "segmentación/scoring de panaderías. Eres preciso con números, umbrales y "
    "nombres. No inventas. Respondes en español."
)

PROMPT_MAP = """Este es un FRAGMENTO de la transcripción de la reunión. Extrae SOLO lo que aparezca, en notas concisas bajo estos encabezados (omite los vacíos):

REGLAS: reglas de negocio explícitas (condiciones, fórmulas, scoring).
UMBRALES/NÚMEROS: valores numéricos, rangos, puntajes, porcentajes mencionados.
ESCENARIOS: casos o ejemplos discutidos ("si el cliente X entonces Y").
DECISIONES: acuerdos a los que llegaron.
DUDAS/PENDIENTES: preguntas abiertas o cosas por definir.

No resumas en prosa; usa viñetas cortas. Conserva los números exactos.

--- FRAGMENTO ---
{chunk}
--- FIN FRAGMENTO ---"""

PROMPT_REDUCE_SUMMARY = """A continuación están las NOTAS extraídas de todos los fragmentos de UNA reunión, en orden. Redacta un RESUMEN EJECUTIVO en español (markdown), con esta estructura:

# Resumen — {nombre}

## Tema principal
(2-3 frases)

## Puntos clave discutidos
(viñetas)

## Decisiones tomadas
(viñetas; si no hubo, indícalo)

## Pendientes / dudas abiertas
(viñetas)

Sé fiel a las notas, no inventes. Conserva números exactos.

--- NOTAS ---
{notas}
--- FIN NOTAS ---"""

PROMPT_REDUCE_RULES = """A continuación están las NOTAS extraídas de todos los fragmentos de UNA reunión. Consolida TODAS las reglas de negocio y escenarios en un documento markdown limpio, deduplicado y ordenado:

# Reglas y escenarios — {nombre}

## Reglas de negocio
(lista numerada; cada regla con su condición y resultado; incluye umbrales/puntajes exactos)

## Umbrales y valores
(tabla o lista con todos los números/rangos mencionados)

## Escenarios / casos de ejemplo
(viñetas: situación -> clasificación/resultado)

## Pendientes por definir
(viñetas)

Fusiona duplicados. No inventes reglas que no estén en las notas. Conserva números exactos.

--- NOTAS ---
{notas}
--- FIN NOTAS ---"""


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


def resumir(out_dir: Path, model: str, nombre: str) -> None:
    txt_path = out_dir / "transcript.txt"
    if not txt_path.exists():
        print(f"  ERROR: falta {txt_path}", file=sys.stderr)
        return

    summary_path = out_dir / "summary.md"
    rules_path = out_dir / "rules.md"
    if summary_path.exists() and rules_path.exists():
        print(f"  [skip] resumen ya existe en {out_dir}")
        return

    texto = txt_path.read_text(encoding="utf-8")
    trozos = list(_trozos(texto, PALABRAS_POR_TROZO, SOLAPE))
    print(f"  {len(texto.split())} palabras -> {len(trozos)} trozos (MAP)")

    notas = []
    for i, ch in enumerate(trozos, 1):
        print(f"    MAP trozo {i}/{len(trozos)}")
        nota = _ollama_chat(model, SYS_MAP, PROMPT_MAP.format(chunk=ch))
        notas.append(f"### Fragmento {i}\n{nota}")
    notas_join = "\n\n".join(notas)

    print("  REDUCE -> summary.md")
    summary = _ollama_chat(
        model, SYS_MAP, PROMPT_REDUCE_SUMMARY.format(notas=notas_join, nombre=nombre),
        num_ctx=16384,
    )
    summary_path.write_text(summary + "\n", encoding="utf-8")

    print("  REDUCE -> rules.md")
    rules = _ollama_chat(
        model, SYS_MAP, PROMPT_REDUCE_RULES.format(notas=notas_join, nombre=nombre),
        num_ctx=16384,
    )
    rules_path.write_text(rules + "\n", encoding="utf-8")
    print(f"  ✓ summary.md + rules.md")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--nombre", default=None)
    args = ap.parse_args()
    nombre = args.nombre or args.out_dir.name
    resumir(args.out_dir, args.model, nombre)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
