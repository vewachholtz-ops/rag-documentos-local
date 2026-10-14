"""Agregar una página web como fuente, a partir de su enlace (como en NotebookLM y Open Notebook).

Tesela descarga la página una vez, se queda con el texto (títulos, párrafos, listas y tablas, sin menús ni
scripts) y lo guarda como Markdown en la biblioteca. Un enlace a un PDF, a un Word o a un texto se agrega como ese
archivo. Es lo único que Tesela trae de internet, y solo cuando la persona pega el enlace.

Cuidados: solo http y https; nada de direcciones de la red local ni del propio computador (que una página no
pueda hacer que Tesela le pida algo al router o a otro servicio local), ni en el enlace ni en las redirecciones;
tope de 10 MB y de 30 segundos.
"""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

MAXIMO = 10 * 1024 * 1024
SEGUNDOS = 30
AGENTE = "Mozilla/5.0 (compatible; Tesela/3.0; +https://github.com/vewachholtz-ops/rag-documentos-local)"
PERMITIR_LOCALES = False  # solo para las pruebas, que sirven las páginas desde 127.0.0.1
TIPOS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/markdown": ".md",
    "text/plain": ".txt",
}


class ErrorEnlace(Exception):
    """El enlace no se puede agregar; el mensaje es para mostrarlo tal cual."""


# ---------------- de HTML a Markdown ----------------
_SALTAR = {"script", "style", "noscript", "template", "svg", "nav", "footer", "aside", "iframe", "button", "select"}
_BLOQUES = {"p", "div", "section", "article", "main", "header", "figure", "figcaption", "blockquote", "pre", "dl"}
_VACIOS = {"br", "img", "hr", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}


class _Lector(HTMLParser):
    """Recorre el HTML y arma líneas de Markdown. Guarda aparte lo que está dentro de <article> o <main>: si
    tiene texto suficiente, esa es la página (sin menús, avisos ni pie)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titulo = ""
        self._en_titulo = False
        self._saltar = 0
        self._principal = 0
        self.lineas: list[str] = []
        self.principal: list[str] = []
        self._actual: list[str] = []
        self._prefijo = ""
        self._listas: list[str] = []
        self._fila: list[str] | None = None
        self._celda: list[str] | None = None
        self._filas = 0

    # ---- texto ----
    def _cerrar(self) -> None:
        texto = " ".join("".join(self._actual).split())
        self._actual = []
        if texto:  # sin texto, la viñeta o el título que venía esperan al texto siguiente
            self._linea(f"{self._prefijo}{texto}")
            self._prefijo = ""

    def _linea(self, linea: str) -> None:
        self.lineas.append(linea)
        if self._principal:
            self.principal.append(linea)

    def handle_starttag(self, tag, attrs):
        if tag in _SALTAR:
            self._saltar += 1
            return
        if self._saltar:
            return
        if tag == "title":
            self._en_titulo = True
        elif tag in ("article", "main"):
            self._cerrar()
            self._principal += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self._cerrar()
            self._prefijo = "#" * int(tag[1]) + " "
        elif tag in ("ul", "ol"):
            self._cerrar()
            self._listas.append(tag)
        elif tag == "li":
            self._cerrar()
            marca = "1." if self._listas and self._listas[-1] == "ol" else "-"
            self._prefijo = "  " * max(0, len(self._listas) - 1) + marca + " "
        elif tag == "tr":
            self._cerrar()
            self._fila = []
        elif tag in ("td", "th") and self._fila is not None:
            self._celda = []
        elif tag == "br":
            self._actual.append(" ")
        elif tag in _BLOQUES or tag in ("dt", "dd", "table"):
            self._cerrar()

    def handle_endtag(self, tag):
        if self._saltar:
            if tag in _SALTAR:
                self._saltar -= 1
            return
        if tag == "title":
            self._en_titulo = False
        elif tag in ("article", "main"):
            self._cerrar()
            self._principal = max(0, self._principal - 1)
        elif tag in ("ul", "ol"):
            self._cerrar()
            if self._listas:
                self._listas.pop()
        elif tag in ("td", "th") and self._fila is not None and self._celda is not None:
            self._fila.append(" ".join("".join(self._celda).split()).replace("|", "/"))
            self._celda = None
        elif tag == "tr" and self._fila is not None:
            if any(self._fila):
                self._linea("| " + " | ".join(self._fila) + " |")
                if self._filas == 0:
                    self._linea("|" + "---|" * len(self._fila))
                self._filas += 1
            self._fila = None
        elif tag == "table":
            self._filas = 0
            self._linea("")
        elif re.fullmatch(r"h[1-6]", tag) or tag in _BLOQUES or tag in ("li", "dt", "dd", "p"):
            self._cerrar()

    def handle_data(self, data):
        if self._saltar:
            return
        if self._en_titulo:
            self.titulo += data
        elif self._celda is not None:
            self._celda.append(data)
        else:
            self._actual.append(data)


def html_a_markdown(html_: str) -> tuple[str, str]:
    """(título, texto en Markdown) de una página."""
    lector = _Lector()
    try:
        lector.feed(html_)
        lector.close()
    except AssertionError:  # HTML muy roto: se usa lo que alcanzó a leer
        pass
    lector._cerrar()
    lineas = lector.principal if len(" ".join(lector.principal)) >= 400 else lector.lineas
    # cada bloque separado por una línea en blanco, salvo los ítems de una lista y las filas de una tabla
    salida: list[str] = []

    def clase(linea: str) -> str:
        return "tabla" if linea.startswith("|") else "lista" if re.match(r"^\s*(?:-|\d+\.)\s", linea) else ""

    for linea in lineas:
        junto = salida and clase(linea) and clase(linea) == clase(salida[-1])
        if salida and not junto and salida[-1] != "":
            salida.append("")
        salida.append(linea)
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(salida)).strip()
    titulo = " ".join(lector.titulo.split())
    if not titulo:
        primero = next((x for x in lineas if x.startswith("# ")), "")
        titulo = primero[2:].strip()
    return titulo, texto


# ---------------- descargar ----------------
def _direcciones_publicas(nombre: str, puerto: int | None) -> list:
    try:
        direcciones = socket.getaddrinfo(nombre, puerto, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise ErrorEnlace(f"No encontré el sitio {nombre}. Revisa el enlace o tu conexión a internet.") from None
    if not direcciones:
        raise ErrorEnlace(f"No encontré el sitio {nombre}.")
    for _, _, _, _, direccion in direcciones:
        ip = ipaddress.ip_address(direccion[0].split("%")[0])
        if not ip.is_global and not PERMITIR_LOCALES:
            raise ErrorEnlace("Ese enlace apunta a una dirección de la red local. Tesela solo trae páginas públicas.")
    return direcciones


def _ip_publica(nombre: str) -> None:
    _direcciones_publicas(nombre, None)


def _conectar_publico(destino, timeout=SEGUNDOS, source_address=None):
    """Conecta a la misma IP que se comprobó, sin una segunda resolución DNS entre validación y conexión."""
    error = None
    for familia, tipo, protocolo, _, direccion in _direcciones_publicas(*destino):
        conexion = socket.socket(familia, tipo, protocolo)
        try:
            conexion.settimeout(timeout)
            if source_address:
                conexion.bind(source_address)
            conexion.connect(direccion)
            return conexion
        except OSError as exc:
            error = exc
            conexion.close()
    raise error or OSError("No pude conectar al sitio.")


def _conexion_publica(clase, host, **opciones):
    conexion = clase(host, **opciones)
    # HTTPConnection usa esta fábrica también en HTTPS; conserva Host, SNI y la validación del certificado.
    conexion._create_connection = _conectar_publico
    return conexion


class _HTTPPublico(urllib.request.HTTPHandler):
    def http_open(self, pedido):
        return self.do_open(lambda host, **kw: _conexion_publica(http.client.HTTPConnection, host, **kw), pedido)


# Un Python sin ssl no tiene HTTPS: pasa en la versión web (Pyodide), que igual no trae páginas (ver navegador.py).
_PUBLICOS: list[type] = [_HTTPPublico]
if hasattr(urllib.request, "HTTPSHandler"):

    class _HTTPSPublico(urllib.request.HTTPSHandler):
        def https_open(self, pedido):
            return self.do_open(
                lambda host, **kw: _conexion_publica(http.client.HTTPSConnection, host, **kw),
                pedido,
                context=self._context,
            )

    _PUBLICOS.append(_HTTPSPublico)


def validar(url: str) -> str:
    url = (url or "").strip()
    if not re.match(r"(?i)^https?://", url):
        url = f"https://{url}" if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", url, flags=re.I) else url
    partes = urllib.parse.urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ErrorEnlace("Pega un enlace que empiece con http:// o https://.")
    if partes.username or partes.password:
        raise ErrorEnlace("El enlace no puede traer usuario ni contraseña.")
    _ip_publica(partes.hostname)
    return url


class _Redirecciones(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validar(newurl)  # una redirección tampoco puede llevar a la red local
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _nombre(texto: str, extension: str) -> str:
    limpio = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", " ".join(texto.split()))[:90].strip(" .")
    return f"{limpio or 'Página web'}{extension}"


def traer(url: str) -> tuple[str, bytes, str]:
    """Descarga el enlace. Devuelve (nombre de archivo, contenido, enlace final): una página queda como Markdown
    con su título y el enlace; un PDF, un Word o un texto, tal cual."""
    url = validar(url)
    # Un proxy del entorno podría resolver el destino sin nuestra comprobación de IP.
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}), *_PUBLICOS, _Redirecciones)
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "text/html,application/pdf,*/*"})
    try:
        with abridor.open(pedido, timeout=SEGUNDOS) as r:
            final = r.geturl()
            tipo = (r.headers.get_content_type() or "").lower()
            juego = r.headers.get_content_charset()
            datos = r.read(MAXIMO + 1)
    except ErrorEnlace:
        raise
    except urllib.error.HTTPError as e:
        raise ErrorEnlace(f"El sitio respondió {e.code}: no pude traer la página.") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        motivo = getattr(e, "reason", e)
        raise ErrorEnlace(f"No pude abrir el enlace ({motivo}).") from None
    if len(datos) > MAXIMO:
        raise ErrorEnlace("La página pesa más de 10 MB.")
    ruta = urllib.parse.urlsplit(final).path
    archivo = urllib.parse.unquote(ruta.rsplit("/", 1)[-1]) or urllib.parse.urlsplit(final).hostname or "pagina"
    if tipo in TIPOS or re.search(r"\.(pdf|docx|md|txt)$", ruta, flags=re.I):
        extension = TIPOS.get(tipo) or "." + ruta.rsplit(".", 1)[-1].lower()
        base = archivo.rsplit(".", 1)[0] if "." in archivo else archivo
        return _nombre(base, extension), datos, final
    if tipo not in ("text/html", "application/xhtml+xml", ""):
        raise ErrorEnlace("Ese enlace no es una página web ni un PDF, Word o texto.")
    try:
        texto_html = datos.decode(juego or _juego_de(datos), errors="replace")
    except LookupError:  # el sitio declara una codificación que no existe
        texto_html = datos.decode("utf-8", errors="replace")
    titulo, cuerpo = html_a_markdown(texto_html)
    if len(cuerpo) < 80:
        raise ErrorEnlace(
            "La página casi no tiene texto: puede que se arme con JavaScript o pida iniciar sesión. "
            "Copia el texto y agrégalo con «Pegar texto»."
        )
    titulo = titulo or urllib.parse.urlsplit(final).hostname or "Página web"
    markdown = f"# {titulo}\n\nPágina web: {final}\n\n{cuerpo}\n"
    return _nombre(titulo, ".md"), markdown.encode("utf-8"), final


def _juego_de(datos: bytes) -> str:
    m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", datos[:4096], flags=re.I)
    juego = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    try:
        "".encode(juego)
        return juego
    except LookupError:
        return "utf-8"
