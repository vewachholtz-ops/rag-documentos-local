"""La biblioteca de la app: los documentos que la persona agrega, su texto, sus trozos y sus embeddings.

Todo queda en una carpeta del computador (por defecto, biblioteca/ dentro del proyecto):

    documentos.json      # la lista, con nombre, tipo, páginas y estado
    originales/<id>.pdf  # una copia del archivo, para abrirlo tal cual
    texto/<id>.md        # el texto extraído, como Markdown
    trozos/<id>.json     # los trozos, con su página si viene de un PDF
    vectores/<id>.npy    # el embedding de cada trozo
    anexos/<id>.json     # lo que se calcula después: notas de lectura y la guía de la fuente (ver estudio.py)

Agregar un documento lo lee, lo trocea y calcula los embeddings una sola vez; preguntar arma el índice híbrido
(BM25 + vectores) solo con los documentos elegidos. Quitar un documento borra su copia, nunca el original.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import re
import threading
import time
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from .indice import Embedder, Indice, Trozo, trocear_markdown

TIPOS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".html": "html",
    ".htm": "html",
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
}
NO_SE_PUEDE = "Ese tipo de archivo no se puede agregar: usa PDF, Word, PowerPoint, Excel, CSV, HTML, Markdown o texto."
TAMANO_MAXIMO = 30 * 1024 * 1024  # 30 MB por archivo
PALABRAS = 180  # por trozo, como en la evaluación
# Límites contra archivos que pesan poco pero se inflan al leerlos (bombas), como en Mesa documental
PAGINAS_MAXIMAS = 3_000
TEXTO_MAXIMO = 20_000_000  # caracteres extraídos de un archivo
TROZOS_MAXIMOS = 20_000
XML_MAXIMO = 40 * 1024 * 1024  # el XML de un Word, una presentación o una planilla, ya descomprimido
FILAS_MAXIMAS = 5_000  # por hoja de una planilla
COLUMNAS_MAXIMAS = 40
FILAS_POR_TABLA = 15  # una tabla larga se parte en tablas chicas (con su encabezado) para buscar mejor
SEGUNDOS_PDF = 180
Avisar = Callable[[dict], None]


class ErrorDocumento(Exception):
    """El archivo no se puede agregar; el mensaje es para mostrarlo tal cual."""


# ---------------- lectura de cada tipo ----------------
def _decodificar(datos: bytes) -> str:
    """Texto plano en UTF-8 (con o sin BOM), UTF-16 o, si no, Windows-1252: lo que guardan el Bloc de notas
    y Excel en Windows."""
    if datos.startswith((b"\xff\xfe", b"\xfe\xff")):
        return datos.decode("utf-16")
    try:
        return datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        return datos.decode("cp1252", errors="replace")


def leer_pdf(datos: bytes) -> list[str]:
    """El texto de cada página. Un PDF escaneado (solo imágenes) no tiene texto que leer."""
    from pypdf import PdfReader  # solo se carga si hay un PDF

    try:
        lector = PdfReader(io.BytesIO(datos))
        if lector.is_encrypted:
            raise ErrorDocumento("El PDF tiene contraseña.")
        if len(lector.pages) > PAGINAS_MAXIMAS:
            raise ErrorDocumento(f"El PDF tiene más de {PAGINAS_MAXIMAS:,} páginas.".replace(",", "."))
        inicio = time.monotonic()
        paginas: list[str] = []
        largo = 0
        for pagina in lector.pages:
            paginas.append(pagina.extract_text() or "")
            largo += len(paginas[-1])
            if largo > TEXTO_MAXIMO:
                raise ErrorDocumento("El PDF tiene demasiado texto para una sola fuente. Divídelo en partes.")
            if time.monotonic() - inicio > SEGUNDOS_PDF:
                raise ErrorDocumento("El PDF tarda demasiado en leerse. Divídelo en partes o expórtalo de nuevo.")
    except ErrorDocumento:
        raise
    except Exception as error:
        raise ErrorDocumento(f"No pude leer el PDF ({error.__class__.__name__}).") from None
    if not "".join(paginas).strip():
        raise ErrorDocumento("El PDF no tiene texto: parece escaneado. Pásalo antes por un OCR.")
    return paginas


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def leer_docx(datos: bytes) -> str:
    """El texto de un Word como Markdown: títulos, párrafos y tablas. Sin dependencias: un .docx es un zip con
    XML adentro."""
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > XML_MAXIMO:
                raise ErrorDocumento("El Word es demasiado grande por dentro.")
            with z.open(info) as f:  # se lee con tope, aunque el tamaño declarado mienta
                xml = f.read(XML_MAXIMO + 1)
            if len(xml) > XML_MAXIMO:
                raise ErrorDocumento("El Word es demasiado grande por dentro.")
    except (zipfile.BadZipFile, KeyError):
        raise ErrorDocumento("El archivo no es un Word (.docx) válido.") from None
    if b"<!DOCTYPE" in xml[:2000] or b"<!ENTITY" in xml:
        raise ErrorDocumento("El Word trae declaraciones que no se aceptan.")
    raiz = ElementTree.fromstring(xml)
    cuerpo = raiz.find(f"{_W}body")
    lineas: list[str] = []
    for nodo in list(cuerpo) if cuerpo is not None else []:
        if nodo.tag == f"{_W}p":
            texto = "".join(t.text or "" for t in nodo.iter(f"{_W}t")).strip()
            if not texto:
                continue
            estilo = nodo.find(f"{_W}pPr/{_W}pStyle")
            nombre = (estilo.get(f"{_W}val") if estilo is not None else "") or ""
            nivel = re.search(r"(?i)(?:heading|t\w*tulo)\s*(\d)", nombre)
            if re.fullmatch(r"(?i)title|t\w*tulo", nombre):
                lineas.append(f"# {texto}")
            elif nivel:
                lineas.append(f"## {texto}")
            else:
                lineas.append(texto)
            lineas.append("")
        elif nodo.tag == f"{_W}tbl":
            filas = []
            for fila in nodo.iter(f"{_W}tr"):
                celdas = [
                    " ".join("".join(t.text or "" for t in c.iter(f"{_W}t")).split()).replace("|", "/")
                    for c in fila.iter(f"{_W}tc")
                ]
                filas.append("| " + " | ".join(celdas) + " |")
            if filas:
                columnas = filas[0].count("|") - 1
                lineas += [filas[0], "|" + "---|" * columnas, *filas[1:], ""]
    texto = "\n".join(lineas).strip()
    if not texto:
        raise ErrorDocumento("El Word está vacío.")
    return texto


class _Zip:
    """Lee los XML de un archivo de Office con tope: por archivo y en total, aunque los tamaños declarados
    mientan, y sin declaraciones DOCTYPE ni ENTITY (bombas de entidades)."""

    def __init__(self, datos: bytes, que: str):
        self.que = que
        try:
            self.z = zipfile.ZipFile(io.BytesIO(datos))
        except zipfile.BadZipFile:
            raise ErrorDocumento(f"El archivo no es un {que} válido.") from None
        self.nombres = set(self.z.namelist())
        self.leido = 0

    def xml(self, nombre: str) -> ElementTree.Element:
        try:
            info = self.z.getinfo(nombre)
        except KeyError:
            raise ErrorDocumento(f"El archivo no es un {self.que} válido.") from None
        if info.file_size > XML_MAXIMO:
            raise ErrorDocumento(f"El {self.que} es demasiado grande por dentro.")
        with self.z.open(info) as f:
            xml = f.read(XML_MAXIMO + 1)
        self.leido += len(xml)
        if len(xml) > XML_MAXIMO or self.leido > 3 * XML_MAXIMO:
            raise ErrorDocumento(f"El {self.que} es demasiado grande por dentro.")
        if b"<!DOCTYPE" in xml[:2000] or b"<!ENTITY" in xml:
            raise ErrorDocumento(f"El {self.que} trae declaraciones que no se aceptan.")
        try:
            return ElementTree.fromstring(xml)
        except ElementTree.ParseError:
            raise ErrorDocumento(f"El archivo no es un {self.que} válido.") from None


_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _relaciones(z: _Zip, ruta: str) -> dict[str, str]:
    """Id → archivo de destino, ya como ruta dentro del zip (ppt/slides/slide1.xml)."""
    carpeta, _, nombre = ruta.rpartition("/")
    rels = f"{carpeta}/_rels/{nombre}.rels"
    if rels not in z.nombres:
        return {}
    salida = {}
    for r in z.xml(rels).iter(f"{_REL}Relationship"):
        destino = r.get("Target", "")
        partes = (destino.lstrip("/") if destino.startswith("/") else f"{carpeta}/{destino}").split("/")
        limpio: list[str] = []
        for p in partes:
            if p == "..":
                if limpio:
                    limpio.pop()
            elif p and p != ".":
                limpio.append(p)
        salida[r.get("Id", "")] = "/".join(limpio)
    return salida


def _parrafos(elemento: ElementTree.Element) -> list[str]:
    salida = []
    for p in elemento.iter(f"{_A}p"):
        texto = " ".join("".join(t.text or "" for t in p.iter(f"{_A}t")).split())
        if texto:
            salida.append(texto)
    return salida


def leer_pptx(datos: bytes) -> str:
    """Una sección por diapositiva, en el orden de la presentación, con su título, su texto (también el de las
    tablas) y las notas del orador."""
    z = _Zip(datos, "PowerPoint (.pptx)")
    with z.z:
        rels = _relaciones(z, "ppt/presentation.xml")
        orden = []
        if "ppt/presentation.xml" in z.nombres:
            orden = [rels.get(s.get(f"{_R}id", ""), "") for s in z.xml("ppt/presentation.xml").iter(f"{_P}sldId")]
        diapositivas = [d for d in orden if d in z.nombres] or sorted(
            (n for n in z.nombres if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.findall(r"\d+", n)[-1]),
        )
        if not diapositivas:
            raise ErrorDocumento("El PowerPoint no tiene diapositivas.")
        if len(diapositivas) > PAGINAS_MAXIMAS:
            raise ErrorDocumento(f"El PowerPoint tiene más de {PAGINAS_MAXIMAS:,} diapositivas.".replace(",", "."))
        secciones = []
        for n, ruta in enumerate(diapositivas, 1):
            raiz = z.xml(ruta)
            titulo, cuerpo = "", []
            for forma in raiz.iter(f"{_P}sp"):
                marcador = forma.find(f"{_P}nvSpPr/{_P}nvPr/{_P}ph")
                textos = _parrafos(forma)
                if marcador is not None and marcador.get("type") in ("title", "ctrTitle") and not titulo:
                    titulo = " ".join(textos)
                else:
                    cuerpo += textos
            for tabla in raiz.iter(f"{_A}tbl"):
                filas = [
                    [_celda(" ".join(_parrafos(c))) for c in fila.iter(f"{_A}tc")] for fila in tabla.iter(f"{_A}tr")
                ]
                if filas and any(any(f) for f in filas):
                    ancho = max(len(f) for f in filas)
                    lineas = ["| " + " | ".join(f + [""] * (ancho - len(f))) + " |" for f in filas]
                    cuerpo.append("\n".join([lineas[0], "|" + "---|" * ancho, *lineas[1:]]))
            notas = []
            for destino in _relaciones(z, ruta).values():
                if re.search(r"notesSlide\d+\.xml$", destino) and destino in z.nombres:
                    for forma in z.xml(destino).iter(f"{_P}sp"):
                        marcador = forma.find(f"{_P}nvSpPr/{_P}nvPr/{_P}ph")
                        if marcador is not None and marcador.get("type") == "body":
                            notas += _parrafos(forma)
            if not (titulo or cuerpo or notas):
                continue
            encabezado = f"## Diapositiva {n}" + (f": {titulo[:100]}" if titulo else "")
            bloque = [encabezado, *cuerpo]
            if notas:
                bloque.append("Notas del orador: " + " ".join(notas))
            secciones.append("\n\n".join(bloque))
    if not secciones:
        raise ErrorDocumento("El PowerPoint no tiene texto.")
    return "\n\n".join(secciones)


def _columna(referencia: str) -> int:
    """«C7» → 2."""
    n = 0
    for letra in re.match(r"[A-Z]*", referencia.upper()).group():
        n = n * 26 + ord(letra) - 64
    return n - 1


def _tablas(titulo: str, filas: list[list[str]], cortada: bool) -> str:
    """Una tabla Markdown por cada FILAS_POR_TABLA filas, todas con el encabezado: cada una queda en su trozo."""
    ancho = max(len(f) for f in filas)
    filas = [f + [""] * (ancho - len(f)) for f in filas]
    encabezado, datos = filas[0], filas[1:]
    cabeza = ["| " + " | ".join(encabezado) + " |", "|" + "---|" * ancho]
    bloques = [f"## {titulo}"]
    for i in range(0, max(1, len(datos)), FILAS_POR_TABLA):
        grupo = datos[i : i + FILAS_POR_TABLA]
        bloques.append("\n".join([*cabeza, *("| " + " | ".join(f) + " |" for f in grupo)]))
    if cortada:
        bloques.append(f"(Solo se leyeron las primeras {FILAS_MAXIMAS:,} filas.)".replace(",", "."))
    return "\n\n".join(bloques)


def _celda(texto: str) -> str:
    return " ".join(str(texto).split()).replace("|", "/")


_FORMATOS_FECHA = {*range(14, 23), 45, 46, 47}


def _estilos_fecha(z: _Zip) -> set[int]:
    """Los estilos de celda (índices de cellXfs) que muestran el número como fecha u hora."""
    if "xl/styles.xml" not in z.nombres:
        return set()
    raiz = z.xml("xl/styles.xml")
    propios = set()
    for formato in raiz.iter(f"{_S}numFmt"):
        codigo = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", formato.get("formatCode", "").lower())
        if re.search(r"[dmyhs]", codigo):
            propios.add(int(formato.get("numFmtId", "0")))
    xfs = raiz.find(f"{_S}cellXfs")
    if xfs is None:
        return set()
    return {i for i, xf in enumerate(xfs.iter(f"{_S}xf")) if int(xf.get("numFmtId", "0")) in _FORMATOS_FECHA | propios}


def _fecha(serial: float) -> str:
    momento = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=serial)
    return momento.strftime("%Y-%m-%d %H:%M" if serial % 1 else "%Y-%m-%d")


def leer_xlsx(datos: bytes) -> str:
    """Cada hoja como tablas Markdown, con los valores que guardó Excel (no las fórmulas) y las fechas como
    fechas."""
    z = _Zip(datos, "Excel (.xlsx)")
    with z.z:
        fechas = _estilos_fecha(z)
        compartidos = []
        if "xl/sharedStrings.xml" in z.nombres:
            compartidos = ["".join(t.text or "" for t in si.iter(f"{_S}t")) for si in z.xml("xl/sharedStrings.xml")]
        rels = _relaciones(z, "xl/workbook.xml")
        libro = z.xml("xl/workbook.xml")
        hojas = [(h.get("name", "Hoja"), rels.get(h.get(f"{_R}id", ""), "")) for h in libro.iter(f"{_S}sheet")]
        secciones = []
        for nombre, ruta in hojas:
            if ruta not in z.nombres:
                continue
            filas: list[list[str]] = []
            cortada = False
            for fila in z.xml(ruta).iter(f"{_S}row"):
                valores: dict[int, str] = {}
                for c in fila.iter(f"{_S}c"):
                    col = _columna(c.get("r", "")) if c.get("r") else len(valores)
                    if not 0 <= col < COLUMNAS_MAXIMAS:
                        continue
                    tipo, v = c.get("t"), c.find(f"{_S}v")
                    crudo = v.text if v is not None and v.text else ""
                    if tipo == "s":
                        valor = compartidos[int(crudo)] if crudo.isdigit() and int(crudo) < len(compartidos) else ""
                    elif tipo == "inlineStr":
                        valor = "".join(t.text or "" for t in c.iter(f"{_S}t"))
                    elif tipo == "b":
                        valor = "VERDADERO" if crudo == "1" else "FALSO"
                    elif tipo in (None, "n") and crudo:
                        try:
                            numero = float(crudo)
                            fecha = int(c.get("s", "0")) in fechas and 0 < numero < 2_958_466
                            valor = _fecha(numero) if fecha else crudo
                        except ValueError:
                            valor = crudo
                    else:
                        valor = crudo
                    valores[col] = _celda(valor)
                if any(valores.values()):
                    filas.append([valores.get(i, "") for i in range(max(valores) + 1)])
                if len(filas) > FILAS_MAXIMAS:
                    cortada = True
                    break
            if filas:
                secciones.append(_tablas(f"Hoja: {nombre}", filas[: FILAS_MAXIMAS + 1], cortada))
    if not secciones:
        raise ErrorDocumento("La planilla está vacía.")
    return "\n\n".join(secciones)


def leer_csv(datos: bytes) -> str:
    texto = _decodificar(datos)
    muestra = texto[:8192]
    try:
        separador = csv.Sniffer().sniff(muestra, delimiters=",;\t|").delimiter
    except csv.Error:
        separador = max(",;\t", key=muestra.count)
    filas: list[list[str]] = []
    cortada = False
    for fila in csv.reader(io.StringIO(texto), delimiter=separador):
        celdas = [_celda(c) for c in fila[:COLUMNAS_MAXIMAS]]
        if any(celdas):
            filas.append(celdas)
        if len(filas) > FILAS_MAXIMAS:
            cortada = True
            break
    if not filas:
        raise ErrorDocumento("El CSV está vacío.")
    return _tablas("Datos", filas[: FILAS_MAXIMAS + 1], cortada)


def leer_html(datos: bytes) -> str:
    from .enlaces import html_a_markdown

    titulo, cuerpo = html_a_markdown(_decodificar(datos))
    if not cuerpo.strip():
        raise ErrorDocumento("La página no tiene texto.")
    return f"# {titulo}\n\n{cuerpo}" if titulo and not cuerpo.startswith("# ") else cuerpo


def _como_markdown(texto: str) -> str:
    """Si un Markdown usa «#» para cada sección (en vez de un solo título y «##»), las secciones se corren un
    nivel, que es lo que espera el troceo."""
    titulos = [linea for linea in texto.splitlines() if linea.startswith("# ")]
    if len(titulos) > 1:
        texto = re.sub(r"(?m)^# ", "## ", texto)
    return texto


def trocear_pdf(doc_id: str, nombre: str, paginas: list[str]) -> list[Trozo]:
    """Trozos de cada página, sin mezclar páginas, para poder decir de cuál viene cada cita."""
    trozos: list[Trozo] = []
    for numero, texto in enumerate(paginas, 1):
        lineas = [" ".join(linea.split()) for linea in texto.splitlines()]
        grupo: list[str] = []
        for linea in [x for x in lineas if x]:
            if grupo and len(" ".join([*grupo, linea]).split()) > PALABRAS:
                trozos.append(_trozo_pdf(doc_id, nombre, numero, grupo, len(trozos)))
                grupo = []
            grupo.append(linea)
        if grupo:
            trozos.append(_trozo_pdf(doc_id, nombre, numero, grupo, len(trozos)))
    return trozos


def _trozo_pdf(doc_id: str, nombre: str, pagina: int, lineas: list[str], n: int) -> Trozo:
    return Trozo(f"{doc_id}#{n}", doc_id, f"{nombre} > Página {pagina}", "\n".join(lineas), pagina=pagina)


def trocear(doc_id: str, nombre: str, tipo: str, datos: bytes) -> tuple[str, list[Trozo], int | None]:
    """El texto (como Markdown, para mostrarlo), los trozos y, si es un PDF, el número de páginas."""
    titulo = Path(nombre).stem
    if tipo == "pdf":
        paginas = leer_pdf(datos)
        texto = "\n\n".join(f"## Página {n}\n\n{p.strip()}" for n, p in enumerate(paginas, 1) if p.strip())
        return texto, trocear_pdf(doc_id, nombre, paginas), len(paginas)
    lectores = {"docx": leer_docx, "pptx": leer_pptx, "xlsx": leer_xlsx, "csv": leer_csv, "html": leer_html}
    texto = lectores.get(tipo, _decodificar)(datos)
    if len(texto) > TEXTO_MAXIMO:
        raise ErrorDocumento("El archivo tiene demasiado texto para una sola fuente. Divídelo en partes.")
    texto = _como_markdown(texto)
    if not texto.strip():
        raise ErrorDocumento("El archivo está vacío.")
    if not any(linea.startswith("# ") for linea in texto.splitlines()):
        texto = f"# {titulo}\n\n{texto}"
    # el texto antes del primer subtítulo queda como "Inicio" (trocear_markdown lo llama "Introducción")
    trozos = [
        Trozo(f"{doc_id}#{i}", doc_id, f"{nombre} > {'Inicio' if t.seccion == 'Introducción' else t.seccion}", t.texto)
        for i, t in enumerate(trocear_markdown(doc_id, texto, PALABRAS))
    ]
    return texto, trozos, None


# ---------------- la biblioteca ----------------
class Biblioteca:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        for sub in ("originales", "texto", "trozos", "vectores", "anexos"):
            (self.carpeta / sub).mkdir(parents=True, exist_ok=True)
        self._cerrojo = threading.RLock()
        self._indices: dict[tuple, Indice] = {}
        ruta = self.carpeta / "documentos.json"
        self._docs: list[dict] = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
        # lo que quedó a medias si se cerró la app mientras agregaba un documento
        self._docs = [d for d in self._docs if d.get("estado") == "listo"]

    # ---- consulta ----
    def documentos(self) -> list[dict]:
        with self._cerrojo:
            return [dict(d) for d in self._docs]

    def documento(self, doc_id: str) -> dict | None:
        with self._cerrojo:
            return next((dict(d) for d in self._docs if d["id"] == doc_id), None)

    def texto(self, doc_id: str) -> str:
        return (self.carpeta / "texto" / f"{doc_id}.md").read_text(encoding="utf-8")

    def original(self, doc_id: str) -> Path | None:
        d = self.documento(doc_id)
        return self.carpeta / "originales" / f"{doc_id}{d['extension']}" if d else None

    def indice(self, ids: list[str] | None = None) -> Indice | None:
        """El índice con los documentos elegidos (todos, si ids es None). Se arma una vez por selección."""
        with self._cerrojo:
            elegidos = [d["id"] for d in self._docs if ids is None or d["id"] in ids]
            if not elegidos:
                return None
            clave = tuple(sorted(elegidos))
            if clave not in self._indices:
                trozos: list[Trozo] = []
                vectores = []
                for doc_id in clave:
                    datos = json.loads((self.carpeta / "trozos" / f"{doc_id}.json").read_text(encoding="utf-8"))
                    trozos += [Trozo(**t) for t in datos]
                    ruta = self.carpeta / "vectores" / f"{doc_id}.npy"
                    vectores.append(np.load(ruta) if ruta.exists() else None)
                # Si a algún documento le faltan los embeddings (se agregó sin Ollama), se busca solo por palabras.
                juntos = None if any(v is None for v in vectores) else np.vstack(vectores)
                self._indices = {clave: Indice(trozos, juntos)}  # solo la última selección
            return self._indices[clave]

    def sin_vectores(self, ids: list[str] | None = None) -> list[str]:
        """Los documentos elegidos que se agregaron sin embeddings."""
        with self._cerrojo:
            return [
                d["id"]
                for d in self._docs
                if (ids is None or d["id"] in ids) and not (self.carpeta / "vectores" / f"{d['id']}.npy").exists()
            ]

    def completar_vectores(self, ids: list[str], embedder: Embedder, modelo: str, avisar: Avisar) -> None:
        """Calcula los embeddings de documentos que se agregaron sin ellos (por ejemplo, en modo solo buscar)."""
        for n, doc_id in enumerate(ids, 1):
            ruta = self.carpeta / "trozos" / f"{doc_id}.json"
            if not ruta.exists():
                continue  # lo quitaron entretanto
            avisar({"tipo": "paso", "texto": f"Preparando {n} de {len(ids)} documentos para buscar por significado"})
            trozos = [Trozo(**t) for t in json.loads(ruta.read_text(encoding="utf-8"))]
            vectores = _embeber(trozos, embedder, lambda _evento: None)
            with self._cerrojo:
                doc = next((d for d in self._docs if d["id"] == doc_id), None)
                if doc is None:
                    continue
                np.save(self.carpeta / "vectores" / f"{doc_id}.npy", vectores)
                doc["embeddings"] = modelo
                self._guardar()

    # ---- cambios ----
    def agregar(
        self,
        nombre: str,
        datos: bytes,
        embedder: Embedder | None,
        modelo: str | None,
        avisar: Avisar,
        url: str | None = None,
    ) -> dict:
        """Lee, trocea e indexa un archivo. avisar recibe el avance: {"tipo": "paso" | "progreso", ...}. `url` es
        el enlace de donde vino, si se agregó desde una página web.

        Sin embedder (Ollama cerrado o modo solo buscar) se indexa solo para buscar por palabras; los embeddings
        se calculan después con completar_vectores()."""
        nombre = Path(nombre.replace("\\", "/")).name.strip() or "documento"
        extension = Path(nombre).suffix.lower()
        if extension not in TIPOS:
            raise ErrorDocumento(NO_SE_PUEDE)
        if len(datos) > TAMANO_MAXIMO:
            raise ErrorDocumento("El archivo pesa más de 30 MB.")
        huella = hashlib.sha256(datos).hexdigest()
        with self._cerrojo:
            igual = next((d for d in self._docs if d["sha256"] == huella), None)
        if igual:
            return {**igual, "repetido": True}
        doc_id = uuid.uuid4().hex[:12]
        avisar({"tipo": "paso", "texto": "Leyendo"})
        texto, trozos, paginas = trocear(doc_id, nombre, TIPOS[extension], datos)
        if not trozos:
            raise ErrorDocumento("No encontré texto en el archivo.")
        if len(trozos) > TROZOS_MAXIMOS:
            raise ErrorDocumento("El documento es demasiado largo para una sola fuente. Divídelo en partes.")
        vectores = _embeber(trozos, embedder, avisar) if embedder is not None else None
        doc = {
            "id": doc_id,
            "nombre": nombre,
            "extension": extension,
            "tipo": TIPOS[extension],
            "paginas": paginas,
            "trozos": len(trozos),
            "bytes": len(datos),
            "sha256": huella,
            "embeddings": modelo if embedder is not None else None,
            "agregado": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "estado": "listo",
        }
        if url:
            doc["url"] = url
        with self._cerrojo:
            (self.carpeta / "originales" / f"{doc_id}{extension}").write_bytes(datos)
            (self.carpeta / "texto" / f"{doc_id}.md").write_text(texto, encoding="utf-8")
            (self.carpeta / "trozos" / f"{doc_id}.json").write_text(
                json.dumps([asdict(t) for t in trozos], ensure_ascii=False), encoding="utf-8"
            )
            if vectores is not None:
                np.save(self.carpeta / "vectores" / f"{doc_id}.npy", vectores)
            self._docs.append(doc)
            self._guardar()
        return dict(doc)

    def quitar(self, doc_id: str) -> bool:
        with self._cerrojo:
            doc = next((d for d in self._docs if d["id"] == doc_id), None)
            if doc is None:
                return False
            self._docs.remove(doc)
            self._guardar()
            for ruta in (
                self.carpeta / "originales" / f"{doc_id}{doc['extension']}",
                self.carpeta / "texto" / f"{doc_id}.md",
                self.carpeta / "trozos" / f"{doc_id}.json",
                self.carpeta / "vectores" / f"{doc_id}.npy",
                self.carpeta / "anexos" / f"{doc_id}.json",
            ):
                ruta.unlink(missing_ok=True)
            return True

    # ---- anexos: lo que se calcula después de agregarlo ----
    def anexo(self, doc_id: str) -> dict:
        """Las notas de lectura y la guía del documento (estudio.py), o {} si todavía no hay."""
        try:
            datos = json.loads((self.carpeta / "anexos" / f"{doc_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return datos if isinstance(datos, dict) else {}

    def guardar_anexo(self, doc_id: str, datos: dict) -> None:
        with self._cerrojo:
            if not any(d["id"] == doc_id for d in self._docs):
                return  # lo borraron mientras se calculaba
            ruta = self.carpeta / "anexos" / f"{doc_id}.json"
            temporal = ruta.with_suffix(".json.tmp")
            temporal.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            temporal.replace(ruta)

    def guardar_guia(self, doc_id: str, guia: dict) -> None:
        """La guía de la fuente (resumen, temas y preguntas), que va con el documento en documentos.json."""
        with self._cerrojo:
            doc = next((d for d in self._docs if d["id"] == doc_id), None)
            if doc is not None:  # si no, lo borraron mientras se escribía
                doc["guia"] = guia
                self._escribir()

    def _guardar(self) -> None:
        self._indices.clear()
        self._escribir()

    def _escribir(self) -> None:
        temporal = self.carpeta / "documentos.json.tmp"
        temporal.write_text(json.dumps(self._docs, ensure_ascii=False, indent=1), encoding="utf-8")
        temporal.replace(self.carpeta / "documentos.json")


def _embeber(trozos: list[Trozo], embedder: Embedder, avisar: Avisar) -> np.ndarray:
    vectores = []
    for i in range(0, len(trozos), 16):
        avisar({"tipo": "progreso", "hecho": i, "total": len(trozos)})
        vectores.append(np.asarray(embedder([t.texto_indice for t in trozos[i : i + 16]]), dtype=float))
    avisar({"tipo": "progreso", "hecho": len(trozos), "total": len(trozos)})
    return np.vstack(vectores)
