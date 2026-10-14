# Evaluación y resultados

[← Volver al README](../README.md)

## Cómo se evaluó

**Documentos.** 24 procedimientos ficticios de "Faena Cerro Alto" ([`documentos/`](../documentos/)), de 9 áreas. Varios se parecen a propósito: dos tablas de aprobaciones con montos distintos (compras y contratos de servicios), dos pautas de mantención (camiones y palas), dos cursos con distinta vigencia, dos horarios de bodega. `PR-COM-01-v4` es la versión **obsoleta** de la política de compras, con otros montos.

**Preguntas.** [`evaluacion/preguntas.json`](../evaluacion/preguntas.json) tiene 74, cada una con la **sección** que la responde y el dato que la respuesta debe contener:

| Tipo | Cantidad | Ejemplo |
|---|---:|---|
| Directa | 27 | "¿Quién aprueba una solicitud de compra de USD 80.000?" |
| Coloquial | 18 | "¿Puedo pagar con la caja chica una compra de 80 lucas?" |
| Parecida | 12 | "¿Cuál es la meta de disponibilidad física de las palas?" (la de los camiones es otra) |
| Versión | 5 | "¿Quién aprueba una solicitud de compra de USD 150.000?" (la versión obsoleta dice otra persona) |
| Trampa | 3 | "¿Cuál es la velocidad máxima de los camiones?" |
| Trampa *casi* respondible | 9 | "¿A qué hora sale el bus de regreso a Calama?" (el procedimiento solo dice la hora de ida) |

**Métricas.** Búsqueda: acierto@1, @3 y @5 (¿la sección correcta está entre las k primeras?) y MRR@5 sobre las 62 preguntas con respuesta. Respuestas: contiene el dato esperado, cita la sección correcta, pasa la validación y, en las trampas, dice que no está. Las cifras se comparan sin importar cómo se escriban ("30 000" o "30.000", "88%" u "88 %"), sin que una calce dentro de otra.

**Juez de fidelidad.** El mismo modelo parte cada respuesta en afirmaciones y juzga si cada una se deduce de las fuentes. Un juez también se equivoca: antes de usarlo se prueba con 6 casos cuyo puntaje se conoce.

**Límites.**
- Los documentos y las preguntas son inventados y las escribió el mismo autor; una base real tendría PDF escaneados, tablas rotas y preguntas más ambiguas.
- La configuración de la v2 se eligió por su MRR con estas mismas preguntas. Con un conjunto separado el resultado podría bajar algo.
- Es una sola corrida con temperatura 0 y un solo modelo de respuestas.

## Resultados

Medidos con 24 procedimientos ficticios y 74 preguntas, en un computador portátil con una RTX 4070 de 8 GB, con `gpt-oss:20b` para responder y para las tareas auxiliares y `nomic-embed-text` para los embeddings. Todo se reproduce con `evaluar.bat`; cada respuesta, con sus fuentes y su puntaje, está en [`resultados/evaluacion.json`](../resultados/evaluacion.json).

- **Reordenar con el modelo es lo que más aporta.** El acierto en el primer resultado sube de 68 % (búsqueda híbrida con contexto) a 97 %. Cuesta una llamada al modelo por pregunta.
- **Reescribir la pregunta rescata las coloquiales:** el acierto@5 en esas preguntas pasa de 67 % a 83 %, y junto con el reordenamiento llega a 100 %.
- **Contextual Retrieval casi no cambió nada aquí** (acierto@5 de 89 % a 90 %). En el cookbook de Anthropic los trozos eran fragmentos de código sin contexto; aquí cada trozo ya lleva el título del documento y de la sección, que es buena parte de lo que aporta el contexto. Se mantiene porque cuesta poco (12 minutos, una sola vez al indexar).
- **BM25 le gana a los vectores** (87 % contra 81 % de acierto@5): las preguntas traen códigos, montos y nombres de cargos, que es lo que BM25 encuentra bien.
- **Respuestas: 60 de 62 con la v2 contra 54 de 62 con la v1.** Cuando la búsqueda de la v1 falla, el modelo casi siempre dice "No está en los documentos" en vez de inventar: 7 de sus 8 errores son abstenciones.
- **La trampa que nadie atrapa.** "¿De cuánto es el fondo fijo de cada gerencia?": las dos versiones responden CLP 300.000, que es el de las superintendencias. La frase copiada es textual, la cifra está en la fuente y el juez la da por respaldada. Es el tipo de error que una revisión por texto no ve.
- **Vigencia:** sin descartar el documento obsoleto, en 1 de las 5 preguntas de versión el primer resultado es la versión reemplazada.
- **Costo:** la v2 tarda 35 segundos por pregunta y la v1, 11.

### Búsqueda (62 preguntas con respuesta; ¿está la sección correcta entre las k recuperadas?)

| Configuración | Acierto@1 | Acierto@3 | Acierto@5 | MRR@5 | Documento correcto en 4 |
|---|---:|---:|---:|---:|---:|
| BM25 | 76 % | 82 % | 87 % | 0.80 | 95 % |
| Vectores | 65 % | 77 % | 81 % | 0.71 | 85 % |
| Híbrido (v1) | 69 % | 84 % | 89 % | 0.77 | 92 % |
| Híbrido sin descartar obsoletos | 68 % | 82 % | 89 % | 0.75 | 90 % |
| Híbrido + contexto | 68 % | 82 % | 90 % | 0.77 | 90 % |
| Híbrido + contexto + reescritura | 76 % | 90 % | 95 % | 0.83 | 95 % |
| Híbrido + contexto + reordenamiento | 97 % | 98 % | 98 % | 0.98 | 98 % |
| Híbrido + contexto + reescritura + reordenamiento | 98 % | 100 % | 100 % | 0.99 | 100 % |

Sin descartar el documento obsoleto, en 1 de 5 preguntas de versión el primer resultado es la versión obsoleta.

Acierto@5 por tipo de pregunta:

| Configuración | directa | versión | coloquial | parecida |
|---|---:|---:|---:|---:|
| BM25 | 96 % | 100 % | 61 % | 100 % |
| Vectores | 93 % | 100 % | 50 % | 92 % |
| Híbrido (v1) | 96 % | 100 % | 67 % | 100 % |
| Híbrido sin descartar obsoletos | 96 % | 100 % | 67 % | 100 % |
| Híbrido + contexto | 100 % | 100 % | 67 % | 100 % |
| Híbrido + contexto + reescritura | 100 % | 100 % | 83 % | 100 % |
| Híbrido + contexto + reordenamiento | 100 % | 100 % | 94 % | 100 % |
| Híbrido + contexto + reescritura + reordenamiento | 100 % | 100 % | 100 % | 100 % |

### Respuestas

| | v1 | v2 |
|---|---:|---:|
| Búsqueda | Híbrido (v1) | Híbrido + contexto + reescritura + reordenamiento |
| Citas textuales verificadas | no | sí |
| Correctas, preguntas con respuesta | 54 de 62 | 60 de 62 |
| Trampas rechazadas | 11 de 12 | 11 de 12 |
| Citan la sección correcta | 54 de 62 | 61 de 62 |
| No pasan la validación | 1 | 2 |
| Fidelidad promedio (juez) | 0.97 | 0.98 |
| Segundos por pregunta | 11 | 35 |

Juez de fidelidad: acierta 6 de 6 casos de calibración con puntaje conocido.

### Qué cambió después de la primera corrida

La primera corrida completa (unas 3 horas, en [`resultados/corrida-1/`](../resultados/corrida-1/)) mostró errores del validador y del puntaje, no del modelo. Se corrigieron y se volvió a correr: ninguna respuesta tuvo que pedirse de nuevo al modelo (con el validador corregido, varias pasan al primer intento) y solo hubo 16 juicios de fidelidad nuevos.

- **El validador marcaba como inventadas las cifras que el modelo repetía de la pregunta** ("una compra de USD 80.000"). Ahora la pregunta también respalda cifras.
- **Con citas textuales, la línea `[n] "frase"` cuenta como cita** aunque el cuerpo de la respuesta no repita `[n]`.
- **Cinco preguntas se puntuaban mal aunque la respuesta era correcta:** "hasta 50 horas" (se esperaba "550"), la raíz escrita en LaTeX, "7 días de trabajo y 7 de descanso" (se esperaba "7x7"), "medir la tensión" (se esperaba "energía cero") y la trampa de los explosivos: los documentos sí dicen que el procedimiento es PR-EXP-01, así que esa respuesta también vale. Además, el puntaje ahora ignora los guiones tipográficos con que el modelo escribe esos códigos. Cada cambio está en el historial del repo.

| | v1, corrida 1 | v1, final | v2, corrida 1 | v2, final |
|---|---:|---:|---:|---:|
| Correctas, preguntas con respuesta | 52 de 62 | 54 de 62 | 58 de 62 | 60 de 62 |
| Trampas rechazadas | 10 de 12 | 11 de 12 | 11 de 12 | 11 de 12 |
| No pasan la validación | 6 | 1 | 9 | 2 |

**Lo que el validador todavía no hace bien:** marca como inventada una cifra calculada ("hasta 50 horas" es el 10 % de 500; "80 lucas" convertido a 80.000) y no detecta una cifra que está en la fuente pero con otra unidad (la v2 respondió "hasta 10 horas" donde la fuente dice "10 %"). **El juez** acertó los 6 casos de calibración, pero puntuó con 0 dos respuestas correctas y no vio la trampa del fondo fijo: sirve como señal, no como verdad.

## Después de la evaluación: la unidad de las cifras

La validación revisa que cada cifra de la respuesta aparezca en la fuente, pero no con qué unidad, y así se le
escapó p09: la v2 respondió "hasta 10 horas" donde la fuente dice "10 %". El experimento agrega esa comprobación
como opción (`validar(..., unidades=True)`) sin tocar la evaluación de arriba: solo marca las contradicciones
claras, una cifra que en la fuente aparece únicamente con otra unidad.

**Sin modelo, sobre las 148 respuestas guardadas:** marca p09 y ninguna otra; ninguna de las respuestas correctas
de la v1 ni de la v2. Detalle en [`resultados/experimento-unidades.md`](../resultados/experimento-unidades.md).

**Con el modelo** falta correrlo: `experimento-unidades.bat` (o `uv run rag evaluar --unidades`) vuelve a
responder con la configuración de la v2 más la comprobación. Con la caché de la evaluación, solo p09 pide una
llamada nueva al modelo (el reintento), así que toma unos minutos. Dirá si al avisarle "la fuente dice 10 %" el
modelo corrige la respuesta; si no la corrige, la respuesta queda marcada como no validada, que también es
información.

No cubre el otro tipo de error que queda: en p72 la cifra y su unidad están bien, pero son de otro cargo
(superintendencias en vez de gerencias). Para eso no basta con revisar el texto.
