## ADDED Requirements

### Requirement: El progreso se emite solo cuando cambia
`GET /api/progress` SHALL enviar una instantánea de las sesiones al conectar y después solo cuando el almacén de sesiones haya cambiado desde el último envío.

#### Scenario: Conexión
- **WHEN** un cliente se conecta
- **THEN** recibe de inmediato un evento `data:` con la lista de sesiones

#### Scenario: Sin cambios
- **WHEN** pasan 5 intervalos sin escrituras en el almacén
- **THEN** no se envía ningún evento `data:` adicional

#### Scenario: Cambio de estado de un video
- **WHEN** un video pasa de `transcribing` a `summarizing`
- **THEN** en el siguiente intervalo se envía un evento `data:` con el nuevo estado

#### Scenario: Cliente desconectado
- **WHEN** el cliente cierra la conexión
- **THEN** el generador termina en el siguiente intervalo

### Requirement: Latido
El flujo de progreso SHALL enviar una línea de comentario `: ping` tras 15 intervalos consecutivos sin eventos de datos.

#### Scenario: Inactividad prolongada
- **WHEN** pasan 15 intervalos sin cambios
- **THEN** se envía `: ping` seguido de una línea en blanco y el contador se reinicia

### Requirement: Revisión del almacén
El almacén de sesiones SHALL exponer un contador de revisión que aumenta en cada escritura.

#### Scenario: Escritura
- **WHEN** se crea una sesión o se actualiza un video
- **THEN** `revision` es mayor que antes

#### Scenario: Lectura
- **WHEN** solo se leen sesiones
- **THEN** `revision` no cambia
