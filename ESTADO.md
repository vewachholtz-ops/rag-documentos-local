# Estado

Última actualización: 2026-10-13, Codex (publicación y verificación del portafolio).

## Publicación del portafolio (F27)

Vicente autorizó revisar y subir Tesela, Rajo, Mostrador y el README de su perfil a GitHub. La revisión de Tesela
en Windows pasó Ruff, formato y 206 pruebas (se omitió el módulo de navegador Pyodide, que requiere
`RAG_PYODIDE`). Las compilaciones instalada y web terminaron bien; `app/` coincide con su código y el sitio de
evaluación pasa su verificación. Se comprobó la versión web servida localmente con el CDN real de Pyodide:
creación de cuaderno, incorporación de texto, búsqueda de un pasaje y persistencia al recargar.

Los cuatro repositorios quedaron públicos en `github.com/vewachholtz-ops`; CI y Pages terminaron correctamente
en los tres proyectos. Se abrió el perfil sin iniciar sesión y se comprobó Tesela desde
https://vewachholtz-ops.github.io/rag-documentos-local/app/: carga del motor desde el CDN, creación del cuaderno
«Ejemplo · Tesela», incorporación de «Cómo usar Tesela.md» y búsqueda «¿Cómo usar Ollama?» con el pasaje correcto.
Ese ejemplo queda únicamente en el navegador de revisión. Rajo ejecutó su barrido de 630 turnos en la página
pública; las ocho consultas de Mostrador coincidieron con sus resultados publicados. Los tres enlaces figuran
en el README del perfil. Las futuras publicaciones usan los flujos de GitHub Actions; para retirar una corrección
defectuosa se revierte su commit y se vuelve a ejecutar Pages, conservando el historial.

## Versión web (F26)

https://vewachholtz-ops.github.io/rag-documentos-local/app/ (se publica con el flujo de Pages). La interfaz construida
con `VITE_WEB=1` carga Pyodide 0.27.7 desde su CDN en un Web Worker y corre `rag_local` tal cual:
`src/rag_local/navegador.py` atiende los pedidos a /api con el mismo Manejador de `servidor.py`, sin hilos ni red, y
`interfaz/src/web/puente.ts` desvía a él los `fetch` de la interfaz. La biblioteca queda en IndexedDB. Arranca en solo
buscar; la API compatible con OpenAI funciona desde el navegador con `pyodide-http` (si el servicio acepta CORS) y
Estudio también. Sin Ollama, carpetas ni enlaces (se ocultan en la interfaz y el servidor los rechaza).
`scripts/construir_web.py` agrega el motor y la rueda de pypdf (con el hash de `uv.lock`); `construir_sitio.py` ya no
toca `site/app/`.

Probado: `tests/test_version_web.py` (Python común) y `tests/test_app_web.py` en Chromium con una copia local de
Pyodide (agregar PDF y Markdown, buscar, recargar y seguir con la biblioteca, bajar el original, API de mentira con
CORS para chat y Estudio). Esas pruebas se saltan sin `RAG_PYODIDE`, así que el CI no las corre.
La búsqueda publicada con el CDN real quedó comprobada en F27. Falta una API de verdad desde el navegador;
cancelar un trabajo largo no detiene
Python (no hay hilos que interrumpir): la interfaz deja de esperar, pero el trabajo termina y se guarda.

## Instalador de una línea (F25)

`instalar.ps1`: se pega `irm https://raw.githubusercontent.com/vewachholtz-ops/rag-documentos-local/main/instalar.ps1 | iex`
en PowerShell. Baja la rama `main`, la deja en `%LOCALAPPDATA%\Tesela` (con `robocopy /MIR`, sin tocar
`biblioteca/`, `.venv/` ni `.indice/`), instala uv si falta, corre `uv sync`, pregunta si instalar Ollama (con
winget, o el instalador de ollama.com si no hay winget), crea el acceso directo en el escritorio y en el menú Inicio
y abre la app. Volver a pegarlo actualiza. Va en ASCII porque PowerShell 5.1 lee mal UTF-8 sin BOM
(`tests/test_instalador.py` lo revisa). **No se ha probado en un Windows de verdad**: se probó en Linux con
PowerShell 7 y los comandos de Windows simulados (instalación nueva y actualización que conserva la biblioteca).

## Nombre nuevo: Tesela (F24)

Vicente eligió **Tesela** en vez de Mesa, con una marca abstracta: un mosaico de cuatro piezas redondeadas, una
sin relleno (la fuente que se está citando). Cambian los textos de la app, del servidor, del instalador, de la
página de la evaluación y de la documentación; el ícono es `interfaz/public/tesela.svg` y `tesela.ico`.
Los identificadores internos se quedan como estaban para no romper nada (`X-Mesa-Token`, `<meta name="mesa-token">`,
las clases `mesa-*` de la interfaz), igual que el nombre del repositorio. Las revisiones de `revisiones/`
conservan el nombre de su fecha. Un acceso directo «Mesa» creado antes queda sin ícono: se borra y
`abrir-app.bat` ofrece crear el de Tesela si se elimina el archivo `.acceso-directo`.

## Correcciones de la revisión

- Desde la guía, «Leer en Tesela» muestra el documento con formato. «Descargar el original» descarga los
  archivos de texto y de oficina; los PDF y las páginas web conservan su apertura propia.
- Excel conserva la cifra escrita en el archivo, sin redondearla a diez dígitos. Los Excel importados con la
  versión anterior necesitan volver a importarse para reconstruir el texto; el archivo original nunca se alteró.
- Los enlaces conectan a la IP comprobada; una segunda respuesta DNS no permite entrar a la red local. HTTPS
  conserva su certificado y nombre de servidor. Se comprueban también las redirecciones.
- Cancelar durante la escritura final de Estudio o de una guía impide guardar el resultado. El servidor detecta
  desconexiones durante la espera y confirma el último paso antes de guardar.
- Las conversaciones ya no pierden en silencio sus primeras 200 vueltas ni los cuadernos sus primeras 50
  conversaciones. El contexto enviado al modelo sigue acotado por separado.
- Una nota de IA convertida en fuente incluye su procedencia, modelo, fuentes y advertencias en el texto.
  Eso conserva el contexto de origen; no garantiza que el contenido generado sea correcto.
- Estudio respeta el máximo de partes y pide reducir la selección si hay demasiadas fuentes largas.
- Windows reserva el puerto de Tesela de forma exclusiva y explica si ya está ocupado.
- Las propuestas Mesa, Folio y Trama eran alternativas visuales para elegir; Vicente eligió Tesela (ver arriba).

## Dónde quedó

**Tesela** tiene lo principal que comparten NotebookLM y Open Notebook, menos el audio. Todo en `main`.

- **Cuadernos** con fuentes, chat al centro y Estudio a la derecha; fuentes que se pueden dejar fuera del chat
  (F1, F2).
- **Fuentes:** PDF, Word, PowerPoint (por diapositiva, con notas del orador), Excel y CSV (tablas partidas con su
  encabezado), HTML, Markdown y texto (F17); páginas web desde su enlace (F16, `src/rag_local/enlaces.py`); y
  carpetas conectadas que se sincronizan (F5).
- **Guía de cada fuente** (F6): resumen, temas y preguntas; las preguntas se sugieren en un chat vacío.
- **Estudio** (F15, `src/rag_local/estudio.py`): ocho tipos de nota generada con las fuentes del chat; el mapa de
  ideas, las tarjetas y el cuestionario se usan en la app. Lee por partes, guarda las notas de lectura, avisa las
  cifras sin respaldo y se cancela al cerrar la página o con «Cancelar».
- **Conversaciones** (F13): varias por cuaderno; los cuadernos guardados con una sola se pasan solos al formato
  nuevo. **Configurar el chat** (F18): respuestas cortas, normales o detalladas e indicaciones propias.
- **Notas** en Markdown seguro; una nota se puede convertir en fuente (F11).
- **Tres modos de responder**: Ollama, API compatible con OpenAI y solo buscar (F3, F4).
- **Seguridad** (F7): token por sesión, CSP, topes contra archivos bomba; los enlaces no pueden apuntar a la red
  local, tampoco por redirección; un HTML subido se descarga, no se abre dentro de la app.
- **Licencia** (F19): PolyForm Noncommercial 1.0.0 en `LICENSE`, README, `pyproject.toml` y `package.json`.
- Pruebas: ver el cierre de validación en `revisiones/2026-10-13-correcciones-mesa.md`.

## Lo que no se ha probado

- **Con Ollama de verdad (F10, F20)**: una pregunta, una guía y un resumen con gpt-oss:20b; cuánto tarda leer un
  PDF largo por partes; si el modelo sigue los formatos del cuestionario, las tarjetas y el mapa (si no, se ven
  como texto, que igual sirve). Las capturas del README son con el modelo simulado.
- La API compatible con OpenAI contra un servicio real.
- Agregar páginas web reales (en las pruebas se sirven desde 127.0.0.1): algunos sitios rechazan a los programas o
  arman la página con JavaScript; en ese caso Tesela lo explica y sugiere «Pegar texto».
- Conectar carpetas de trabajo reales con distintos permisos y rutas. La compilación de la interfaz y las
  pruebas con carpetas temporales sí se comprobaron en Windows.

## Siguiente paso

1. F10/F20: abrir `abrir-app.bat`, agregar un PDF de un ramo, escribir su guía, un mapa de ideas y un
   cuestionario, y anotar aquí los tiempos y lo que salió mal.
2. Probar `instalar.ps1` en Windows (instalación nueva, actualización y sin winget).
3. Ampliar la prueba web publicada con un PDF largo y una API real (OpenAI u OpenRouter).
4. Lo libre de la tabla de PLAN.md: F8 (visor de PDF), F21 (audio), embeddings por API.

## Cómo correr

```
uv sync
uv run rag servir                    # la app en http://127.0.0.1:8000
uv run pytest                        # sin Ollama; las de navegador necesitan Chromium (uv run playwright install chromium)
python tests/ollama_falso.py 11999   # un Ollama de mentira; luego OLLAMA_HOST=http://127.0.0.1:11999 uv run rag servir
cd interfaz && npm ci && npm run build                   # reconstruir app/ después de tocar interfaz/
MESA_TOKEN=dev uv run rag servir --sin-navegador         # y en otra terminal: MESA_TOKEN=dev npm run dev
```
