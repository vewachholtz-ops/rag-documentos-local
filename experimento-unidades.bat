@echo off
rem Experimento: la validacion tambien revisa la unidad de las cifras ("10 horas" contra "10 %%").
rem Doble clic, con Ollama abierto. Usa la cache de la evaluacion, asi que toma unos minutos.
rem Sin Ollama hace solo la parte que no necesita el modelo.
cd /d "%~dp0"
where uv >nul 2>nul || (echo Falta uv: https://docs.astral.sh/uv/ & pause & exit /b 1)
uv sync || (pause & exit /b 1)
uv run rag evaluar --unidades || (pause & exit /b 1)
echo.
echo Listo. Resultado en resultados\experimento-unidades.md
pause
