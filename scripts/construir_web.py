"""Completa la versión web de Tesela (site/app/) con el motor en Python que corre en el navegador.

La interfaz se construye antes con `cd interfaz && VITE_WEB=1 npm run build` (deja site/app/). Esto agrega site/app/py/:
- el paquete rag_local en un zip (con su huella en el nombre, para que el navegador no use uno viejo),
- la rueda de pypdf de la versión fijada en uv.lock, comprobada con su sha256,
- manifiesto.json, que el Worker lee para saber qué cargar.
Pyodide, numpy y pyodide-http vienen del CDN de Pyodide (ver interfaz/src/web/config.ts).

Uso: uv run python scripts/construir_web.py [--ruedas carpeta]   (con --ruedas, busca ahí la rueda antes de bajarla)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import tomllib
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "site" / "app"
RUEDAS = ("pypdf",)


def motor() -> bytes:
    """src/rag_local como zip: solo los .py, en orden y con fecha fija, para que el mismo código dé el mismo zip."""
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for ruta in sorted((RAIZ / "src" / "rag_local").glob("*.py")):
            info = zipfile.ZipInfo(f"rag_local/{ruta.name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, ruta.read_bytes())
    return salida.getvalue()


def rueda(nombre: str, carpeta: Path | None) -> tuple[str, bytes]:
    """La rueda universal (py3-none-any) del paquete, en la versión y con el hash de uv.lock."""
    bloqueo = tomllib.loads((RAIZ / "uv.lock").read_text(encoding="utf-8"))
    paquete = next(p for p in bloqueo["package"] if p["name"] == nombre)
    datos = next(w for w in paquete["wheels"] if w["url"].endswith("-py3-none-any.whl"))
    archivo = datos["url"].rsplit("/", 1)[1]
    esperado = datos["hash"].removeprefix("sha256:")
    local = carpeta / archivo if carpeta else None
    contenido = local.read_bytes() if local and local.exists() else urllib.request.urlopen(datos["url"]).read()
    if hashlib.sha256(contenido).hexdigest() != esperado:
        sys.exit(f"{archivo}: el sha256 no calza con uv.lock")
    return archivo, contenido


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ruedas", type=Path, help="carpeta donde buscar las ruedas antes de bajarlas")
    args = ap.parse_args()
    if not (APP / "index.html").exists():
        sys.exit("Falta la interfaz: cd interfaz && VITE_WEB=1 npm run build")
    py = APP / "py"
    shutil.rmtree(py, ignore_errors=True)
    py.mkdir()
    zip_motor = motor()
    nombre_motor = f"rag_local-{hashlib.sha256(zip_motor).hexdigest()[:10]}.zip"
    (py / nombre_motor).write_bytes(zip_motor)
    ruedas = []
    for nombre in RUEDAS:
        archivo, contenido = rueda(nombre, args.ruedas)
        (py / archivo).write_bytes(contenido)
        ruedas.append(archivo)
    (py / "manifiesto.json").write_text(json.dumps({"motor": nombre_motor, "ruedas": ruedas}, indent=1) + "\n")
    print(f"site/app/py: {nombre_motor} y {', '.join(ruedas)}")


if __name__ == "__main__":
    main()
