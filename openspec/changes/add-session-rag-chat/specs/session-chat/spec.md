## ADDED Requirements

### Requirement: Preguntar sobre todas las grabaciones de una sesión
El sistema SHALL responder preguntas usando las grabaciones en estado `done` de una sesión, como flujo `text/event-stream` con eventos en orden: `status` opcional, `meta`, `token`*, y `done` o `error`.

#### Scenario: Pregunta respondida
- **WHEN** se hace `POST /api/sessions/{sid}/chat` con una pregunta y la sesión tiene dos videos `done`
- **THEN** la respuesta es 200, el evento `meta` trae `context_mode: "retrieval"` y `sources` no vacío, y el último evento es `done`

#### Scenario: Sesión inexistente
- **WHEN** la sesión no existe
- **THEN** la respuesta es 404

#### Scenario: Sin grabaciones analizadas
- **WHEN** ningún video de la sesión está en `done`
- **THEN** la respuesta es 409 con `detail` `Esta sesión no tiene grabaciones analizadas.`

#### Scenario: GPU ocupada
- **WHEN** el candado de GPU tiene propietario
- **THEN** la respuesta es 409 y no se llama al modelo

#### Scenario: Mensaje inválido
- **WHEN** el mensaje está vacío o supera 3000 caracteres
- **THEN** la respuesta es 422

### Requirement: Indexado perezoso de grabaciones antiguas
Antes de recuperar, el sistema SHALL indexar las grabaciones `done` de la sesión que no tengan índice vigente e informar de ello con un evento `status`.

#### Scenario: Grabaciones sin índice
- **WHEN** 2 de 3 grabaciones `done` no tienen índice vigente
- **THEN** el primer evento es `{"type":"status","detail":"Indexando 2 grabación(es)…"}` y tras el flujo las 3 tienen índice

#### Scenario: Todo indexado
- **WHEN** todas las grabaciones tienen índice vigente
- **THEN** no se emite evento `status`

#### Scenario: Una grabación no se puede indexar
- **WHEN** el indexado de una grabación falla
- **THEN** el chat continúa con las demás

### Requirement: Contexto con resúmenes y fragmentos citables
El contexto del chat de sesión SHALL contener un bloque de resúmenes por grabación (máx. 1500 palabras) y los fragmentos recuperados etiquetados `[S1]`, `[S2]`… con nombre de la grabación, tiempo y tipo, sin superar 5200 palabras.

#### Scenario: Etiquetas de fuente
- **WHEN** se recuperan 3 fragmentos
- **THEN** el contexto los contiene como `[S1]`, `[S2]`, `[S3]` y `sources` tiene 3 elementos con `id`, `video_id`, `video_name`, `kind`, `start` y `preview`

#### Scenario: Presupuesto
- **WHEN** los fragmentos recuperados suman más palabras de las disponibles
- **THEN** se incluyen por orden de puntuación solo los que caben y `sources` lista únicamente los incluidos

#### Scenario: Muchas grabaciones
- **WHEN** los resúmenes de todas las grabaciones no caben en 1500 palabras
- **THEN** se incluyen los que caben y una línea `(y N grabaciones más)`

### Requirement: Historial de sesión con fuentes
El sistema SHALL guardar el historial del chat de sesión en `sessions/<sid>/chat.json`, incluyendo en cada respuesta del asistente las fuentes usadas.

#### Scenario: Fuentes persistidas
- **WHEN** un flujo termina con `done` y se consulta `GET /api/sessions/{sid}/chat`
- **THEN** el mensaje del asistente incluye `sources` igual al del evento `meta`

#### Scenario: Historial previo sin fuentes
- **WHEN** `chat.json` contiene mensajes sin el campo `sources`
- **THEN** se leen correctamente con `sources` vacío

#### Scenario: Borrado
- **WHEN** se hace `DELETE /api/sessions/{sid}/chat`
- **THEN** el historial queda vacío y los índices de los videos no se tocan

### Requirement: Chat de sesión en la interfaz
La interfaz SHALL ofrecer un botón `Chat de la sesión` en la cabecera de la sesión que abre el panel de detalle en modo chat, sin pestañas de video, y SHALL mostrar bajo cada respuesta las fuentes citadas como controles que abren la grabación en el punto citado.

#### Scenario: Apertura
- **WHEN** el usuario pulsa `Chat de la sesión`
- **THEN** el panel muestra el título `Chat de la sesión`, el nombre de la sesión, el chat, y las pestañas de video quedan ocultas

#### Scenario: Sin grabaciones analizadas
- **WHEN** ningún video de la sesión está `done`
- **THEN** el botón está deshabilitado y explica el motivo

#### Scenario: Cita de transcripción
- **WHEN** el usuario activa `[S2]` cuya fuente es de tipo `transcript` con `start` 754
- **THEN** se abre el detalle de esa grabación en la pestaña de subtítulos con el cue de 00:12:34 enfocado

#### Scenario: Cita de resumen
- **WHEN** la fuente es de tipo `summary`
- **THEN** se abre esa grabación en la pestaña Resumen

#### Scenario: Cita inexistente
- **WHEN** la respuesta contiene `[S9]` y no hay fuente `S9`
- **THEN** se muestra como texto plano, sin control

#### Scenario: Estado de indexado
- **WHEN** llega un evento `status`
- **THEN** su texto se muestra en la burbuja provisional hasta que llegue el primer `token`

#### Scenario: Volver a un video
- **WHEN** tras usar el chat de sesión el usuario selecciona un video
- **THEN** el panel vuelve al modo video con sus pestañas visibles
