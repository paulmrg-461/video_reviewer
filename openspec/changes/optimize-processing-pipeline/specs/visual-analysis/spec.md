## ADDED Requirements

### Requirement: Deduplicación de frames antes del análisis de visión
Cuando la deduplicación está activa (umbral mayor que 0), el análisis visual SHALL describir solo los frames cuya diferencia con el último frame conservado sea mayor o igual al umbral, SHALL conservar siempre el primer frame y al menos un frame cada `max_gap` frames, y MUST mantener para cada nota el tiempo real del frame original.

#### Scenario: Pantalla estática
- **WHEN** hay 6 frames idénticos, umbral 3.0 y `max_gap` 8
- **THEN** solo se describe el frame 0

#### Scenario: Cambio de pantalla
- **WHEN** los frames 0–2 son idénticos y los frames 3–5 son idénticos entre sí y distintos de los anteriores
- **THEN** se describen los frames 0 y 3, y la nota del segundo lleva el tiempo `3 × intervalo`

#### Scenario: Cambio gradual
- **WHEN** cada frame difiere del anterior menos que el umbral pero la diferencia acumulada respecto al último conservado lo alcanza en el frame 4
- **THEN** el frame 4 se conserva

#### Scenario: Intervalo máximo
- **WHEN** hay 20 frames idénticos y `max_gap` es 8
- **THEN** se conservan los frames 0, 8 y 16

#### Scenario: Desactivada
- **WHEN** el umbral es 0
- **THEN** se describen todos los frames y no se piden firmas

#### Scenario: Firmas no disponibles
- **WHEN** la obtención de firmas falla o su número no coincide con el de frames
- **THEN** se describen todos los frames y se registra por consola que la deduplicación se omitió

### Requirement: Firmas de frame sin dependencias adicionales
El sistema SHALL obtener una firma de 1024 bytes (32×32 en escala de grises) por frame mediante ffmpeg, con el mismo muestreo temporal que la extracción de frames.

#### Scenario: Salida de ffmpeg
- **WHEN** ffmpeg devuelve 3072 bytes
- **THEN** se obtienen 3 firmas de 1024 bytes

#### Scenario: Bloque final incompleto
- **WHEN** ffmpeg devuelve 2500 bytes
- **THEN** se obtienen 2 firmas y los 452 bytes restantes se descartan

#### Scenario: ffmpeg falla
- **WHEN** ffmpeg termina con código distinto de cero
- **THEN** se lanza `FrameExtractionError`
