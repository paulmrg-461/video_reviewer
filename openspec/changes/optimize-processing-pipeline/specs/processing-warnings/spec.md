## ADDED Requirements

### Requirement: Avisos de calidad por video
Cada video SHALL acumular avisos en lenguaje claro sobre condiciones que pueden degradar su resultado (contexto del modelo desbordado, audio recuperado parcialmente, imágenes no extraídas), sin duplicados y con un máximo de 10.

#### Scenario: Contexto desbordado
- **WHEN** durante el resumen el modelo informa de un prompt que llena el contexto
- **THEN** el video terminado tiene el aviso `El texto no cupo en el contexto del modelo; parte del análisis puede faltar o ser impreciso.`

#### Scenario: Audio parcial
- **WHEN** la extracción de audio solo recupera parte del audio
- **THEN** el video tiene el aviso `El audio estaba dañado y se recuperó solo en parte; la transcripción puede estar incompleta.`

#### Scenario: Frames no extraídos
- **WHEN** falla la extracción de frames
- **THEN** el video termina en `done` con el aviso `No se pudieron extraer imágenes del video; el análisis no incluye lo mostrado en pantalla.`

#### Scenario: Aviso repetido
- **WHEN** el mismo aviso se produce 5 veces en un video
- **THEN** aparece una sola vez

#### Scenario: Sin avisos
- **WHEN** el procesamiento no produce avisos
- **THEN** `warnings` es una lista vacía

### Requirement: Los avisos no se mezclan entre videos
Los avisos producidos al procesar un video MUST asignarse solo a ese video.

#### Scenario: Dos videos consecutivos
- **WHEN** el primer video produce un aviso y el segundo ninguno
- **THEN** el segundo tiene `warnings` vacío

#### Scenario: Video que termina en error
- **WHEN** un video produce un aviso y luego falla
- **THEN** el video en `error` conserva el aviso y el siguiente video empieza sin avisos

### Requirement: Avisos persistidos y expuestos
Los avisos SHALL guardarse en `sessions.json`, devolverse en el campo `warnings` de cada video en la API y en el flujo de progreso, y vaciarse al reintentar el video.

#### Scenario: Persistencia
- **WHEN** se reinicia el servidor
- **THEN** un video con avisos los conserva

#### Scenario: Datos antiguos
- **WHEN** `sessions.json` contiene videos sin el campo `warnings`
- **THEN** se leen con `warnings` vacío

#### Scenario: Reintento
- **WHEN** se reintenta un video en `error` que tenía avisos
- **THEN** sus avisos quedan vacíos al volver a `queued`
