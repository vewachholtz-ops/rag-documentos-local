# Publicar la página de la evaluación en GitHub Pages

La página está preparada localmente. La URL pública solo existe después de crear/subir el repositorio y completar el despliegue de Pages.

## Generar y comprobar

```bash
uv sync --locked
uv run python scripts/construir_sitio.py
uv run python scripts/construir_sitio.py --check
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -m http.server 8001 --directory site
```

La última línea la muestra en http://127.0.0.1:8001 antes de publicar. Abrir `site/index.html` como archivo no funciona: la página carga `datos.json` y el navegador no lo permite desde el disco. (`rag servir` abre Fuente, la app, no esta página.)

`web/` y `scripts/construir_sitio.py` son fuentes; `site/` es salida generada y versionada para publicar. Editar las fuentes y volver a generar. `--check` falla cuando la salida está desactualizada. Los saltos de línea quedan fijados en LF con `.gitattributes` para obtener el mismo resultado en Windows y Linux.

## Publicación

1. Subir el repo a GitHub con sus cambios confirmados. El plan gratuito de Pages requiere un repo público.
2. En el repo: **Settings → Pages → Build and deployment → Source → GitHub Actions**.
3. En **Actions → Publicar la app → Run workflow**, ejecutar sobre `main`. Los cambios posteriores en las fuentes o en `site/` también activan el flujo.
4. Esperar que pasen las pruebas y el despliegue. Copiar la URL que entrega el entorno `github-pages`; comprobarla en una ventana privada y en el celular antes de usarla en el CV o LinkedIn: entrada, un ejemplo, una cita, la versión inicial, la pregunta que no está y el error conocido.
5. Revisar la vista previa del enlace en el [Post Inspector de LinkedIn](https://www.linkedin.com/post-inspector/) (título, descripción e imagen salen de las etiquetas Open Graph de `web/plantilla.html`).

El flujo verifica Ruff, pytest y la vigencia de `site/` antes de publicar. Publica solo `site/`: no expone entornos, datos crudos ni archivos de trabajo.

URL esperada: **https://vewachholtz-ops.github.io/rag-documentos-local/**

## Referencias

- [Qué es GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [Configurar el origen de publicación](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

## Enlaces y evidencia

`?p=p47&v=v1` abre la app con esa pregunta y esa versión, y la dirección se actualiza con cada respuesta. Una pregunta desconocida abre la pantalla de inicio; una versión desconocida, la mejorada (v2).

`datos.json` trae ambas respuestas para las 74 preguntas, armadas con `rag_local.web` igual que en el servidor local, y los procedimientos. Una fuente ausente hace fallar la generación: no se desplazan los números de las citas. La página separa el acierto en la evaluación de la comprobación de citas y conserva las respuestas incorrectas. Publicada, no contacta Ollama ni ningún modelo: `api/estado` es un archivo que dice que no hay modelo.
