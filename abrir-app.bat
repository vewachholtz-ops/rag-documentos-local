@echo off
rem Tesela: abre la app. Doble clic.
rem La primera vez instala uv (si falta) y lo que necesita la app; la app misma ofrece descargar los modelos.
setlocal
cd /d "%~dp0"
title Tesela
where uv >nul 2>nul
if errorlevel 1 (
  echo Instalando uv, una sola vez...
  powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>nul || (echo No se pudo instalar uv: https://docs.astral.sh/uv/ & pause & exit /b 1)
echo Preparando Tesela...
uv sync --quiet || (pause & exit /b 1)
if not exist ".acceso-directo" call :acceso
echo.
echo Tesela esta abierta en una ventana aparte. Para cerrarla, cierra esta ventana.
uv run rag servir
pause
exit /b 0

:acceso
echo.> ".acceso-directo"
choice /c SN /m "Crear un acceso directo a Tesela en el escritorio"
if errorlevel 2 exit /b 0
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Tesela.lnk'); $s.TargetPath='%~f0'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0app\tesela.ico'; $s.WindowStyle=7; $s.Description='Preguntale a tus documentos'; $s.Save()"
exit /b 0
