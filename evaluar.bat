@echo off
rem Evaluacion completa del RAG con los modelos locales de Ollama.
rem Doble clic. Requiere uv y Ollama abiertos. La primera vez tarda unas 3 horas con una GPU de 8 GB, y
rem el computador no se suspende mientras corre. Si se corta, basta con volver a abrirlo: lo ya calculado
rem queda en las caches de .indice y no se repite. El avance queda en .indice\progreso.log.
cd /d "%~dp0"
where uv >nul 2>nul || (echo Falta uv: https://docs.astral.sh/uv/ & pause & exit /b 1)
where ollama >nul 2>nul || (echo Falta Ollama: https://ollama.com & pause & exit /b 1)
echo Revisando los modelos (si falta nomic-embed-text, se descargan unos 270 MB)...
ollama show nomic-embed-text >nul 2>nul || ollama pull nomic-embed-text || (pause & exit /b 1)
ollama show gpt-oss:20b >nul 2>nul || ollama pull gpt-oss:20b || (pause & exit /b 1)
uv sync || (pause & exit /b 1)
uv run rag evaluar --solo-busqueda
uv run rag evaluar || (pause & exit /b 1)
echo.
echo Listo. Resultados en resultados\evaluacion.md
pause
