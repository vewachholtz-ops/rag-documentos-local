# Para agentes (Codex, Claude y otros)

1. Lee `PLAN.md` (qué se está construyendo, decisiones, API y tabla de tareas) y `ESTADO.md` (dónde quedó el
   último que trabajó y el siguiente paso).
2. Marca en la tabla de `PLAN.md` la tarea que tomas. No tomes una que está "en curso" por otro sin que lo pida
   Vicente.
3. Pruebas antes de cada commit:
   ```
   uv run ruff check . && uv run ruff format --check . && uv run pytest
   cd interfaz && npm ci && npm run build      # solo si tocaste interfaz/; sube también app/
   ```
4. Al terminar o si te quedas sin tokens: commit (en tu rama si está a medias) y actualiza `ESTADO.md`.

Reglas:

- `app/` es la salida de `npm run build`: no se edita a mano.
- No cambies los prompts de `textos="procedimientos"` ni `resultados/`: con ellos se hizo la evaluación.
- Nada sale del PC sin que la persona lo elija (modo API) y sin aviso visible.
- El servidor solo escucha en 127.0.0.1 y valida Host, Origin y Content-Type. No relajar eso.
- Todo en español. Los `.bat` sin acentos.
- Código tomado de otro proyecto: anótalo en `TERCEROS.md` con su licencia. Solo licencias permisivas (MIT,
  BSD, ISC, Apache-2.0): Tesela es PolyForm Noncommercial y no puede incluir código GPL ni sin licencia.
