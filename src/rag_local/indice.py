"""Carga de documentos, troceo por secciones e índice híbrido (BM25 + embeddings).

El flujo sigue los pasos de pguso/rag-from-scratch (MIT): cargar, trocear, embeber, guardar,
buscar y reordenar. La implementación es propia y en Python.

Los documentos marcados "Estado: obsoleto" no se indexan: un procedimiento reemplazado no debe
responder preguntas (es lo que exige un control documental).
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

Embedder = Callable[[Sequence[str]], np.ndarray]


@dataclass(frozen=True)
class Trozo:
    id: str  # documento#número
    documento: str  # nombre del archivo
    titulo: str  # título del documento > título de la sección
    texto: str
    contexto: str = ""  # frase que ubica el trozo en su documento (Contextual Retrieval), si se generó
    pagina: int | None = None  # en un PDF, la página de donde viene el texto

    @property
    def seccion(self) -> str:
        return self.titulo.split(" > ", 1)[-1]

    @property
    def texto_indice(self) -> str:
        """Lo que se indexa en BM25 y en los vectores: título, contexto (si hay) y texto."""
        return "\n".join(x for x in (self.titulo, self.contexto, self.texto) if x)


# ---------------- carga y troceo ----------------
def trocear_markdown(nombre: str, md: str, max_palabras: int = 180) -> list[Trozo]:
    """Un trozo por sección "##"; una sección larga se parte por párrafos sin pasar de max_palabras.

    Cortar por secciones mantiene juntas las reglas que van juntas (una tabla con su título),
    que es lo que más importa en procedimientos.
    """
    titulo_doc = next((linea[2:].strip() for linea in md.splitlines() if linea.startswith("# ")), nombre)
    secciones: list[tuple[str, str]] = []
    actual, lineas = "Introducción", []
    for linea in md.splitlines():
        if linea.startswith("## "):
            secciones.append((actual, "\n".join(lineas)))
            actual, lineas = linea[3:].strip(), []
        elif not linea.startswith("# "):
            lineas.append(linea)
    secciones.append((actual, "\n".join(lineas)))

    trozos: list[Trozo] = []
    for seccion, cuerpo in secciones:
        parrafos = [p.strip() for p in re.split(r"\n\s*\n", cuerpo) if p.strip()]
        grupo: list[str] = []
        for p in parrafos:
            if grupo and len(" ".join([*grupo, p]).split()) > max_palabras:
                trozos.append(_trozo(nombre, titulo_doc, seccion, grupo, len(trozos)))
                grupo = []
            grupo.append(p)
        if grupo:
            trozos.append(_trozo(nombre, titulo_doc, seccion, grupo, len(trozos)))
    return trozos


def _trozo(nombre: str, titulo_doc: str, seccion: str, parrafos: list[str], n: int) -> Trozo:
    return Trozo(f"{nombre}#{n}", nombre, f"{titulo_doc} > {seccion}", "\n\n".join(parrafos))


def es_obsoleto(md: str) -> bool:
    """True si el documento tiene una línea "Estado: obsoleto" (con o sin negrita y tildes)."""
    for linea in md.splitlines():
        plano = unicodedata.normalize("NFKD", linea.lower()).replace("*", "").strip()
        if re.match(r"estado\s*:\s*obsolet", plano):
            return True
    return False


def cargar_documentos(carpeta: Path, incluir_obsoletos: bool = False) -> dict[str, str]:
    """Nombre de archivo -> Markdown, sin el README de la carpeta ni los documentos obsoletos."""
    documentos = {}
    for archivo in sorted(Path(carpeta).glob("*.md")):
        if archivo.name.lower() == "readme.md":
            continue
        md = archivo.read_text(encoding="utf-8")
        if incluir_obsoletos or not es_obsoleto(md):
            documentos[archivo.name] = md
    return documentos


def trocear_documentos(documentos: dict[str, str]) -> list[Trozo]:
    return [t for nombre, md in documentos.items() for t in trocear_markdown(nombre, md)]


def cargar_carpeta(carpeta: Path, incluir_obsoletos: bool = False) -> list[Trozo]:
    return trocear_documentos(cargar_documentos(carpeta, incluir_obsoletos))


# ---------------- BM25 ----------------
VACIAS = set(
    "a al con de del el en es la las lo los o para por que se si sin su sus un una y cual cuales cuanto "
    "cuantos cuantas como cuando donde quien quienes hay debe deben".split()
)


def tokens(texto: str) -> list[str]:
    """Minúsculas, sin tildes, sin palabras vacías; los números se conservan (5.000 -> 5000)."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", t)
    return [w for w in re.findall(r"[a-z0-9]+", t) if w not in VACIAS]


class BM25:
    """BM25 (Robertson y Zaragoza) con k1 = 1,5 y b = 0,75, y el idf de Lucene, log(1 + …), que nunca es
    negativo (el de Okapi sí lo es para palabras que están en más de la mitad de los trozos)."""

    def __init__(self, documentos: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokens(d)) for d in documentos]
        self.largos = np.array([sum(c.values()) for c in self.docs], dtype=float)
        self.promedio = float(self.largos.mean()) if len(self.docs) else 0.0
        df = Counter(w for c in self.docs for w in c)
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    def puntajes(self, consulta: str) -> np.ndarray:
        s = np.zeros(len(self.docs))
        for w in set(tokens(consulta)):
            if w not in self.idf:
                continue
            for i, c in enumerate(self.docs):
                f = c.get(w, 0)
                if f:
                    s[i] += (
                        self.idf[w]
                        * f
                        * (self.k1 + 1)
                        / (f + self.k1 * (1 - self.b + self.b * self.largos[i] / self.promedio))
                    )
        return s


# ---------------- índice ----------------
@dataclass
class Resultado:
    trozo: Trozo
    puntaje: float
    rango_bm25: int | None
    rango_vector: int | None


class Indice:
    def __init__(self, trozos: list[Trozo], vectores: np.ndarray | None = None):
        self.trozos = trozos
        self.bm25 = BM25([t.texto_indice for t in trozos])
        self.vectores = None if vectores is None else _normalizar(vectores)

    @classmethod
    def construir(cls, trozos: list[Trozo], embedder: Embedder | None) -> Indice:
        vectores = None
        if embedder is not None:
            vectores = np.asarray(embedder([t.texto_indice for t in trozos]), dtype=float)
        return cls(trozos, vectores)

    def buscar(
        self, consulta: str, k: int = 4, embedder: Embedder | None = None, modo: str = "hibrido"
    ) -> list[Resultado]:
        """modo: "bm25", "vector" o "hibrido" (fusión por rango recíproco de ambos, k = 60)."""
        orden_bm25 = list(np.argsort(-self.bm25.puntajes(consulta), kind="stable"))
        orden_vec: list[int] = []
        if modo != "bm25":
            if self.vectores is None or embedder is None:
                raise ValueError("Para buscar con vectores se necesita el índice con embeddings y un embedder.")
            q = _normalizar(np.asarray(embedder([consulta]), dtype=float))[0]
            orden_vec = list(np.argsort(-(self.vectores @ q), kind="stable"))
        rb = {int(i): r for r, i in enumerate(orden_bm25)}
        rv = {int(i): r for r, i in enumerate(orden_vec)}
        if modo == "bm25":
            puntaje = {i: 1 / (60 + r) for i, r in rb.items()}
        elif modo == "vector":
            puntaje = {i: 1 / (60 + r) for i, r in rv.items()}
        else:
            puntaje = {i: 1 / (60 + rb[i]) + 1 / (60 + rv[i]) for i in rb}
        mejores = sorted(puntaje, key=lambda i: (-puntaje[i], i))[:k]
        return [Resultado(self.trozos[i], puntaje[i], rb.get(i), rv.get(i)) for i in mejores]

    # ---- guardar y cargar ----
    def guardar(self, carpeta: Path) -> None:
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "trozos.json").write_text(
            json.dumps([asdict(t) for t in self.trozos], ensure_ascii=False, indent=1), encoding="utf-8"
        )
        if self.vectores is not None:
            np.save(carpeta / "vectores.npy", self.vectores)

    @classmethod
    def cargar(cls, carpeta: Path) -> Indice:
        trozos = [Trozo(**d) for d in json.loads((carpeta / "trozos.json").read_text(encoding="utf-8"))]
        ruta = carpeta / "vectores.npy"
        return cls(trozos, np.load(ruta) if ruta.exists() else None)


def _normalizar(v: np.ndarray) -> np.ndarray:
    v = np.atleast_2d(v)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
