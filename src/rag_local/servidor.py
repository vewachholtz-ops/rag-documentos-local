"""La app en el computador: `uv run rag servir` (en Windows, doble clic en abrir-app.bat).

Sirve la página construida de app/ (la interfaz en React, ver interfaz/) y una API local. Las rutas están en
PLAN.md; las largas (agregar, preguntar, descargar) responden en líneas JSON con el avance y un evento final.

Solo escucha en 127.0.0.1 y solo atiende pedidos dirigidos a 127.0.0.1 o localhost en su puerto, con el
Origin de la propia app, el tipo de contenido esperado y el token de la sesión: un valor al azar que se genera al
abrir la app y va escrito en la página (como en Mesa documental). Otra página abierta en el navegador, u otro
programa que adivine el puerto, no puede usar la API.
"""

from __future__ import annotations

import hmac
import html
import json
import mimetypes
import os
import queue
import re
import secrets
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import enlaces, estudio, ollama
from .asistente import buscar_en_biblioteca, responder_en_biblioteca
from .biblioteca import TAMANO_MAXIMO, Biblioteca, ErrorDocumento
from .carpetas import Carpetas
from .cuadernos import Cuadernos, NoExiste
from .proveedores import ErrorProveedor, Proveedores
from .responder import sistema_general
from .web import markdown_html, markdown_nota

LARGO_JSON = 40_000  # bytes de un pedido JSON común: una pregunta, un nombre, unos ajustes
LARGO_NOTA = 250_000  # una nota puede ser larga (hasta 50.000 caracteres, con tildes)
SUGERENCIAS = 4  # preguntas sugeridas en un chat vacío, sacadas de las guías de las fuentes
ID = r"([0-9a-f]{12})"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)


class App:
    """La biblioteca, los cuadernos y los modelos. Una pregunta a la vez: el modelo local no responde dos a la par."""

    def __init__(self, biblioteca: Biblioteca, proveedores: Proveedores | None = None):
        self.biblioteca = biblioteca
        primera_vez = not (biblioteca.carpeta / "cuadernos").exists()
        self.cuadernos = Cuadernos(biblioteca.carpeta)
        self.carpetas = Carpetas(biblioteca.carpeta)
        self.proveedores = proveedores or Proveedores(biblioteca.carpeta)
        self._turno = threading.Lock()
        # MESA_TOKEN fija el token (para `npm run dev`); si no, uno nuevo cada vez que se abre la app
        self.token = os.environ.get("MESA_TOKEN") or secrets.token_urlsafe(32)
        documentos = [d["id"] for d in biblioteca.documentos()]
        if primera_vez and documentos:  # la biblioteca de Fuente 2, antes de que hubiera cuadernos
            self.cuadernos.crear("Mis documentos", "Los documentos que agregaste antes de los cuadernos.", documentos)

    # ---- consulta ----
    def estado(self) -> dict:
        return self.proveedores.estado() | {
            "documentos": len(self.biblioteca.documentos()),
            "cuadernos": len(self.cuadernos.lista()),
        }

    def documentos(self) -> list[dict]:
        en = self.cuadernos.cuadernos_de()
        return [publico(d) | {"cuadernos": en.get(d["id"], [])} for d in self.biblioteca.documentos()]

    def cuaderno(self, cid: str) -> dict:
        """El cuaderno para la interfaz: sus documentos, sus notas (con su HTML), el resumen de cada conversación
        (las vueltas se piden aparte) y preguntas sugeridas por las guías de las fuentes que entran al chat."""
        c = self.cuadernos.obtener(cid)
        existentes = {d["id"]: d for d in self.biblioteca.documentos()}
        en_chat = [existentes[d] for d in c["documentos"] if d in existentes and d not in c["fuera"]]
        c["documentos"] = [publico(existentes[d]) for d in c["documentos"] if d in existentes]
        c["conversaciones"] = self.cuadernos.conversaciones(cid)
        for nota in c["notas"]:
            nota["html"] = markdown_nota(nota["contenido"])
        listas = [d["guia"].get("preguntas", []) for d in en_chat if d.get("guia")]
        sugerencias: list[str] = []
        for ronda in range(max((len(x) for x in listas), default=0)):  # una de cada fuente, por turnos
            sugerencias += [x[ronda] for x in listas if ronda < len(x) and x[ronda] not in sugerencias]
        c["sugerencias"] = sugerencias[:SUGERENCIAS]
        return c

    # ---- trabajos largos ----
    def agregar(self, nombre: str, datos: bytes, cuaderno: str | None = None, url: str | None = None) -> Iterator[dict]:
        def trabajo(avisar):
            embedder, modelo = self.proveedores.embedder_documentos()
            doc = self.biblioteca.agregar(nombre, datos, embedder, modelo, avisar, url=url)
            if cuaderno:
                self.cuadernos.enlazar(cuaderno, doc["id"])
            return {"tipo": "listo", "documento": publico(doc)}

        return _en_otro_hilo(trabajo)

    def agregar_enlace(self, url: str, cuaderno: str | None = None) -> Iterator[dict]:
        def trabajo(avisar):
            avisar({"tipo": "paso", "texto": "Descargando la página"})
            nombre, datos, final = enlaces.traer(url)
            avisar({"tipo": "paso", "texto": "Leyendo"})
            embedder, modelo = self.proveedores.embedder_documentos()
            doc = self.biblioteca.agregar(nombre, datos, embedder, modelo, avisar, url=final)
            if cuaderno:
                self.cuadernos.enlazar(cuaderno, doc["id"])
            return {"tipo": "listo", "documento": publico(doc)}

        return _en_otro_hilo(trabajo)

    def preguntar(self, cid: str, pregunta: str, conversacion: str | None = None) -> Iterator[dict]:
        def trabajo(avisar):
            def paso(texto: str) -> None:
                avisar({"tipo": "paso", "texto": texto})

            ids = self._en_el_chat(cid)
            if not ids:
                raise ErrorDocumento("Agrega una fuente al cuaderno, o activa alguna, para preguntar.")
            if self.proveedores.modo == "buscar":
                datos = buscar_en_biblioteca(
                    self.biblioteca, pregunta, ids, self.proveedores.embedder_consulta(), avisar=paso
                )
                vuelta = {"pregunta": pregunta, "modo": "buscar", "pasajes": datos}
            else:
                chat, aux, modelo = self.proveedores.chats()
                estilo = self.cuadernos.obtener(cid)["estilo"]
                with self._modelo_libre(paso):
                    embedder = self.proveedores.embedder_consulta()
                    if embedder is not None and (faltan := self.biblioteca.sin_vectores(ids)):
                        documentos, _ = self.proveedores.embedder_documentos()
                        if documentos is not None:
                            self.biblioteca.completar_vectores(faltan, documentos, ollama.MODELO_EMBEDDINGS, avisar)
                    datos = responder_en_biblioteca(
                        self.biblioteca, pregunta, ids, self.cuadernos.historial(cid, conversacion), chat, aux,
                        embedder, a_fondo=self.proveedores.a_fondo, avisar=paso,
                        k=8 if estilo["largo"] == "largo" else 5,
                        sistema=sistema_general(estilo["largo"], estilo["instrucciones"]),
                    )  # fmt: skip
                vuelta = {"pregunta": pregunta, "modo": self.proveedores.modo, "modelo": modelo, "respuesta": datos}
            id_conversacion, guardada = self.cuadernos.agregar_vuelta(cid, conversacion, vuelta)
            return {"tipo": "vuelta", "vuelta": guardada, "conversacion": id_conversacion}

        return _en_otro_hilo(trabajo)

    # ---- estudio: lo que escribe el modelo a partir de las fuentes ----
    def guia(self, doc_id: str) -> Iterator[dict]:
        """Escribe (o reescribe) la guía de una fuente: resumen, temas y preguntas."""

        def trabajo(avisar):
            def paso(texto: str) -> None:
                avisar({"tipo": "paso", "texto": texto})

            doc = self.biblioteca.documento(doc_id)
            if doc is None:
                raise NoExiste(doc_id)
            chat, aux, modelo = self._modelo_para("La guía")
            with self._modelo_libre(paso):
                fuentes = self._fuentes([doc_id])
                material, leido = estudio.material(fuentes, aux, modelo, self._medidas(), paso)
                self._guardar_notas(fuentes)
                paso("Escribiendo la guía")
                guia = estudio.escribir_guia(doc["nombre"], material, chat)
            guia |= {"modelo": modelo, "leido": round(leido, 2), "creada": time.strftime("%Y-%m-%dT%H:%M:%S")}
            paso("Guardando la guía")
            self.biblioteca.guardar_guia(doc_id, guia)
            return {"tipo": "guia", "guia": guia}

        return _en_otro_hilo(trabajo, cancelable=True)

    def generar(self, cid: str, tipo: str, instruccion: str = "") -> Iterator[dict]:
        """Una nota generada con las fuentes que entran al chat: resumen, guía de estudio, cuestionario, etc."""

        def trabajo(avisar):
            def paso(texto: str) -> None:
                avisar({"tipo": "paso", "texto": texto})

            ids = self._en_el_chat(cid)
            if not ids:
                raise ErrorDocumento("Incluye al menos una fuente en el chat para escribir a partir de ella.")
            chat, aux, modelo = self._modelo_para("Estudio")
            with self._modelo_libre(paso):
                fuentes = self._fuentes(ids)
                material, leido = estudio.material(fuentes, aux, modelo, self._medidas(), paso)
                self._guardar_notas(fuentes)
                paso(f"Escribiendo {estudio.TIPOS[tipo].que}")
                titulo, contenido = estudio.escribir(tipo, material, chat, instruccion)
            extra = {
                "tipo": tipo,
                "fuentes": [{"id": f.id, "nombre": f.nombre} for f in fuentes],
                "modelo": modelo,
                "leido": round(leido, 2),
                "avisos": estudio.cifras_sin_respaldo(contenido, [f.texto for f in fuentes]),
            } | ({"instruccion": instruccion} if tipo == "propia" else {})
            paso("Guardando la nota")
            nota = self.cuadernos.crear_nota(cid, titulo, contenido, "generada", extra)
            return {"tipo": "nota", "nota": nota | {"html": markdown_nota(contenido)}}

        return _en_otro_hilo(trabajo, cancelable=True)

    def _en_el_chat(self, cid: str) -> list[str]:
        existentes = {d["id"] for d in self.biblioteca.documentos()}
        return [d for d in self.cuadernos.para_el_chat(cid) if d in existentes]

    def _modelo_para(self, que: str) -> tuple:
        """(chat, auxiliar, modelo) si hay un modelo listo; si no, un error que dice qué falta."""
        if self.proveedores.modo == "buscar":
            raise ErrorProveedor(f"{que} la escribe un modelo: elige Ollama o una API en Modelos.")
        estado = self.proveedores.estado()
        if self.proveedores.modo == "ollama" and not estado["ollama"]:
            raise ollama.SinConexion()
        if estado["faltan"]:
            raise ErrorProveedor(f"Falta descargar {' y '.join(estado['faltan'])}: hazlo en Modelos.")
        return self.proveedores.chats()

    def _medidas(self) -> estudio.Medidas:
        return estudio.NUBE if self.proveedores.modo == "openai" else estudio.LOCAL

    def _fuentes(self, ids: list[str]) -> list[estudio.Fuente]:
        fuentes = []
        for doc_id in ids:
            doc = self.biblioteca.documento(doc_id)
            try:
                texto = self.biblioteca.texto(doc_id) if doc else ""
            except OSError:
                continue  # lo borraron recién
            if doc and texto.strip():
                notas = self.biblioteca.anexo(doc_id).get("notas", {})
                fuentes.append(estudio.Fuente(doc_id, doc["nombre"], texto, dict(notas)))
        if not fuentes:
            raise ErrorDocumento("Las fuentes ya no están en la biblioteca.")
        return fuentes

    def _guardar_notas(self, fuentes: list[estudio.Fuente]) -> None:
        for f in fuentes:
            anexo = self.biblioteca.anexo(f.id)
            if anexo.get("notas") != f.notas:
                self.biblioteca.guardar_anexo(f.id, anexo | {"notas": f.notas})

    @contextmanager
    def _modelo_libre(self, paso: Callable[[str], None]):
        """Una tarea del modelo a la vez (una respuesta, una guía, un resumen): el modelo local no atiende dos a la
        par. Si hay otra en curso, se avisa y se espera."""
        if not self._turno.acquire(blocking=False):
            paso("Esperando a que el modelo termine lo anterior")
            self._turno.acquire()
        try:
            yield
        finally:
            self._turno.release()

    def carpetas_con_nombre(self) -> list[dict]:
        nombres = {c["id"]: c["nombre"] for c in self.cuadernos.lista()}
        return [c | {"cuaderno_nombre": nombres.get(c["cuaderno"] or "")} for c in self.carpetas.lista()]

    def sincronizar(self, cid: str) -> Iterator[dict]:
        def trabajo(avisar):
            embedder, modelo = self.proveedores.embedder_documentos()
            informe = self.carpetas.sincronizar(cid, self.biblioteca, self.cuadernos, embedder, modelo, avisar)
            return {"tipo": "sincronizada", "informe": informe, "carpeta": self.carpetas.obtener(cid)}

        return _en_otro_hilo(trabajo)

    def descargar(self, modelo: str) -> Iterator[dict]:
        def trabajo(avisar):
            pedido = urllib.request.Request(
                f"{ollama.URL}/api/pull",
                data=json.dumps({"model": modelo, "stream": True}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(pedido, timeout=3600) as r:
                for linea in r:
                    if not linea.strip():
                        continue
                    d = json.loads(linea)
                    if d.get("error"):
                        raise ErrorDocumento(d["error"])
                    avisar({"tipo": "progreso", "estado": d.get("status", ""), "hecho": d.get("completed", 0),
                            "total": d.get("total", 0)})  # fmt: skip
            return {"tipo": "listo"}

        return _en_otro_hilo(trabajo)

    def modelos_descargables(self) -> set[str]:
        return {self.proveedores.publico()["modelo"], ollama.MODELO_CHAT, ollama.MODELO_EMBEDDINGS}


def publico(doc: dict) -> dict:
    campos = ("id", "nombre", "tipo", "paginas", "trozos", "bytes", "agregado", "url")
    return (
        {k: doc[k] for k in campos if k in doc}
        | {"por_significado": bool(doc.get("embeddings")), "guia": bool(doc.get("guia"))}
        | ({"repetido": True} if doc.get("repetido") else {})
    )


class Cancelado(Exception):
    """Cerraron la página o tocaron «Cancelar»: el trabajo se detiene en el próximo paso."""


def resultado(trabajo: Callable[[Callable[[dict], None]], dict], avisar: Callable[[dict], None]) -> dict:
    """Corre el trabajo y devuelve su resultado o, si falla, el error explicado (un documento ilegible, Ollama
    cerrado a mitad, etc.). Cancelado sigue de largo: no hay a quién contestarle."""
    try:
        return trabajo(avisar)
    except Cancelado:
        raise
    except (ErrorDocumento, ErrorProveedor, estudio.SinMaterial, enlaces.ErrorEnlace) as error:
        return {"tipo": "error", "texto": str(error)}
    except ollama.SinConexion:
        return {"tipo": "error", "texto": "No encuentro Ollama. Ábrelo y vuelve a intentarlo."}
    except ollama.ErrorOllama as error:
        return {"tipo": "error", "texto": f"Ollama no pudo responder ({error})."}
    except NoExiste:
        return {"tipo": "error", "texto": "El cuaderno o el documento ya no existe."}
    except Exception as error:
        return {"tipo": "error", "texto": f"No pude terminar: {error}"}


def _en_otro_hilo(trabajo: Callable[[Callable[[dict], None]], dict], cancelable: bool = False) -> Iterator[dict]:
    """Corre el trabajo en otro hilo y entrega sus avisos a medida que llegan; al final, su resultado o el error
    explicado (un documento ilegible, Ollama cerrado a mitad, etc.).

    Si es cancelable y quien pidió se va (el navegador corta la conexión), el trabajo se detiene en su próximo
    aviso: no sigue ocupando el modelo varios minutos para nadie."""
    cola: queue.Queue[dict | None] = queue.Queue()
    cancelado = threading.Event()
    recibido = threading.Event()

    def avisar(evento: dict) -> None:
        if cancelable and cancelado.is_set():
            raise Cancelado()
        recibido.clear()
        cola.put(evento)
        if cancelable:
            while not recibido.wait(0.1):
                if cancelado.is_set():
                    raise Cancelado()
            if cancelado.is_set():
                raise Cancelado()

    def correr() -> None:
        try:
            cola.put(resultado(trabajo, avisar))
        except Cancelado:
            pass
        finally:
            cola.put(None)

    threading.Thread(target=correr, daemon=True).start()
    try:
        while True:
            try:
                evento = cola.get(timeout=0.25)
            except queue.Empty:
                if cancelable:
                    yield {"tipo": "latido"}
                continue
            if evento is None:
                break
            yield evento
            recibido.set()
    finally:
        cancelado.set()


class Manejador(SimpleHTTPRequestHandler):
    def __init__(self, *args, app: App, sitio: Path, **kwargs):
        self.app = app
        super().__init__(*args, directory=str(sitio), **kwargs)

    def log_message(self, *args):  # sin una línea por cada archivo servido
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        ruta = urllib.parse.urlsplit(self.path).path
        if not ruta.startswith("/api/"):
            self.send_header("Content-Security-Policy", CSP)
            # los archivos de assets/ llevan su huella en el nombre; la página, no
            cache = "max-age=31536000, immutable" if ruta.startswith("/assets/") else "no-cache"
            self.send_header("Cache-Control", cache)
        super().end_headers()

    # ---- respuestas ----
    def _json(self, datos: dict, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _eventos(self, eventos: Iterator[dict]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for evento in eventos:
                # Durante una llamada larga también detectamos el cierre, antes de autorizar el guardado.
                if select.select([self.connection], [], [], 0)[0] and not self.connection.recv(1, socket.MSG_PEEK):
                    raise ConnectionAbortedError()
                datos = (
                    b"\n"
                    if evento.get("tipo") == "latido"
                    else (json.dumps(evento, ensure_ascii=False) + "\n").encode()
                )
                self.wfile.write(datos)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            close = getattr(eventos, "close", None)
            if close:
                close()  # cerraron la página a mitad: un trabajo cancelable se detiene

    def _no_existe(self) -> None:
        self._json({"error": "no existe"}, 404)

    # ---- quién pide ----
    def _propios(self) -> set[str]:
        puerto = self.server.server_address[1]
        return {f"127.0.0.1:{puerto}", f"localhost:{puerto}"}

    def _host_valido(self) -> bool:
        """Solo pedidos dirigidos a este servidor por su nombre local: un sitio que hace apuntar su dominio a
        127.0.0.1 (DNS rebinding) llega con su propio nombre en Host y se rechaza."""
        if self.headers.get("Host", "") in self._propios():
            return True
        self._json({"error": "host no permitido"}, 403)
        return False

    def _origen_valido(self) -> bool:
        origen = self.headers.get("Origin")
        if origen is None or origen in {f"http://{h}" for h in self._propios()}:
            return True
        self._json({"error": "origen no permitido"}, 403)
        return False

    def _token_valido(self) -> bool:
        if hmac.compare_digest(self.headers.get("X-Mesa-Token", ""), self.app.token):
            return True
        self._json({"error": "falta el token de la sesión: vuelve a abrir la app"}, 403)
        return False

    def _pagina(self) -> None:
        """index.html con el token de la sesión, que la interfaz manda en cada pedido a la API."""
        pagina = (Path(self.directory) / "index.html").read_text(encoding="utf-8")
        meta = f'<meta name="mesa-token" content="{html.escape(self.app.token)}">'
        cuerpo = pagina.replace("<head>", f"<head>\n    {meta}", 1).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _cuerpo(self, tipo: str, maximo: int) -> bytes | None:
        """El cuerpo, si tiene el tipo esperado y no pasa del máximo; si no, responde el error y da None."""
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != tipo:
            self._json({"error": f"se espera {tipo}"}, 415)
            return None
        try:
            largo = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._json({"error": "falta Content-Length"}, 411)
            return None
        if not 0 < largo <= maximo:
            self._json({"error": "pedido demasiado largo"}, 413)
            return None
        return self.rfile.read(largo)

    def _pedido_json(self, maximo: int = LARGO_JSON) -> dict | None:
        datos = self._cuerpo("application/json", maximo)
        if datos is None:
            return None
        try:
            pedido = json.loads(datos)
            if isinstance(pedido, dict):
                return pedido
        except ValueError:
            pass
        self._json({"error": "JSON inválido"}, 400)
        return None

    # ---- rutas ----
    def _rutear(self, metodo: str) -> None:
        if not self._host_valido():
            return
        if metodo != "GET" and not self._origen_valido():
            return
        ruta = urllib.parse.urlsplit(self.path).path
        if metodo == "GET" and ruta in ("/", "/index.html"):
            self._pagina()
            return
        for verbo, patron, nombre in RUTAS:
            if verbo == metodo and (m := re.fullmatch(patron, ruta)):
                # el original se abre con un enlace en otra pestaña, que no puede mandar el token
                if nombre != "original" and not self._token_valido():
                    return
                try:
                    getattr(self, nombre)(*m.groups())
                except NoExiste:
                    self._no_existe()
                except ErrorProveedor as error:
                    self._json({"error": str(error)}, 400)
                return
        if ruta.startswith("/api/"):
            self._no_existe()
        elif metodo == "GET":
            super().do_GET()
        else:
            self._json({"error": "método no permitido"}, 405)

    def do_GET(self):
        self._rutear("GET")

    def do_HEAD(self):
        if self._host_valido():
            super().do_HEAD()

    def do_POST(self):
        self._rutear("POST")

    def do_PUT(self):
        self._rutear("PUT")

    def do_PATCH(self):
        self._rutear("PATCH")

    def do_DELETE(self):
        self._rutear("DELETE")

    # estado y ajustes
    def estado(self):
        self._json(self.app.estado())

    def ver_ajustes(self):
        self._json(self.app.proveedores.publico())

    def cambiar_ajustes(self):
        if (pedido := self._pedido_json()) is not None:
            self._json(self.app.proveedores.cambiar(pedido))

    def descargar_modelo(self):
        if (pedido := self._pedido_json()) is None:
            return
        if pedido.get("modelo") not in self.app.modelos_descargables():
            self._json({"error": "modelo no permitido"}, 400)
            return
        self._eventos(self.app.descargar(pedido["modelo"]))

    # biblioteca
    def documentos(self):
        self._json({"documentos": self.app.documentos()})

    def _subir(self, cuaderno: str | None = None):
        nombre = urllib.parse.unquote(self.headers.get("X-Nombre", ""))
        if not nombre:
            self._json({"error": "falta X-Nombre"}, 400)
            return
        if cuaderno:
            self.app.cuadernos.obtener(cuaderno)  # NoExiste → 404 antes de leer el archivo
        datos = self._cuerpo("application/octet-stream", TAMANO_MAXIMO)
        if datos is not None:
            self._eventos(self.app.agregar(nombre, datos, cuaderno))

    def subir_documento(self):
        self._subir()

    def documento(self, doc_id: str):
        doc = self.app.biblioteca.documento(doc_id)
        if doc is None:
            raise NoExiste(doc_id)
        texto = markdown_html(html.escape(self.app.biblioteca.texto(doc["id"]), quote=False))
        self._json({"documento": publico(doc), "html": texto, "guia": doc.get("guia")})

    def escribir_guia(self, doc_id: str):
        if self.app.biblioteca.documento(doc_id) is None:
            raise NoExiste(doc_id)
        if self._pedido_json() is not None:
            self._eventos(self.app.guia(doc_id))

    def agregar_enlace(self):
        if (pedido := self._pedido_json()) is None:
            return
        cuaderno = str(pedido.get("cuaderno") or "") or None
        if cuaderno:
            self.app.cuadernos.obtener(cuaderno)  # NoExiste → 404
        url = str(pedido.get("url", "")).strip()[:2000]
        if not url:
            self._json({"error": "falta el enlace"}, 400)
            return
        self._eventos(self.app.agregar_enlace(url, cuaderno))

    def original(self, doc_id: str):
        doc = self.app.biblioteca.documento(doc_id)
        ruta = self.app.biblioteca.original(doc_id)
        if doc is None or ruta is None or not ruta.exists():
            raise NoExiste(doc_id)
        datos = ruta.read_bytes()
        tipo = mimetypes.guess_type(doc["nombre"])[0] or "application/octet-stream"
        if doc["tipo"] in ("md", "txt"):
            tipo = "text/plain; charset=utf-8"
        disposicion = "inline" if doc["tipo"] == "pdf" else "attachment"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Content-Disposition", f"{disposicion}; filename*=UTF-8''{urllib.parse.quote(doc['nombre'])}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def borrar_documento(self, doc_id: str):
        if not self.app.biblioteca.quitar(doc_id):
            raise NoExiste(doc_id)
        self.app.cuadernos.olvidar_documento(doc_id)
        self._json({"ok": True})

    # cuadernos
    def cuadernos(self):
        self._json({"cuadernos": self.app.cuadernos.lista()})

    def crear_cuaderno(self):
        if (pedido := self._pedido_json()) is not None:
            c = self.app.cuadernos.crear(str(pedido.get("nombre", "")), str(pedido.get("descripcion", "")))
            self._json({"cuaderno": self.app.cuaderno(c["id"])}, 201)

    def cuaderno(self, cid: str):
        self._json({"cuaderno": self.app.cuaderno(cid)})

    def cambiar_cuaderno(self, cid: str):
        if (pedido := self._pedido_json()) is not None:
            self.app.cuadernos.cambiar(cid, pedido)
            self._json({"cuaderno": self.app.cuaderno(cid)})

    def borrar_cuaderno(self, cid: str):
        self.app.cuadernos.borrar(cid)
        self.app.carpetas.olvidar_cuaderno(cid)
        self._json({"ok": True})

    def subir_al_cuaderno(self, cid: str):
        self._subir(cid)

    def enlazar(self, cid: str, doc_id: str):
        if self.app.biblioteca.documento(doc_id) is None:
            raise NoExiste(doc_id)
        self.app.cuadernos.enlazar(cid, doc_id)
        self._json({"cuaderno": self.app.cuaderno(cid)})

    def desenlazar(self, cid: str, doc_id: str):
        self.app.cuadernos.desenlazar(cid, doc_id)
        self._json({"cuaderno": self.app.cuaderno(cid)})

    def crear_nota(self, cid: str):
        if (pedido := self._pedido_json(LARGO_NOTA)) is not None:
            nota = self.app.cuadernos.crear_nota(
                cid, str(pedido.get("titulo", "")), str(pedido.get("contenido", "")), str(pedido.get("origen", ""))
            )
            self._json({"nota": nota}, 201)

    def cambiar_nota(self, cid: str, nid: str):
        if (pedido := self._pedido_json(LARGO_NOTA)) is not None:
            self._json({"nota": self.app.cuadernos.cambiar_nota(cid, nid, pedido)})

    def borrar_nota(self, cid: str, nid: str):
        self.app.cuadernos.borrar_nota(cid, nid)
        self._json({"ok": True})

    def preguntar(self, cid: str):
        if (pedido := self._pedido_json()) is None:
            return
        pregunta = str(pedido.get("pregunta", "")).strip()[:1000]
        if not pregunta:
            self._json({"error": "falta la pregunta"}, 400)
            return
        self.app.cuadernos.obtener(cid)
        conversacion = pedido.get("conversacion")
        conversacion = conversacion if isinstance(conversacion, str) and re.fullmatch(ID, conversacion) else None
        self._eventos(self.app.preguntar(cid, pregunta, conversacion))

    def generar(self, cid: str):
        if (pedido := self._pedido_json()) is None:
            return
        tipo = str(pedido.get("tipo", ""))
        instruccion = str(pedido.get("instruccion", "")).strip()[:1500]
        if tipo not in estudio.TIPOS or (tipo == "propia" and not instruccion):
            self._json({"error": "tipo de nota desconocido o falta la instrucción"}, 400)
            return
        self.app.cuadernos.obtener(cid)
        self._eventos(self.app.generar(cid, tipo, instruccion))

    def conversacion(self, cid: str, conversacion: str):
        self._json({"conversacion": self.app.cuadernos.conversacion(cid, conversacion)})

    def renombrar_conversacion(self, cid: str, conversacion: str):
        if (pedido := self._pedido_json()) is not None:
            titulo = str(pedido.get("titulo", ""))
            self._json({"conversacion": self.app.cuadernos.renombrar_conversacion(cid, conversacion, titulo)})

    def borrar_conversacion(self, cid: str, conversacion: str):
        self.app.cuadernos.borrar_conversacion(cid, conversacion)
        self._json({"ok": True})

    # carpetas conectadas
    def carpetas(self):
        self._json({"carpetas": self.app.carpetas_con_nombre()})

    def conectar_carpeta(self):
        if (pedido := self._pedido_json()) is None:
            return
        cuaderno = str(pedido.get("cuaderno") or "") or None
        if cuaderno:
            self.app.cuadernos.obtener(cuaderno)  # NoExiste → 404
        try:
            carpeta = self.app.carpetas.conectar(str(pedido.get("ruta", "")), cuaderno)
        except ErrorDocumento as error:
            self._json({"error": str(error)}, 400)
            return
        self._json({"carpeta": carpeta}, 201)

    def sincronizar_carpeta(self, cid: str):
        self.app.carpetas.obtener(cid)
        self._eventos(self.app.sincronizar(cid))

    def desconectar_carpeta(self, cid: str):
        self.app.carpetas.desconectar(cid)
        self._json({"ok": True})


RUTAS = [
    ("GET", r"/api/estado", "estado"),
    ("GET", r"/api/ajustes", "ver_ajustes"),
    ("PUT", r"/api/ajustes", "cambiar_ajustes"),
    ("POST", r"/api/modelos/descargar", "descargar_modelo"),
    ("GET", r"/api/documentos", "documentos"),
    ("POST", r"/api/documentos", "subir_documento"),
    ("GET", rf"/api/documentos/{ID}", "documento"),
    ("GET", rf"/api/documentos/{ID}/original", "original"),
    ("DELETE", rf"/api/documentos/{ID}", "borrar_documento"),
    ("POST", rf"/api/documentos/{ID}/guia", "escribir_guia"),
    ("POST", r"/api/enlaces", "agregar_enlace"),
    ("GET", r"/api/cuadernos", "cuadernos"),
    ("POST", r"/api/cuadernos", "crear_cuaderno"),
    ("GET", rf"/api/cuadernos/{ID}", "cuaderno"),
    ("PATCH", rf"/api/cuadernos/{ID}", "cambiar_cuaderno"),
    ("DELETE", rf"/api/cuadernos/{ID}", "borrar_cuaderno"),
    ("POST", rf"/api/cuadernos/{ID}/documentos", "subir_al_cuaderno"),
    ("PUT", rf"/api/cuadernos/{ID}/documentos/{ID}", "enlazar"),
    ("DELETE", rf"/api/cuadernos/{ID}/documentos/{ID}", "desenlazar"),
    ("POST", rf"/api/cuadernos/{ID}/notas", "crear_nota"),
    ("PATCH", rf"/api/cuadernos/{ID}/notas/{ID}", "cambiar_nota"),
    ("DELETE", rf"/api/cuadernos/{ID}/notas/{ID}", "borrar_nota"),
    ("POST", rf"/api/cuadernos/{ID}/preguntar", "preguntar"),
    ("POST", rf"/api/cuadernos/{ID}/generar", "generar"),
    ("GET", rf"/api/cuadernos/{ID}/conversaciones/{ID}", "conversacion"),
    ("PATCH", rf"/api/cuadernos/{ID}/conversaciones/{ID}", "renombrar_conversacion"),
    ("DELETE", rf"/api/cuadernos/{ID}/conversaciones/{ID}", "borrar_conversacion"),
    ("GET", r"/api/carpetas", "carpetas"),
    ("POST", r"/api/carpetas", "conectar_carpeta"),
    ("POST", rf"/api/carpetas/{ID}/sincronizar", "sincronizar_carpeta"),
    ("DELETE", rf"/api/carpetas/{ID}", "desconectar_carpeta"),
]


class ServidorLocal(ThreadingHTTPServer):
    def server_bind(self):
        if sys.platform == "win32":
            # SO_REUSEADDR permite compartir un puerto en Windows; una segunda Tesela debe rechazarlo.
            self.allow_reuse_address = False
            self.allow_reuse_port = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def crear(sitio: Path, app: App, puerto: int = 8000) -> ThreadingHTTPServer:
    return ServidorLocal(("127.0.0.1", puerto), partial(Manejador, app=app, sitio=sitio))


def abrir_ventana(url: str) -> None:
    """La app en una ventana propia, sin pestañas ni barra de direcciones, si hay Edge o Chrome; si no, en el
    navegador de siempre."""
    candidatos = ["msedge", "chrome", "google-chrome", "chromium"]
    if sys.platform == "win32":
        candidatos = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            *candidatos,
        ]
    for candidato in candidatos:
        ejecutable = candidato if Path(candidato).exists() else shutil.which(candidato)
        if ejecutable:
            try:
                subprocess.Popen([ejecutable, f"--app={url}", "--window-size=1440,900"])
                return
            except OSError:
                continue
    webbrowser.open(url)


def servir(raiz: Path, carpeta: Path, puerto: int = 8000, abrir: bool = True) -> None:
    sitio = raiz / "app"
    if not (sitio / "index.html").exists():
        raise SystemExit("Falta la carpeta app/ con la página. Constrúyela con: cd interfaz && npm ci && npm run build")
    try:
        servidor = crear(sitio, App(Biblioteca(carpeta)), puerto)
    except OSError:
        url = f"http://127.0.0.1:{puerto}/"
        if abrir:
            abrir_ventana(url)  # ya estaba abierta: se muestra esa
        raise SystemExit(f"La app ya está abierta en {url} (o el puerto {puerto} está ocupado).") from None
    url = f"http://127.0.0.1:{puerto}/"
    print(f"La app está en {url}. Para cerrarla, cierra esta ventana o presiona Ctrl+C.")
    if abrir:
        threading.Timer(0.6, abrir_ventana, args=(url,)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
