"""Caché en disco de las llamadas al modelo de chat.

Con temperatura 0, la misma consulta da la misma respuesta: guardarla permite retomar una evaluación
larga donde quedó y volver a puntuar sin llamar de nuevo al modelo.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .indice import Embedder
from .responder import Chat


class CacheLLM:
    def __init__(self, chat: Chat, ruta: Path, etiqueta: str):
        self.chat, self.ruta, self.etiqueta = chat, Path(ruta), etiqueta
        self.datos: dict[str, str] = {}
        self.duracion: dict[str, float] = {}
        self.llamadas = 0  # llamadas reales al modelo (las que no estaban en la caché)
        self.ahorrados = 0.0  # segundos que habrían tomado las respuestas sacadas de la caché
        if self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    d = json.loads(linea)
                    self.datos[d["clave"]] = d["respuesta"]
                    self.duracion[d["clave"]] = d.get("segundos", 0.0)

    def __call__(self, sistema: str, usuario: str) -> str:
        clave = hashlib.sha256(f"{self.etiqueta}\0{sistema}\0{usuario}".encode()).hexdigest()
        if clave in self.datos:
            self.ahorrados += self.duracion.get(clave, 0.0)
            return self.datos[clave]
        t0 = time.perf_counter()
        self.datos[clave] = self.chat(sistema, usuario)
        self.duracion[clave] = round(time.perf_counter() - t0, 2)
        self.llamadas += 1
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        fila = {"clave": clave, "respuesta": self.datos[clave], "segundos": self.duracion[clave]}
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        return self.datos[clave]


class CacheEmbeddings:
    """Caché de los embeddings de las consultas: al repetir una evaluación, las mismas preguntas y
    reescrituras no se vuelven a mandar al modelo de embeddings."""

    def __init__(self, embedder: Embedder, ruta: Path, etiqueta: str):
        self.embedder, self.ruta, self.etiqueta = embedder, Path(ruta), etiqueta
        self.datos: dict[str, list[float]] = {}
        if self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    d = json.loads(linea)
                    self.datos[d["clave"]] = d["vector"]

    def __call__(self, textos: Sequence[str]) -> np.ndarray:
        claves = [hashlib.sha256(f"{self.etiqueta}\0{t}".encode()).hexdigest() for t in textos]
        faltan = [(c, t) for c, t in zip(claves, textos, strict=True) if c not in self.datos]
        if faltan:
            vectores = np.asarray(self.embedder([t for _, t in faltan]), dtype=float)
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            with self.ruta.open("a", encoding="utf-8") as f:
                for (c, _), v in zip(faltan, vectores, strict=True):
                    self.datos[c] = [round(float(x), 6) for x in v]
                    f.write(json.dumps({"clave": c, "vector": self.datos[c]}) + "\n")
        return np.array([self.datos[c] for c in claves], dtype=float)
