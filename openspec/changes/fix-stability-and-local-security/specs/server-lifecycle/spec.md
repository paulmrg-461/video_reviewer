## ADDED Requirements

### Requirement: Apagado limpio
Al apagarse, el servidor SHALL cancelar el worker de procesamiento y detener todas las grabadoras activas sin lanzar excepciones.

#### Scenario: Apagado con grabadoras activas
- **WHEN** termina el contexto `lifespan` de la aplicación
- **THEN** `stop_recording_use_case.stop_all_recorders` se invoca exactamente una vez y no se propaga ninguna excepción

#### Scenario: Worker cancelado
- **WHEN** termina el contexto `lifespan`
- **THEN** la tarea del worker creada al arrancar queda en estado terminado (`done()` es verdadero)

### Requirement: Arranque del worker
Al arrancar, el servidor SHALL iniciar exactamente una tarea de worker que consume la cola de procesamiento.

#### Scenario: Arranque
- **WHEN** se entra en el contexto `lifespan`
- **THEN** existe una tarea asyncio ejecutando `worker()`
