# Tesela

Cuadernos para consultar documentos, revisar sus fuentes y guardar notas.

[**Abrir Tesela**](https://vewachholtz-ops.github.io/rag-documentos-local/app/) · [Instalar](#instalar) · [Cómo funciona](docs/como-funciona.md)

[![Pruebas](https://github.com/vewachholtz-ops/rag-documentos-local/actions/workflows/ci.yml/badge.svg)](https://github.com/vewachholtz-ops/rag-documentos-local/actions/workflows/ci.yml)

![Un cuaderno de Tesela con documentos, conversación y notas](docs/tesela-cuaderno.png)

## Enfoque del proyecto

- **Revisar la evidencia.** Las citas abren el pasaje del documento y, en PDF, su página. El motor comprueba que las frases citadas existan en la fuente; eso no garantiza que la interpretación del modelo sea correcta.
- **Elegir cómo consultar.** Búsqueda sin IA, respuestas con Ollama local o una API compatible con OpenAI. Con Ollama y en modo búsqueda, el procesamiento es local. Con una API remota se envían al proveedor la pregunta, los pasajes y el contexto reciente utilizado.
- **Trabajar con archivos propios.** PDF, Word, PowerPoint, Excel, CSV y texto. La versión instalada también permite incorporar páginas web y sincronizar carpetas sin modificar los originales.
- **Mantener fuentes y apuntes juntos.** Cada cuaderno reúne conversaciones y notas. Puedes guardar una respuesta o preparar guías, tarjetas y cuestionarios a partir de las fuentes seleccionadas.

## Instalar

**En el navegador:** [abre Tesela](https://vewachholtz-ops.github.io/rag-documentos-local/app/). Los documentos se guardan en ese navegador. Puedes buscar sin IA o configurar una API; Ollama, carpetas conectadas y páginas web por enlace requieren la versión instalada.

**En Windows 10 u 11:** abre PowerShell y pega:

```powershell
irm https://raw.githubusercontent.com/vewachholtz-ops/rag-documentos-local/main/instalar.ps1 | iex
```

El [instalador](instalar.ps1) deja Tesela en `%LOCALAPPDATA%\Tesela`, crea un acceso directo y ofrece instalar [Ollama](https://ollama.com). Para actualizar, ejecuta la misma línea; se conservan documentos, cuadernos y notas.

También puedes descargar el proyecto (**Code → Download ZIP**), descomprimirlo y abrir `abrir-app.bat`. Sin Ollama, elige **Solo buscar** o configura una API en **Modelos**.

En otros sistemas, con [uv](https://docs.astral.sh/uv/) instalado:

```bash
uv sync
uv run rag servir
```

La biblioteca local queda en `biblioteca/`. Quitar un documento de Tesela no borra el archivo original.

## Evaluación del motor

Una configuración anterior del motor se evaluó con 74 preguntas sobre 24 procedimientos de una mina ficticia: 62 con respuesta y 12 sin información suficiente.

| Medición | Configuración inicial | Configuración evaluada |
|---|---:|---:|
| Respuestas correctas, preguntas con respuesta | 54 de 62 | 60 de 62 |
| Preguntas sin respuesta rechazadas | 11 de 12 | 11 de 12 |
| Sección correcta en el primer resultado | 69 % | 98 % |
| Segundos por pregunta | 11 | 35 |

Estos resultados corresponden a ese corpus y esa configuración; **no miden la exactitud de la app actual**. Hubo respuestas incorrectas aun cuando el modelo recibió la sección correcta.

[Método, resultados y límites](docs/evaluacion.md) · [Consultar las respuestas de esa evaluación](https://vewachholtz-ops.github.io/rag-documentos-local/)

## Desarrollo y límites

```bash
uv sync
uv run rag servir
uv run pytest
cd interfaz
npm ci
npm run build
```

La interfaz está en `interfaz/`, su compilación en `app/` y el motor en `src/rag_local/`. El detalle técnico está en [Cómo funciona](docs/como-funciona.md). La versión web se construye con `VITE_WEB=1 npm run build` desde `interfaz/` y `uv run python scripts/construir_web.py` desde la raíz.

Las pruebas de la app usan proveedores simulados; falta validar los flujos actuales con Ollama y una API reales. Las capturas también usan un modelo simulado. Para las pruebas de navegador se necesita Chromium (`uv run playwright install chromium`); las pruebas de Pyodide requieren su distribución local.

Tesela no incluye cuadernos compartidos ni generación de audio. Los embeddings por API están pendientes.

## Créditos y licencia

La organización en cuadernos y el panel de estudio se inspiraron en NotebookLM y [Open Notebook](https://github.com/lfnovo/open-notebook), sin incorporar su código. Las referencias del motor están en [Cómo funciona](docs/como-funciona.md#de-dónde-salió-cada-idea); las dependencias y sus licencias, en [TERCEROS.md](TERCEROS.md).

Licencia [PolyForm Noncommercial 1.0.0](LICENSE). Para uso comercial, contacta al autor en [GitHub](https://github.com/vewachholtz-ops). Las dependencias conservan sus propias licencias.
