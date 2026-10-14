# Experimento: la unidad de las cifras

La validación revisa que cada cifra de la respuesta aparezca en la fuente, pero no con qué unidad: en la
evaluación, la v2 respondió "hasta 10 horas" donde la fuente dice "10 %". Este experimento agrega esa
comprobación (`validar(..., unidades=True)`) y la mide sin cambiar la evaluación guardada.

## Sin modelo: sobre las respuestas guardadas

- **v1:** marca 0 de 74 respuestas: 0 de sus 9 incorrectas y 0 correctas.
- **v2:** marca 1 de 74 respuestas: 1 de sus 3 incorrectas y 0 correctas.
  - p09: la cifra 10 horas aparece en la fuente como 10 %

Falta la parte con modelo: `uv run rag evaluar --unidades` con Ollama abierto.
