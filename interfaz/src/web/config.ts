// La versión web (VITE_WEB=1): la misma interfaz, con el motor de Python corriendo en el navegador (Pyodide).
export const ES_WEB = import.meta.env.VITE_WEB === '1'

/** De dónde se baja Pyodide: su CDN, o una copia local (VITE_PYODIDE) para probar sin internet. */
export const URL_PYODIDE = import.meta.env.VITE_PYODIDE || 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/'

/** Dónde se explica cómo instalar la app completa (con Ollama, carpetas y páginas web). */
export const URL_INSTALAR = 'https://github.com/vewachholtz-ops/rag-documentos-local#instalar'
