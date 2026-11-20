## ADDED Requirements

### Requirement: Escritura atómica de sessions.json
El almacén de sesiones SHALL persistir cada cambio escribiendo un archivo temporal en el mismo directorio y sustituyendo el archivo final con una operación atómica, de modo que `sessions.json` contenga siempre un JSON completo (el anterior o el nuevo).

#### Scenario: Guardado normal
- **WHEN** se guarda una sesión nueva
- **THEN** `sessions.json` contiene la sesión y no queda ningún archivo `sessions.json.tmp`

#### Scenario: Fallo durante la escritura
- **WHEN** la escritura del archivo temporal lanza una excepción
- **THEN** `sessions.json` conserva byte a byte su contenido anterior

### Requirement: Detección de archivo corrupto
El almacén de sesiones MUST lanzar `SessionsFileCorruptError` cuando `sessions.json` existe y no es JSON válido, y MUST NOT sobrescribirlo ni tratarlo como vacío.

#### Scenario: JSON truncado
- **WHEN** `sessions.json` contiene `{"sessions": {` y se invoca `list_sessions()`
- **THEN** se lanza `SessionsFileCorruptError` cuyo mensaje incluye la ruta del archivo, y el archivo queda sin modificar

#### Scenario: Archivo inexistente
- **WHEN** `sessions.json` no existe y se invoca `list_sessions()`
- **THEN** devuelve una lista vacía
