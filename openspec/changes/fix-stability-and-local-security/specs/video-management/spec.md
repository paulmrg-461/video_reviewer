## ADDED Requirements

### Requirement: Alta de videos con rechazos explícitos
Al añadir videos a una sesión, el sistema SHALL devolver por separado los videos añadidos y las rutas rechazadas con su motivo, y MUST NOT encolar ninguna ruta rechazada.

#### Scenario: Mezcla de rutas válidas e inválidas
- **WHEN** se envía `paths` con una ruta válida y una inexistente
- **THEN** la respuesta contiene `added` con 1 elemento y `rejected` con 1 elemento `{path, reason: "no existe"}`, y la cola recibe exactamente 1 tarea

#### Scenario: Todas las rutas rechazadas
- **WHEN** todas las rutas están fuera de las carpetas permitidas
- **THEN** la respuesta es 200 con `added: []`, `rejected` con todas ellas, y la cola no recibe tareas

#### Scenario: Rutas vacías
- **WHEN** `paths` contiene cadenas vacías o solo espacios
- **THEN** se ignoran y no aparecen en `rejected`

#### Scenario: La interfaz informa los rechazos
- **WHEN** la respuesta trae `rejected` no vacío
- **THEN** la UI muestra bajo el campo de rutas cada ruta rechazada con su motivo y conserva en el campo solo las rutas rechazadas

### Requirement: No se elimina un video en proceso
El sistema SHALL rechazar la eliminación de un video cuyo estado sea `extracting_audio`, `transcribing`, `analyzing_visual` o `summarizing`.

#### Scenario: Borrado durante la transcripción
- **WHEN** se llama a `DELETE /api/sessions/{sid}/videos/{vid}` y el video está en `transcribing`
- **THEN** la respuesta es 409, el video sigue en la sesión y su carpeta no se borra

#### Scenario: Borrado de un video en cola
- **WHEN** el video está en `queued`
- **THEN** la respuesta es 200, el video desaparece de la sesión y el worker ignora su tarea al desencolarla

#### Scenario: Borrado de un video terminado
- **WHEN** el video está en `done` o `error`
- **THEN** la respuesta es 200 y su carpeta `sessions/<sid>/<vid>/` se elimina
