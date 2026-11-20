## ADDED Requirements

### Requirement: Uso exclusivo de la GPU
El sistema SHALL garantizar que el procesamiento de videos y el chat nunca usan la GPU a la vez, mediante un único candado con propietario (`processing` o `chat`).

#### Scenario: Chat mientras se procesa
- **WHEN** el worker tiene el candado y llega un `POST .../chat`
- **THEN** la respuesta es 409 con `detail` `GPU ocupada procesando videos. Intenta cuando termine.` y no se llama al modelo

#### Scenario: Procesamiento mientras hay chat
- **WHEN** un flujo de chat tiene el candado y el worker desencola un video
- **THEN** el worker espera a que el chat termine y solo entonces procesa

#### Scenario: Carrera entre validación y flujo
- **WHEN** el candado se ocupa entre la validación de la petición y el inicio del flujo
- **THEN** el flujo emite un único evento `{"type":"error","detail":"GPU ocupada"}` y termina

### Requirement: El candado siempre se libera
El sistema MUST liberar el candado cuando termina el trabajo que lo tomó, incluidos los casos de error, cancelación y desconexión del cliente.

#### Scenario: Error del modelo en el chat
- **WHEN** el modelo falla durante un flujo de chat
- **THEN** al terminar el flujo el propietario del candado es `null`

#### Scenario: Cliente desconectado
- **WHEN** el cliente cierra la conexión a mitad del flujo
- **THEN** el propietario del candado vuelve a `null`

#### Scenario: Excepción en el procesamiento
- **WHEN** `process_video_use_case.execute` lanza una excepción inesperada
- **THEN** el worker libera el candado y sigue con la siguiente tarea

### Requirement: Descarga del modelo de chat antes de procesar
Al tomar el candado para procesar, el worker SHALL pedir a Ollama que descargue el modelo de chat.

#### Scenario: Procesar tras chatear
- **WHEN** el worker adquiere el candado
- **THEN** se invoca `release(CHAT_MODEL)` del planificador de GPU antes de ejecutar el caso de uso de procesamiento

### Requirement: Estado de la GPU en health
`GET /api/health` SHALL incluir `gpu_owner` con valor `null`, `"processing"` o `"chat"`.

#### Scenario: GPU libre
- **WHEN** nadie tiene el candado
- **THEN** `gpu_owner` es `null`

#### Scenario: Procesando
- **WHEN** el worker tiene el candado
- **THEN** `gpu_owner` es `"processing"`
