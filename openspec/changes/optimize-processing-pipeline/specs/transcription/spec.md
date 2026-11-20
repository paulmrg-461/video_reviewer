## ADDED Requirements

### Requirement: Idioma automático
Cuando el idioma solicitado es `auto` o vacío, la transcripción SHALL pedir a Whisper detección automática (idioma `None`) y registrar el idioma detectado en la transcripción.

#### Scenario: Idioma auto
- **WHEN** se transcribe con idioma `auto`
- **THEN** el modelo recibe `language=None` y `Transcript.language` es el idioma detectado

#### Scenario: Idioma explícito
- **WHEN** se transcribe con idioma `es`
- **THEN** el modelo recibe `language="es"`

### Requirement: Transcripción por lotes opcional
Cuando `WHISPER_BATCH_SIZE` es mayor que 1, la transcripción SHALL usar la tubería por lotes de faster-whisper con ese tamaño y las mismas opciones de decodificación y filtros anti-alucinación que el modo en serie; en otro caso SHALL usar el modo en serie.

#### Scenario: Lotes activados
- **WHEN** `batch_size` es 8
- **THEN** se invoca la tubería por lotes con `batch_size=8`, `vad_filter=True`, `condition_on_previous_text=False`, `temperature=0.0` y los umbrales actuales

#### Scenario: Lotes desactivados
- **WHEN** `batch_size` es 0 o 1
- **THEN** se invoca `WhisperModel.transcribe` sin argumento `batch_size`

#### Scenario: Filtro de repeticiones
- **WHEN** en cualquiera de los dos modos llegan tres segmentos consecutivos con el mismo texto
- **THEN** la transcripción conserva solo el primero

### Requirement: Glosario de términos propios
Si existe el archivo de glosario, la transcripción SHALL pasar sus términos a Whisper como `hotwords`; si no existe o está vacío, SHALL transcribir sin `hotwords`.

#### Scenario: Glosario presente
- **WHEN** el archivo contiene `Levapan`, una línea vacía, `# comentario` y `levapan`
- **THEN** `hotwords` es `Levapan`

#### Scenario: Glosario ausente
- **WHEN** el archivo no existe
- **THEN** `hotwords` es `None`

#### Scenario: Glosario demasiado largo
- **WHEN** el archivo tiene 150 términos distintos
- **THEN** se usan los 100 primeros y se registra un aviso por consola
