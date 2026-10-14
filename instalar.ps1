# Tesela: instala o actualiza la app en este computador (Windows 10 u 11).
#
# Uso, en PowerShell:
#   irm https://raw.githubusercontent.com/vewachholtz-ops/rag-documentos-local/main/instalar.ps1 | iex
#
# Que hace, en orden:
#   1. Baja la ultima version de GitHub y la deja en %LOCALAPPDATA%\Tesela. Si ya estaba, la actualiza y
#      conserva tus documentos, cuadernos y notas (la carpeta biblioteca).
#   2. Instala uv si falta (prepara Python y lo que necesita la app; https://docs.astral.sh/uv/).
#   3. Pregunta si instalar Ollama, que responde con IA en tu computador. Sin Ollama la app igual funciona:
#      busca pasajes sin IA o usa una API que elijas.
#   4. Crea el acceso directo "Tesela" en el escritorio y en el menu Inicio, y abre la app.
# Los modelos (gpt-oss 20B pesa unos 13 GB) no se bajan aqui: la app ofrece descargarlos la primera vez.
#
# Sin tildes a proposito: PowerShell 5.1 lee mal los archivos UTF-8 sin BOM.
# Variables opcionales: TESELA_CARPETA (otra carpeta de instalacion), TESELA_RAMA (otra rama de GitHub),
# TESELA_SIN_ABRIR=1 (no abrir la app al terminar).

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # con la barra de avance, Invoke-WebRequest es mucho mas lento
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Repo = 'vewachholtz-ops/rag-documentos-local'
$Rama = if ($env:TESELA_RAMA) { $env:TESELA_RAMA } else { 'main' }
$Destino = if ($env:TESELA_CARPETA) { $env:TESELA_CARPETA } else { Join-Path $env:LOCALAPPDATA 'Tesela' }

function Paso([string]$Texto) { Write-Host ''; Write-Host "> $Texto" -ForegroundColor Cyan }

function Preguntar([string]$Texto) {
    # Enter solo cuenta como si
    $respuesta = Read-Host "$Texto [S/n]"
    return ($respuesta -eq '' -or $respuesta -match '^(s|si|y|yes)$')
}

function Hay([string]$Comando) { return [bool](Get-Command $Comando -ErrorAction SilentlyContinue) }

function Instalar-Tesela {
    $actualizar = Test-Path (Join-Path $Destino 'pyproject.toml')
    $temporal = Join-Path ([IO.Path]::GetTempPath()) ('tesela-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temporal | Out-Null
    try {
        Paso ($(if ($actualizar) { 'Bajando la ultima version de Tesela' } else { 'Bajando Tesela' }))
        $zip = Join-Path $temporal 'tesela.zip'
        Invoke-WebRequest "https://github.com/$Repo/archive/refs/heads/$Rama.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $temporal
        $origen = Get-ChildItem -Path $temporal -Directory | Select-Object -First 1
        if (-not $origen -or -not (Test-Path (Join-Path $origen.FullName 'abrir-app.bat'))) {
            throw 'La descarga no trae la app. Vuelve a intentarlo en un rato.'
        }

        Paso "Copiando a $Destino"
        New-Item -ItemType Directory -Force -Path $Destino | Out-Null
        # /MIR deja la carpeta igual a la version nueva; lo excluido (tus datos y lo que se genera) no se toca
        robocopy $origen.FullName $Destino /MIR /NFL /NDL /NJH /NJS /NP /XD biblioteca .venv .indice /XF .acceso-directo | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "No se pudo copiar la app a $Destino (robocopy $LASTEXITCODE)." }
    }
    finally {
        Remove-Item -Recurse -Force -Path $temporal -ErrorAction SilentlyContinue
    }

    if (-not (Hay 'uv')) {
        Paso 'Instalando uv, una sola vez'
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        if (-not (Hay 'uv')) { throw 'No se pudo instalar uv. Instalalo desde https://docs.astral.sh/uv/ y vuelve a correr esto.' }
    }

    Paso 'Preparando Python y la app (la primera vez tarda un par de minutos)'
    Push-Location $Destino
    try {
        uv sync --quiet
        if ($LASTEXITCODE -ne 0) { throw 'uv sync fallo: revisa tu conexion y vuelve a correr esto.' }
    }
    finally { Pop-Location }

    $ollama = (Hay 'ollama') -or (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'))
    if (-not $ollama) {
        Paso 'Ollama'
        Write-Host 'Tesela responde con IA en tu computador usando Ollama (gratis). Sin Ollama igual funciona:'
        Write-Host 'busca pasajes sin IA o usa una API. El modelo (unos 13 GB) se baja despues, desde la app.'
        if (Preguntar 'Instalar Ollama ahora?') {
            if (Hay 'winget') {
                winget install --id Ollama.Ollama --exact --silent --accept-package-agreements --accept-source-agreements
            }
            else {
                $instalador = Join-Path ([IO.Path]::GetTempPath()) 'OllamaSetup.exe'
                Invoke-WebRequest 'https://ollama.com/download/OllamaSetup.exe' -OutFile $instalador -UseBasicParsing
                Start-Process -FilePath $instalador -Wait
                Remove-Item -Force $instalador -ErrorAction SilentlyContinue
            }
        }
        else {
            Write-Host 'Sin Ollama por ahora. Se puede instalar despues desde https://ollama.com/download'
        }
    }

    Paso 'Creando el acceso directo'
    $lanzador = Join-Path $Destino 'abrir-app.bat'
    $shell = New-Object -ComObject WScript.Shell
    foreach ($lugar in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
        $acceso = $shell.CreateShortcut((Join-Path $lugar 'Tesela.lnk'))
        $acceso.TargetPath = $lanzador
        $acceso.WorkingDirectory = $Destino
        $acceso.IconLocation = Join-Path $Destino 'app\tesela.ico'
        $acceso.WindowStyle = 7
        $acceso.Description = 'Preguntale a tus documentos'
        $acceso.Save()
    }
    # abrir-app.bat ya no vuelve a ofrecer el acceso directo
    Set-Content -Path (Join-Path $Destino '.acceso-directo') -Value ''

    Write-Host ''
    Write-Host 'Tesela quedo instalada en' $Destino -ForegroundColor Green
    Write-Host 'Se abre con el acceso directo "Tesela" del escritorio o del menu Inicio.'
    Write-Host 'Para actualizarla, vuelve a pegar la misma linea: tus documentos y notas se conservan.'
    if (-not $env:TESELA_SIN_ABRIR) {
        Start-Process -FilePath $lanzador -WorkingDirectory $Destino -WindowStyle Minimized
    }
}

try {
    Instalar-Tesela
}
catch {
    Write-Host ''
    Write-Host "No se pudo terminar: $($_.Exception.Message)" -ForegroundColor Red
}
