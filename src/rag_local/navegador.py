"""Tesela en el navegador: la versión web, que se usa sin instalar nada.

La página web (la interfaz construida con VITE_WEB=1, ver interfaz/src/web/) corre este módulo con Pyodide dentro
de un Web Worker. Cada pedido que la interfaz hace a /api llega aquí como un pedido HTTP en bytes y lo atiende el
mismo Manejador de servidor.py, con sus rutas y validaciones; la respuesta vuelve en bytes a medida que se escribe,
así los avisos de un trabajo largo («Leyendo», «Buscando») se ven al tiro.

Lo que cambia respecto de la app instalada:
- No hay hilos (Pyodide no los tiene): los trabajos largos corren en el mismo hilo.
- No hay Ollama, ni carpetas conectadas, ni páginas web por enlace: el navegador no deja leer el disco ni pedirle
  páginas a otros sitios. Se responde en modo solo buscar o, si la persona la configura, con una API compatible
  con OpenAI, y la interfaz avisa que entonces la pregunta y los pasajes salen a ese servicio.
- La biblioteca vive en el almacenamiento del navegador (IndexedDB, montado por el Worker), no en el disco.
"""

from __future__ import annotations

import io
import json
import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from . import enlaces, ollama, servidor
from .biblioteca import Biblioteca
from .proveedores import ErrorProveedor, Proveedores

PUERTO = 8000
TOKEN = "web"
SIN_OLLAMA = "La versión web no usa Ollama: para una IA en tu computador, instala Tesela."
SIN_ENLACES = "La versión web no puede traer páginas de otros sitios: copia su texto y usa «Pegar texto»."

_app: servidor.App | None = None
_emitir: Callable[[bytes], None] | None = None  # recibe la respuesta en bytes, a medida que se escribe
_avisar: Callable[[dict], None] | None = None  # escribe un aviso del trabajo en curso


class ProveedoresWeb(Proveedores):
    """Los mismos modos, menos Ollama."""

    def __init__(self, carpeta: Path):
        super().__init__(carpeta)
        if self._ajustes["modo"] == "ollama":
            self._ajustes["modo"] = "buscar"

    def cambiar(self, cambios: dict) -> dict:
        if cambios.get("modo") == "ollama":
            raise ErrorProveedor(SIN_OLLAMA)
        return super().cambiar(cambios)


def _en_el_mismo_hilo(trabajo: Callable[[Callable[[dict], None]], dict], cancelable: bool = False) -> Iterator[dict]:
    """Como servidor._en_otro_hilo, sin hilos: los avisos se escriben apenas ocurren y al final va el resultado."""

    def avisar(evento: dict) -> None:
        if _avisar is not None:
            _avisar(evento)

    try:
        yield servidor.resultado(trabajo, avisar)
    except servidor.Cancelado:
        return


def _sin_enlaces(url: str):
    raise enlaces.ErrorEnlace(SIN_ENLACES)


class _Servidor:
    """Lo único que el Manejador mira del servidor: su dirección."""

    server_address = ("127.0.0.1", PUERTO)


class _Salida(io.RawIOBase):
    def writable(self) -> bool:
        return True

    def write(self, datos) -> int:
        if _emitir is not None:
            _emitir(bytes(datos))
        return len(datos)


class ManejadorWeb(servidor.Manejador):
    """El Manejador de servidor.py sobre bytes en memoria en vez de un socket."""

    def setup(self):
        self.rfile = io.BufferedReader(io.BytesIO(self.request))
        self.wfile = _Salida()

    def finish(self):
        pass

    def _eventos(self, eventos: Iterator[dict]) -> None:
        global _avisar
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def escribir(evento: dict) -> None:
            self.wfile.write((json.dumps(evento, ensure_ascii=False) + "\n").encode())

        _avisar = escribir
        try:
            for evento in eventos:
                escribir(evento)
        finally:
            _avisar = None


def iniciar(carpeta: str | Path) -> None:
    """Abre (o crea) la biblioteca en esa carpeta. La primera vez, el modo es solo buscar: sin IA."""
    global _app
    os.environ["MESA_TOKEN"] = TOKEN
    servidor._en_otro_hilo = _en_el_mismo_hilo
    ollama.modelos_instalados = lambda timeout=1: None  # no hay Ollama al que preguntarle
    enlaces.traer = _sin_enlaces
    carpeta = Path(carpeta)
    nueva = not (carpeta / "ajustes.json").exists()
    biblioteca = Biblioteca(carpeta)
    proveedores = ProveedoresWeb(carpeta)
    if nueva:
        proveedores.cambiar({"modo": "buscar"})
    _app = servidor.App(biblioteca, proveedores)


def atender(metodo: str, ruta: str, cabeceras: dict, cuerpo: bytes | None, emitir: Callable) -> None:
    """Atiende un pedido a /api; la respuesta HTTP completa (estado, cabeceras y cuerpo) sale por emitir."""
    global _emitir
    if _app is None:
        raise RuntimeError("Falta iniciar(): la biblioteca no está abierta.")
    if sys.platform == "emscripten":  # en Pyodide, los bytes pasan a JavaScript como Uint8Array
        from pyodide.ffi import to_js

        emitir_js = emitir

        def emitir(datos: bytes) -> None:
            emitir_js(to_js(datos))

    cuerpo = bytes(cuerpo or b"")
    lineas = [f"{metodo} {ruta} HTTP/1.1", f"Host: 127.0.0.1:{PUERTO}", f"X-Mesa-Token: {TOKEN}", "Connection: close"]
    propias = {"host", "x-mesa-token", "connection", "content-length", "origin"}
    for nombre, valor in dict(cabeceras).items():
        nombre, valor = str(nombre), str(valor)
        if nombre.lower() in propias or any(c in nombre + valor for c in "\r\n"):
            continue
        lineas.append(f"{nombre}: {valor}")
    if cuerpo or metodo in ("POST", "PUT", "PATCH"):
        lineas.append(f"Content-Length: {len(cuerpo)}")
    pedido = ("\r\n".join(lineas) + "\r\n\r\n").encode("utf-8") + cuerpo
    _emitir = emitir
    try:
        ManejadorWeb(pedido, ("127.0.0.1", 0), _Servidor(), app=_app, sitio=Path("/"))
    finally:
        _emitir = None
