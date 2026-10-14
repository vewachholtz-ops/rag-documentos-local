# Auditoría del portafolio · 2026-10-09

Autor: Codex. Solicitud: auditar y mejorar el proyecto y revisar la propuesta de publicación de Claude.

## Hallazgos

- **Corregido:** `?v=desconocida` producía una excepción de Streamlit al dejar un valor fuera de las opciones. Se normaliza a v2; prueba de regresión.
- **Limitación existente, expuesta:** encontrar una cita literal no demuestra que la respuesta sea semánticamente correcta. En p72 se confunden gerencia y superintendencia aunque el texto citado exista. Se muestran el veredicto de evaluación y el de citas por separado.
- **Protección en la exportación:** una fuente ausente detiene la generación; no se eliminan silenciosamente fuentes y no se renumeran citas.
- **Alcance histórico:** los puntajes dependen del corpus pequeño, las preguntas y el juez usados. No se retocaron respuestas ni resultados para mejorar la métrica.

## Cambios

Demo estática en `site/`: las 74 preguntas en v1 y v2 (148 ejemplos), filtros por tipo, URL compartible, respuesta, acierto/error, citas y documentos originales. Exporta también la evaluación descargable y la comparación de búsqueda.

`web/main.js` actualiza selección y URL; valores desconocidos caen en p22/v2. El ejemplo inicial sigue legible sin JavaScript. `scripts/construir_sitio.py` reutiliza separación y marcado de citas del motor; el HTML escapa respuestas y fuentes. El renderizador admite las tablas y encabezados de estos procedimientos, no Markdown arbitrario.

Se mantiene Streamlit/Ollama local. La demo no genera nuevas respuestas ni contacta modelos. Nunito local, CI de vigencia, Pages preparado y pasos en `PUBLICACION.md`.

## Verificación

Baseline: 67 pruebas. Tras corregir el enlace: 68. Final: **71 aprobadas**. Ruff y formato aprobados; generador `--check` aprobado.

Prueba de mutación: volver al valor de versión inválido hace fallar la regresión; restaurado después. Nuevas pruebas comprueban todos los ejemplos, conservación de evaluación, fuentes ausentes, escape HTML y tablas semánticas.

Navegador real: p72 en ambas versiones, cambio de controles y URL; muestra explícitamente una respuesta incorrecta que supera citas. Evidencia visual en `../ecosistema/knowledge/research/2026-10-09-portafolio/`.

## Pendientes para Claude

1. Desplegar y comprobar Pages antes de agregar enlaces al perfil/CV. Checkout sin origin; no está publicado.
2. Si se mejora el validador semántico, hacerlo como otra versión con nueva evaluación; conservar esta corrida histórica.
3. Revisar también `fuentes_guardadas` de la app local ante documentos eliminados: el exportador está protegido, pero el lector local sigue dependiendo de que las fuentes de la corrida estén presentes.
4. Ollama puede alojarse en infraestructura remota; aquí no se implementa por alcance/costo. El localhost de un servidor no corresponde al PC del visitante.

No se efectuó una nueva corrida con Ollama ni una evaluación independiente del juez. Se auditaron y conservaron las respuestas guardadas.

## Revisión de Claude · 2026-10-09

Revisé el generador, el script, los estilos y las pruebas, y la página en 1440 y 390 px. Las respuestas, los puntajes y la protección ante fuentes ausentes no cambian.

- **Encabezado:** la página abría con el nombre del autor y una etiqueta en mayúsculas, como un sitio personal. Ahora abre con el proyecto; el nombre salió del encabezado y del título de la pestaña, y el pie enlaza a los otros proyectos.
- **El hallazgo, mejor mostrado:** el aviso «esto no garantiza una respuesta correcta» salía en todas las respuestas, también en las correctas, y se volvía ruido. Ahora la validación es una línea corta y el aviso aparece solo cuando la cita pasa y la respuesta es incorrecta (p72 y los demás casos), que es donde enseña algo.
- **Diseño:** el mismo de la app: indicadores en un panel, la pregunta como burbuja, citas como números redondos, veredicto y validación como líneas con ícono. Las fuentes sin citar decían «Fuente [2] recuperada, sin citar» sin nombrarla; ahora muestran sección y documento. La versión se elige con dos botones.
- **Búsqueda:** las configuraciones pasaron de una tabla escondida a barras visibles (de 69 % a 98 % en el primer lugar es el resultado más fuerte); acierto@3, @5 y MRR quedan en un desplegable.
- **Organización:** HTML de la página en `web/plantilla.html`. El generador borra de `site/` lo que ya no produce y `--check` falla si sobra algo.
- **App local (pendiente 3):** `fuentes_guardadas` descartaba una sección ausente y corría la numeración de las citas. Ahora deja un aviso en su lugar.

- **App como chat (después):** a pedido de Vicente, la app de Streamlit pasó de un selector de preguntas a un chat como los de kotaemon o Perplexica: caja de texto abajo, conversación con burbujas, fuentes marcadas al lado, sugerencias por tema y páginas Chat, Resultados y Documentos (`paginas/`, con lo común en `interfaz.py`). En demostración responde las 74 preguntas guardadas y, si se escribe otra cosa, sugiere las más parecidas; cambiar de versión cambia la última respuesta. Los enlaces `?p=p47&v=v1` abren el chat con esa pregunta.

Pruebas: **73 aprobadas** (71 antes); con el chat, **78**. Nuevas: el aviso aparece en p72 y no en p22; la página no carga scripts ni estilos externos.

## Nueva app web · 2026-10-09

La app de Streamlit y la vitrina estática se reemplazaron por una sola app web ([`web/`](web/)): HTML, CSS y JavaScript sin dependencias. Vicente pidió una interfaz como las de NotebookLM, Perplexity y Claude; Streamlit no permitía esa disposición ni ese nivel de detalle.

- **Disposición:** tres paneles. Procedimientos a la izquierda, chat al centro y, a la derecha, la fuente citada con la frase marcada o la evaluación. En pantallas angostas los paneles laterales se abren encima.
- **Respuesta:** primero los pasos («Buscando…», «Leyendo 4 secciones») y las tarjetas de las secciones que revisó, citadas primero; las no citadas quedan tras un botón. El texto se escribe palabra por palabra (sin animación si el sistema pide movimiento reducido). Debajo, el veredicto de la evaluación, la comprobación de citas y, cuando corresponde, el aviso de p72.
- **Un solo código para los dos modos:** `rag_local/web.py` arma la respuesta (escape, citas, fuentes marcadas) para la página publicada y para el servidor local. `rag servir` sirve la misma página con una API; la página la detecta y pasa a modo en vivo. Publicada, `api/estado` es un archivo que dice que no hay modelo.
- **Preguntas escritas a mano en la página publicada:** solo se responde con lo guardado si la pregunta es casi idéntica y tiene las mismas cifras (USD 15.000 no es USD 150.000). Si no, se ofrecen las tres más parecidas.
- **Quitado:** `app.py`, `interfaz.py`, `paginas/`, la dependencia de Streamlit y la fuente Nunito. La fuente ahora es Geist (OFL), servida desde el sitio.

Pruebas: **83 aprobadas** (nuevas para `web.py`, el servidor con un motor simulado y los datos de la página). Revisado en 1440, 1100 y 390 px, y el modo en vivo con el servidor real y un motor simulado, incluida una falla del modelo. Falta probarlo con Ollama en el computador de Vicente.

## Correcciones de la auditoría de Codex · 2026-10-12

Codex auditó la app nueva (`ecosistema/knowledge/research/2026-10-10-rag-repos-conocidos-y-auditoria.md` y `2026-10-11-rag-portafolio.md`). Lo corregido, con su prueba:

- **P1, preguntas parecidas:** la página publicada respondía «repuestos clase C» con la respuesta guardada de «clase B». Ahora lo escrito solo se responde con lo guardado si tiene las mismas palabras (cada número, sigla y palabra corta igual; un error de tipeo en palabras largas); lo demás se sugiere. Prueba en navegador con clase C/B, USD/CLP, 15.000/150.000 y una negación; con la regla anterior fallan tres de los cuatro casos.
- **Origen de cada mensaje:** cada respuesta dice si es guardada y de qué versión («Guardada, versión mejorada») o «En vivo», y el tiempo dice «41 s en la evaluación». Las respuestas guardadas ya no simulan pasos de búsqueda. Se quitó el selector v1/v2 del encabezado: cada mensaje muestra la otra versión con un enlace, y mientras responde no se puede enviar otra pregunta.
- **Pasos reales en vivo:** el servidor manda «Reformulando la pregunta», «Buscando…», «Ordenando 20 pasajes…» y «Leyendo… y redactando» a medida que empiezan (la búsqueda corre en otro hilo y avisa cada etapa).
- **Lo que promete la comprobación:** la etiqueta corta es «Citas encontradas textuales en sus fuentes», con otro ícono que el veredicto; al abrirla dice exactamente qué se revisó (frases textuales, cifras de dos o más dígitos que pueden venir de la pregunta) y que no comprueba que la conclusión sea correcta.
- **Errores de Ollama:** `ollama.py` lanza `SinConexion` (ya no `SystemExit`), así que una caída a mitad llega a la página como error; `/api/estado` exige que estén los tres modelos.
- **Servidor local:** rechaza Host ajeno (DNS rebinding), Origin ajeno, cuerpos que no son `application/json` y de más de 2.000 bytes, antes de leerlos. Un puerto ocupado da un mensaje claro.
- **Lector de Markdown:** un título con sangría dejaba el ciclo sin avanzar; ahora cada vuelta consume al menos una línea. Prueba de regresión.
- **Accesibilidad:** en pantallas angostas los paneles cerrados quedan `inert`; al abrir uno, el foco va a su botón de cerrar y vuelve al que lo abrió. El texto secundario pasó a contraste de 4,5:1 o más.
- **Publicador:** `publicar-portafolio.cmd` ya no oculta los errores de Pages ni del workflow: los avisa y el mensaje final no anuncia páginas que no quedaron publicadas (revisado, no ejecutado).

**Portafolio** (de la nota del 11 de octubre): alcance visible al entrar («Es una demostración: muestra lo que respondió el modelo en una evaluación…»), tres ejemplos (coloquial, tabla, no está) y «Ver un error conocido» (p72), versiones con nombre («inicial», «mejorada»), evaluación resumida con las ocho configuraciones en un desplegable, vista previa del enlace (Open Graph) y README de unas 1.150 palabras con el detalle en `docs/evaluacion.md` y `docs/como-funciona.md`.

**Experimento posterior:** la validación puede revisar también la unidad de cada cifra (`unidades=True`, apagado en v1 y v2). Sobre las 148 respuestas guardadas marca p09 («10 horas» contra «10 %») y ninguna correcta. La parte con modelo queda para el computador de Vicente (`experimento-unidades.bat`).

Pruebas: **102**, 10 de ellas en Chromium. La evaluación guardada no cambió.

## Fuente: la app · 2026-10-12

Vicente pidió la app en sí, lista para usar, en vez de una demostración: que abra vacía, sin instrucciones, como NotebookLM o los RAG conocidos. Ahora `rag servir` (y `abrir-app.bat`) abre **Fuente**, una app nueva en `app/` sobre el mismo motor:

- **Biblioteca** (`biblioteca.py`): agrega PDF (pypdf, por página), Word (su XML, sin dependencias, con títulos y tablas), Markdown y texto (UTF-8, UTF-16, Windows-1252); trocea por sección o página, calcula los embeddings y guarda todo en `biblioteca/`. No repite archivos; quitar uno borra su copia, no el original.
- **Preguntar** (`asistente.py`): reescribe una pregunta de seguimiento con la conversación y después usa la búsqueda y la comprobación de la versión evaluada, con instrucciones generales (`SISTEMA_GENERAL`, textos «general» de la búsqueda). Los textos de la evaluación no cambiaron, así que su caché y sus resultados siguen valiendo.
- **Servidor** (`servidor.py`): documentos (agregar con avance, ver, original, quitar), preguntas con pasos reales, estado de Ollama y descarga de modelos desde la app. Mismas defensas que antes (Host, Origin, tipo, tamaño) y el original se sirve con `nosniff`.
- **Interfaz:** documentos con casilla para elegir con cuáles responde, arrastrar archivos a la ventana, chat con pasos, tarjetas de fuentes y citas, visor del pasaje marcado y del documento completo (y el PDF original), ajustes de modelo y de búsqueda a fondo, y la conversación guardada en el navegador. En el celular, paneles que se abren encima e inertes cuando están cerrados.
- **Lanzador:** `abrir-app.bat` instala uv si falta, ofrece un acceso directo con ícono y abre Fuente en una ventana propia (Edge o Chrome en modo app).

La página de GitHub Pages queda como «respuestas de la evaluación»: lo que respondió el motor, sin modelo, con un enlace para descargar Fuente.

Pruebas: **122** (incluidas 8 de Fuente en Chromium con un Ollama de mentira, `tests/ollama_falso.py`). Las capturas del README son de la app real con documentos de ejemplo; no muestran respuestas, porque aquí no hay un modelo de verdad. Falta probarla con Ollama en el computador de Vicente y grabar ahí el recorrido.
