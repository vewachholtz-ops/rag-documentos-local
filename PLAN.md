# Plan: Tesela (cuadernos, Estudio, React y modos de IA)

Tesela se llamó Mesa hasta el 13 de octubre de 2026 (F24).

Este archivo es la memoria compartida entre Claude y Codex. Quien tome el trabajo lee esto y `ESTADO.md` antes de
tocar nada, y al terminar actualiza la tabla de tareas y `ESTADO.md`.

## Qué estamos haciendo

Fuente pasa de "una biblioteca con un chat" a **Tesela**, una app de cuadernos inspirada en NotebookLM y en
[Open Notebook](https://github.com/lfnovo/open-notebook): cuadernos con fuentes, varias conversaciones y notas,
Estudio (la guía de cada fuente y notas generadas: resumen, guía de estudio, cuestionario, tarjetas, mapa de
ideas…), fuentes desde una página web, y tres maneras de responder:

| Modo | Qué hace | Necesita |
|---|---|---|
| Solo buscar | Devuelve los pasajes que más calzan, con la frase marcada. Sin IA. | Nada |
| Ollama (local) | Lo de hoy: búsqueda híbrida, reescritura, reordenamiento, respuesta con citas comprobadas. | Ollama y los modelos |
| API compatible con OpenAI | Igual que Ollama, con un modelo en la nube (OpenAI, Groq, OpenRouter, LM Studio, etc.). | URL, clave y modelo. Avisa que el texto sale del PC |

Se juntaron las mejores partes de Mesa documental (el RAG de Codex, carpeta `mesa-documental` en el PC): el modo
sin IA, carpetas conectadas que se sincronizan, el token por sesión con CSP y los límites contra archivos bomba.

## Decisiones

- **Interfaz en React** (Vite + TypeScript + Tailwind 4 + Radix + lucide-react + TanStack Query), código en
  `interfaz/`. `npm run build` deja la página construida en `app/`, que **se sube al repositorio**: quien usa la
  app no necesita Node, solo `abrir-app.bat`. Node 20.19+ solo para desarrollar la interfaz.
- **El servidor sigue siendo Python sin dependencias web** (`src/rag_local/servidor.py`, stdlib). Toda la lógica
  vive en Python; la interfaz solo llama a la API.
- **Diseño:** identidad propia de Tesela (ver `docs/tesela-diseno.md`): azul tinta y papel frío, el chat al centro
  entre fuentes y notas, Instrument Sans empaquetada (OFL, sin internet). Colores con nombre por función:
  `acento` (acciones), `cita` (asistente y citas), `nota`, `aviso`, `peligro` (solo lo que borra).
- **Datos:** todo en `biblioteca/` (ignorada por git). Los documentos son de la biblioteca y los cuadernos los
  enlazan: un documento puede estar en varios cuadernos, y sacarlo de uno no lo borra.
- **Prompts de la evaluación intactos:** `Busqueda.textos="procedimientos"` y la caché de `resultados/` no se
  tocan; la app usa `textos="general"`.
- **Idioma:** código, interfaz, commits y documentos en español, sin acentos en `.bat` (cmd los rompe).
- **Licencia:** PolyForm Noncommercial 1.0.0 (uso no comercial). Solo se incorpora código de terceros con licencias
  permisivas (MIT, BSD, ISC, Apache-2.0), anotado en `TERCEROS.md`.
- **Estudio con modelos chicos:** un documento largo se lee por partes de 12.000 caracteres (Ollama trabaja con
  8.192 fichas) y se escribe con las notas de lectura, que se guardan por parte en `biblioteca/anexos/`. Nada de
  cambiar `num_ctx` entre llamadas: Ollama recargaría el modelo.

## Estructura

```
interfaz/                React (fuente). npm ci && npm run build → app/
  src/api.ts             cliente tipado de la API
  src/paginas/           Cuadernos, Cuaderno, Biblioteca (Fuentes) y Ajustes (Modelos)
  src/componentes/       columnas, tarjetas, diálogos, chat
app/                     la página construida (se sube; no editar a mano)
src/rag_local/
  biblioteca.py          documentos (PDF, Word, PowerPoint, Excel, CSV, HTML, texto): leer, trocear, indexar
  enlaces.py             agregar una página web desde su enlace (sin red local)
  cuadernos.py           cuadernos, notas, conversaciones y estilo del chat (JSON con escritura atómica)
  estudio.py             guía de cada fuente y notas generadas; leer por partes (map-reduce)
  proveedores.py         modos: buscar | ollama | openai → funciones chat/embedder
  asistente.py           responder en la biblioteca (y solo buscar)
  servidor.py            API local y archivos de app/
tests/                   pytest sin Ollama (tests/ollama_falso.py); navegador con Playwright
```

## API (contrato entre interfaz y servidor)

Respuestas JSON; las largas (agregar, preguntar, descargar) en líneas JSON con avance y un evento final.

```
GET    /api/estado                                  modo, proveedor listo o no, modelos que faltan
GET    /api/ajustes                                 {modo, ollama:{modelo}, openai:{url, modelo, hay_clave}}
PUT    /api/ajustes                                 cambia el modo o el modelo (la clave nunca vuelve)
GET    /api/documentos                              la biblioteca, con los cuadernos de cada documento
POST   /api/documentos                              archivo (octet-stream, X-Nombre) → avance → documento
GET    /api/documentos/<id>                         documento, su texto en HTML y su guía (o null)
POST   /api/documentos/<id>/guia                    {} → pasos → guía {resumen, temas, preguntas, modelo, leido}
POST   /api/enlaces                                 {url, cuaderno?} → pasos → documento (con su url)
GET    /api/documentos/<id>/original                el archivo tal cual
DELETE /api/documentos/<id>                         lo borra de la biblioteca y de todos los cuadernos
GET    /api/cuadernos                               lista con cuántas fuentes y notas tiene cada uno
POST   /api/cuadernos                               {nombre, descripcion}
GET    /api/cuadernos/<id>                          cuaderno, documentos, notas (con su HTML), resumen de cada
                                                    conversación, estilo y preguntas sugeridas
PATCH  /api/cuadernos/<id>                          {nombre?, descripcion?, fuera?: [ids], estilo?: {largo, instrucciones}}
DELETE /api/cuadernos/<id>                          borra el cuaderno; los documentos quedan en la biblioteca
POST   /api/cuadernos/<id>/documentos               archivo nuevo → se agrega a la biblioteca y al cuaderno
PUT    /api/cuadernos/<id>/documentos/<doc>         enlaza un documento que ya está en la biblioteca
DELETE /api/cuadernos/<id>/documentos/<doc>         lo saca del cuaderno (no lo borra)
POST   /api/cuadernos/<id>/notas                    {titulo, contenido, origen: "propia" | "respuesta"}
PATCH  /api/cuadernos/<id>/notas/<nota>             {titulo?, contenido?}
DELETE /api/cuadernos/<id>/notas/<nota>
POST   /api/cuadernos/<id>/preguntar                {pregunta, conversacion?} → pasos → vuelta y id de la conversación
                                                    (sin conversacion, empieza una nueva)
POST   /api/cuadernos/<id>/generar                  {tipo, instruccion?} → pasos → nota generada (cancelable: cerrar la
                                                    conexión la detiene en el paso siguiente)
GET    /api/cuadernos/<id>/conversaciones/<c>       la conversación con sus vueltas
PATCH  /api/cuadernos/<id>/conversaciones/<c>       {titulo}
DELETE /api/cuadernos/<id>/conversaciones/<c>
POST   /api/modelos/descargar                       {modelo} → avance de Ollama
GET    /api/carpetas                                carpetas conectadas, con el nombre de su cuaderno
POST   /api/carpetas                                {ruta, cuaderno} → conecta (no lee todavía)
POST   /api/carpetas/<id>/sincronizar               pasos → informe: agregados, actualizados, quitados, errores
DELETE /api/carpetas/<id>                           deja de seguirla; los documentos se quedan

Todas las rutas de /api piden la cabecera X-Mesa-Token con el token de la sesión (va en la página, en
<meta name="mesa-token">), menos GET /api/documentos/<id>/original, que se abre con un enlace.
```

## Tareas

Estado: `hecho`, `en curso (quién)`, `libre`. Tomar una tarea libre = escribir el nombre aquí antes de empezar.

| # | Tarea | Estado |
|---|---|---|
| F1 | Backend: cuadernos, notas y conversación guardada en el servidor; migrar la biblioteca de hoy a un cuaderno "Mis documentos" | hecho (Claude) |
| F2 | Interfaz React: esqueleto, barra lateral, lista de cuadernos, cuaderno con columnas Fuentes, Notas y Chat, visor de fuentes, editor de notas, ajustes, biblioteca | hecho (Claude) |
| F3 | Modo "Solo buscar": pasajes ordenados con BM25 (y vectores si hay embeddings), sin IA; agregar documentos sin Ollama | hecho (Claude) |
| F4 | Modo API compatible con OpenAI: `/chat/completions`; clave en `biblioteca/ajustes-secretos.json`, nunca en la respuesta de la API; aviso visible de que el texto sale del PC. Falta: embeddings por API (hoy se usan los de Ollama si está, o solo palabras) | hecho, salvo embeddings (Claude) |
| F5 | Carpetas conectadas (de Mesa documental): conectar una carpeta a un cuaderno, sincronizar agregados, cambios y borrados con poda cuidadosa | hecho (Claude) |
| F6 | Guía por documento: resumen, temas y preguntas (a pedido, guardada; las preguntas se sugieren en el chat) | hecho (Claude) |
| F7 | Endurecimiento (de Mesa documental): token por sesión, CSP, topes contra PDF y DOCX bomba, borrar un documento mientras se responde | hecho (Claude) |
| F8 | Visor de PDF por páginas, conservando líneas, con salto a la página citada | libre |
| F9 | Pruebas de navegador de la interfaz nueva, capturas, README y docs | hecho (Claude) |
| F10 | Probar con Ollama de verdad en el PC (gpt-oss:20b) y anotar tiempos y fallas en ESTADO.md | libre (Vicente o Codex) |
| F11 | "Convertir nota en fuente" (así una nota entra al chat y a Estudio, como en NotebookLM) | hecho (Claude) |
| F12 | Revisión de Codex de Tesela (backend, interfaz, seguridad, carpetas), con hallazgos en `revisiones/` | hecho (Codex; correcciones autorizadas por Vicente) |
| F13 | Varias conversaciones por cuaderno (como las sesiones de Open Notebook) | hecho (Claude) |
| F14 | Identidad propia (cuando se llamaba Mesa): marca, navegación, paleta y composición | hecho (Codex; detalles y créditos, Claude) |
| F15 | Estudio: resumen, guía de estudio, preguntas frecuentes, cronología, cuestionario, tarjetas, mapa de ideas e instrucción propia, como notas; mapa, tarjetas y cuestionario interactivos; leer por partes; avisar cifras sin respaldo; cancelar | hecho (Claude) |
| F16 | Fuentes desde un enlace web (texto sin menús; PDF/Word enlazados; sin red local ni por redirección) | hecho (Claude) |
| F17 | PowerPoint (con notas del orador), Excel, CSV y HTML como fuentes | hecho (Claude) |
| F18 | Configurar el chat por cuaderno: largo de las respuestas e indicaciones propias | hecho (Claude) |
| F19 | Licencia PolyForm Noncommercial | hecho (Claude) |
| F20 | Probar Estudio con gpt-oss de verdad: tiempos de un PDF largo, si sigue los formatos (cuestionario, tarjetas, mapa) y ajustar las instrucciones de `estudio.py` | libre |
| F21 | Resumen en audio (pódcast) con un modelo de voz local, si hay uno que corra bien en Windows | libre |
| F22 | Leer una fuente desde su guía dentro de Tesela y distinguir la descarga del original | hecho (Codex) |
| F23 | Corregir cifras Excel, conexiones de enlaces, cancelación final, procedencia e historial; propuestas de identidad | hecho (Codex; incluye puerto exclusivo en Windows) |
| F24 | Nombre nuevo: Tesela, con marca abstracta (mosaico) y textos, ícono, instalador, sitio y documentación al día | hecho (Claude) |
| F25 | Instalador de una línea para Windows (`instalar.ps1`): deja Tesela lista (uv, dependencias, Ollama si se quiere) con su acceso directo, y actualiza sin tocar la biblioteca | hecho (Claude); falta probarlo en Windows |
| F26 | Versión web sin instalar (`site/app/`, Pyodide): solo buscar por defecto; API opcional con aviso de que el texto sale del PC | hecho (Claude); búsqueda publicada comprobada por Codex, API real pendiente |
| F27 | Revisar y publicar el portafolio en GitHub; comprobar Tesela web desde su enlace público | hecho (Codex, autorizado por Vicente) |

## Cómo se trabaja entre los dos

- Una rama por tarea: `claude/f2-interfaz`, `codex/f5-carpetas`. Se junta con `main` cuando pasan las pruebas.
  Si el trabajo es chico y nadie más está tocando lo mismo, directo en `main` con commits pequeños.
- Antes de empezar: `git pull`, leer `ESTADO.md`, marcar la tarea en la tabla.
- Al terminar o al quedarse sin tokens: commit de lo que haya (aunque esté a medias, en la rama), y en
  `ESTADO.md` qué quedó hecho, qué falta, qué se probó y el siguiente paso concreto.
- Revisión cruzada: lo que construye uno lo audita el otro en modo lectura (ver
  `ecosistema/knowledge/flujo-claude-codex.md`), con hallazgos en `revisiones/`.
- Pruebas antes de cada commit: `uv run ruff check . && uv run ruff format --check . && uv run pytest`, y si se
  tocó la interfaz, `cd interfaz && npm run build` (el `app/` construido va en el mismo commit).
