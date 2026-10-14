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
| Correctas, preguntas con respuesta | 52 de 62 | 58 de 62 |
| Trampas rechazadas | 10 de 12 | 11 de 12 |
| Citan la sección correcta | 54 de 62 | 58 de 62 |
| No pasan la validación | 6 | 9 |
| Fidelidad promedio (juez) | 0.98 | 0.97 |
| Segundos por pregunta | 12 | 37 |

Juez de fidelidad: acierta 6 de 6 casos de calibración con puntaje conocido.
