## ADDED Requirements

### Requirement: Selección semántica de fragmentos en grabaciones largas
Cuando la transcripción no cabe entera y existe el recuperador semántico, el chat por grabación SHALL elegir los fragmentos de transcripción por similitud con la pregunta en lugar de por palabras clave, indexando la grabación si hace falta, y SHALL volver a la selección por palabras clave si la recuperación falla.

#### Scenario: Grabación larga con índice
- **WHEN** se pregunta sobre un video cuya transcripción supera el presupuesto y tiene índice vigente
- **THEN** el evento `meta` trae `context_mode: "semantic"` y los fragmentos del contexto están en orden cronológico dentro del presupuesto

#### Scenario: Grabación larga sin índice
- **WHEN** el video no tiene índice vigente
- **THEN** se emite `{"type":"status","detail":"Indexando la grabación…"}`, se indexa, y luego `meta` trae `context_mode: "semantic"`

#### Scenario: Fallo de recuperación
- **WHEN** el servicio de embeddings falla
- **THEN** `meta` trae `context_mode: "excerpts"`, no se emite evento `error` por ese motivo y la respuesta continúa

#### Scenario: Grabación corta
- **WHEN** la transcripción cabe entera
- **THEN** `context_mode` es `full` y no se consulta el índice

### Requirement: Mensajes con fuentes opcionales
Los mensajes del historial SHALL admitir un campo opcional `sources` y los historiales existentes sin ese campo SHALL seguir leyéndose.

#### Scenario: Mensaje antiguo
- **WHEN** se carga un `chat.json` creado antes de este cambio
- **THEN** cada mensaje tiene `sources` vacío

#### Scenario: Mensaje sin fuentes
- **WHEN** se guarda un mensaje con `sources` vacío
- **THEN** el JSON en disco no incluye la clave `sources`
