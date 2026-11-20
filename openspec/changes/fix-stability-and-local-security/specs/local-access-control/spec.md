## ADDED Requirements

### Requirement: Interfaz de red por defecto
El servidor SHALL escuchar en `127.0.0.1` salvo que la variable de entorno `VIDEO_REVIEWER_HOST` indique otra interfaz, y MUST advertir por stderr cuando se expone fuera de loopback.

#### Scenario: Arranque sin configuración
- **WHEN** se ejecuta `./pipeline/run.sh server` sin `VIDEO_REVIEWER_HOST`
- **THEN** uvicorn recibe `--host 127.0.0.1`

#### Scenario: Exposición explícita a la LAN
- **WHEN** se ejecuta con `VIDEO_REVIEWER_HOST=0.0.0.0`
- **THEN** uvicorn recibe `--host 0.0.0.0` y se imprime en stderr una línea que contiene `ADVERTENCIA` y `sin autenticación`

### Requirement: Solo se procesan archivos multimedia dentro de raíces permitidas
El sistema SHALL aceptar como video de entrada únicamente archivos existentes cuya ruta resuelta esté bajo una raíz de entrada configurada y cuya extensión sea multimedia (`.mp4 .mkv .mov .webm .avi .m4v .mp3 .m4a .wav .ogg .flac .opus`).

#### Scenario: Archivo válido dentro de una raíz
- **WHEN** se evalúa `<raíz>/reunion.mp4` y el archivo existe
- **THEN** la política devuelve la ruta resuelta absoluta

#### Scenario: Archivo fuera de las raíces
- **WHEN** se evalúa `/etc/passwd.mp4` existente y `/etc` no es raíz
- **THEN** se rechaza con motivo `fuera de las carpetas permitidas`

#### Scenario: Extensión no multimedia
- **WHEN** se evalúa `<raíz>/.ssh/id_rsa`
- **THEN** se rechaza con motivo `tipo de archivo no permitido`

#### Scenario: Escape mediante `..` o symlink
- **WHEN** se evalúa `<raíz>/../fuera/video.mp4` o un symlink dentro de la raíz que apunta fuera de ella
- **THEN** se rechaza con motivo `fuera de las carpetas permitidas`

#### Scenario: Archivo inexistente
- **WHEN** se evalúa una ruta que no existe
- **THEN** se rechaza con motivo `no existe`

### Requirement: La exportación solo escribe dentro de raíces de exportación
El sistema SHALL copiar artefactos únicamente a carpetas cuya ruta resuelta esté bajo una raíz de exportación configurada y que no contengan componentes ocultos (que empiecen por `.`) relativos a esa raíz, y MUST limitar los nombres de archivo exportables a `summary.md`, `analysis.md`, `transcript.txt`, `transcript.srt`, `visual_notes.md`.

#### Scenario: Destino permitido
- **WHEN** se llama a `POST /api/sessions/{sid}/videos/{vid}/save` con `target_dir` bajo una raíz de exportación
- **THEN** la respuesta es 200 y `saved` lista las rutas copiadas

#### Scenario: Destino fuera de las raíces
- **WHEN** `target_dir` es `/etc/cron.d`
- **THEN** la respuesta es 403, no se crea ningún directorio y no se copia ningún archivo

#### Scenario: Destino oculto
- **WHEN** `target_dir` es `<raíz>/.ssh`
- **THEN** la respuesta es 403 con motivo `carpeta oculta no permitida`

#### Scenario: Nombre de archivo con traversal
- **WHEN** `files` contiene `../../sessions.json`
- **THEN** la respuesta es 422 y no se copia ningún archivo, ni siquiera los válidos de la misma petición

### Requirement: Identificadores de ruta validados
Todas las rutas HTTP con parámetros `sid` o `vid` SHALL rechazar con 422 los valores que no cumplan `^[A-Za-z0-9_-]{1,64}$`.

#### Scenario: Id con puntos codificados
- **WHEN** se llama a `GET /api/sessions/%2e%2e/videos/%2e%2e/transcript`
- **THEN** la respuesta es 422 y no se lee ningún archivo

#### Scenario: Id válido inexistente
- **WHEN** se llama a `GET /api/sessions/abcdef123456/videos/abcdef123456/transcript` y no existe
- **THEN** la respuesta es 404
