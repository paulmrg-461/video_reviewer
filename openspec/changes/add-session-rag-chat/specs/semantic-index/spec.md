## ADDED Requirements

### Requirement: Troceado de artefactos
El sistema SHALL dividir los artefactos de un video en fragmentos indexables: ventanas de transcripción de ~120 palabras con tiempo de inicio y fin, una nota de pantalla por fragmento con su tiempo, y una sección `## ` de resumen o análisis por fragmento (máx. 300 palabras).

#### Scenario: Transcripción
- **WHEN** se trocea un video con 10 segmentos de 50 palabras
- **THEN** se obtienen fragmentos `kind == "transcript"` con `start`/`end` de sus segmentos extremos y texto en líneas `[HH:MM:SS] ...`

#### Scenario: Notas de pantalla
- **WHEN** `visual_notes.md` contiene `### [00:00:15]` seguido de una descripción
- **THEN** se obtiene un fragmento `kind == "visual"` con `start == 15.0`

#### Scenario: Notas con error
- **WHEN** una nota de pantalla empieza por `(error analizando frame`
- **THEN** no se genera fragmento para ella

#### Scenario: Secciones largas
- **WHEN** una sección de `analysis.md` tiene 700 palabras
- **THEN** se generan 3 fragmentos `kind == "analysis"` y cada uno empieza con el encabezado de la sección

#### Scenario: Sin contenido
- **WHEN** todos los artefactos están vacíos
- **THEN** la lista de fragmentos es vacía

### Requirement: Embeddings locales con prefijos de tarea
El sistema SHALL obtener los embeddings desde Ollama con el modelo configurado, anteponiendo `search_document: ` a los fragmentos y `search_query: ` a las preguntas, en lotes de 32.

#### Scenario: Lotes
- **WHEN** se piden embeddings de 70 fragmentos
- **THEN** se hacen 3 peticiones (32, 32, 6) y se devuelven 70 vectores en el mismo orden

#### Scenario: Prefijo de consulta
- **WHEN** se pide el embedding de una pregunta
- **THEN** el texto enviado empieza por `search_query: ` y la petición lleva `keep_alive` 0

#### Scenario: Ollama no disponible
- **WHEN** la conexión falla o la respuesta no es 200
- **THEN** se lanza `EmbeddingError`

#### Scenario: Respuesta incompleta
- **WHEN** Ollama devuelve menos vectores que textos enviados
- **THEN** se lanza `EmbeddingError`

### Requirement: Índice por video con control de frescura
El sistema SHALL guardar por video los vectores normalizados (`index.npz`) y sus fragmentos con el modelo y la huella de los artefactos (`index.json`), y SHALL considerar el índice vigente solo si modelo y huella coinciden.

#### Scenario: Índice vigente
- **WHEN** se indexa un video y se vuelve a pedir el indexado sin cambios
- **THEN** la segunda llamada devuelve 0 y no pide embeddings

#### Scenario: Artefactos cambiados
- **WHEN** cambia `summary.md` tras indexar
- **THEN** `is_fresh` es falso y el siguiente indexado reescribe el índice

#### Scenario: Modelo de embeddings cambiado
- **WHEN** el índice se creó con otro modelo
- **THEN** `is_fresh` es falso

#### Scenario: Escritura atómica
- **WHEN** termina una escritura
- **THEN** no quedan archivos temporales y `index.json` se escribió después de `index.npz`

### Requirement: Búsqueda por similitud
El sistema SHALL devolver los `top_k` fragmentos con mayor similitud coseno a la consulta entre los videos indicados, en orden descendente, ignorando índices ausentes o corruptos.

#### Scenario: Orden por similitud
- **WHEN** hay tres fragmentos con vectores `[1,0]`, `[0.7,0.7]`, `[0,1]` y la consulta es `[1,0]`
- **THEN** el orden devuelto es el primero, el segundo y el tercero

#### Scenario: Varios videos
- **WHEN** se busca en dos videos con índice
- **THEN** los resultados pueden venir de ambos y cada uno conserva su `video_id`

#### Scenario: Índice corrupto
- **WHEN** el número de fragmentos de `index.json` no coincide con las filas de `index.npz`
- **THEN** ese video se ignora y la búsqueda continúa con los demás

#### Scenario: Sin índices
- **WHEN** ningún video indicado tiene índice
- **THEN** el resultado es una lista vacía

### Requirement: Indexado al terminar el procesamiento, no fatal
El procesamiento de un video SHALL indexarlo antes de marcarlo como terminado, y un fallo del indexado MUST NOT impedir que el video termine en `done`.

#### Scenario: Indexado correcto
- **WHEN** un video termina de resumirse
- **THEN** existen `index.npz` e `index.json` en su carpeta cuando su estado pasa a `done`

#### Scenario: Indexado fallido
- **WHEN** el indexado lanza una excepción
- **THEN** el video termina en `done`, se registra un aviso por consola y no hay índice
