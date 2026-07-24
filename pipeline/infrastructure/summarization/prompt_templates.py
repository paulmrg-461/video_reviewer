"""Prompt templates for the map-reduce summarization pipeline.

Ported VERBATIM from `pipeline/summarize.py`'s `_build_prompts()` and
`_build_visual_map_prompt()` — every string here must match the original
byte-for-byte. Any wording/punctuation/section-header change here is a real
behavior change to what the LLM produces, so treat this file as the single
most fidelity-sensitive file in this migration step.
"""
from __future__ import annotations

SYS_DEFAULT = (
    "Eres un analista profesional. Revisas transcripciones de video y extraes "
    "información relevante con precisión. No inventas. Conservas nombres, cifras, "
    "fechas y datos exactos. Respondes en español."
)


def build_prompts(instructions: str | None, nombre: str):
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


def build_visual_map_prompt(instructions: str | None) -> str:
    if instructions:
        return (
            f"Estas son notas de descripciones de pantalla (capturas cada pocos segundos) de "
            f"una grabación. Extrae SOLO lo relacionado con: {instructions}\n\n"
            f"Usa viñetas cortas. Conserva las referencias de tiempo [HH:MM:SS].\n\n"
            f"--- NOTAS DE PANTALLA ---\n{{chunk}}\n--- FIN NOTAS DE PANTALLA ---"
        )
    return (
        "Estas son notas de descripciones de pantalla (capturas cada pocos segundos) de una "
        "grabación. Extrae en viñetas cortas los elementos relevantes: aplicaciones usadas, "
        "texto o datos visibles, cambios importantes de contenido. Conserva las referencias "
        "de tiempo [HH:MM:SS].\n\n"
        "--- NOTAS DE PANTALLA ---\n{chunk}\n--- FIN NOTAS DE PANTALLA ---"
    )
