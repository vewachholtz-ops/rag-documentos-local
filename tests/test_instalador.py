"""El instalador de una línea (instalar.ps1) y el lanzador (abrir-app.bat): lo que se puede revisar sin Windows.

En Linux, el instalador se probó con PowerShell 7 y los comandos de Windows simulados (robocopy, uv, winget y los
accesos directos); en un Windows de verdad falta probarlo (ver ESTADO.md).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
INSTALADOR = RAIZ / "instalar.ps1"
LANZADOR = RAIZ / "abrir-app.bat"


def test_el_instalador_no_tiene_tildes():
    # PowerShell 5.1 lee mal los archivos UTF-8 sin BOM: el instalador va en ASCII, como los .bat
    texto = INSTALADOR.read_bytes()
    assert all(b < 128 for b in texto), [linea for linea in texto.decode().splitlines() if not linea.isascii()]
    assert all(b < 128 for b in LANZADOR.read_bytes())


def test_el_instalador_baja_este_repositorio_y_conserva_la_biblioteca():
    texto = INSTALADOR.read_text(encoding="ascii")
    assert "vewachholtz-ops/rag-documentos-local" in texto
    robocopy = next(linea for linea in texto.splitlines() if linea.strip().startswith("robocopy"))
    assert "/MIR" in robocopy
    excluidas = re.search(r"/XD ([^/]+)", robocopy).group(1).split()
    assert {"biblioteca", ".venv", ".indice"} <= set(excluidas)
    assert ".acceso-directo" in robocopy


def test_los_iconos_de_los_accesos_directos_existen():
    for texto in (INSTALADOR.read_text(encoding="ascii"), LANZADOR.read_text(encoding="ascii")):
        for icono in re.findall(r"app\\(\w+\.ico)", texto):
            assert (RAIZ / "app" / icono).exists(), icono


@pytest.mark.skipif(not shutil.which("pwsh"), reason="sin PowerShell")
def test_el_instalador_no_tiene_errores_de_sintaxis():
    orden = (
        "$e=$null;$t=$null;"
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{INSTALADOR}',[ref]$t,[ref]$e);"
        "$e.Count"
    )
    salida = subprocess.run(["pwsh", "-NoProfile", "-Command", orden], capture_output=True, text=True, check=True)
    assert salida.stdout.strip() == "0", salida.stdout
