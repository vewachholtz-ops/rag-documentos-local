"""Piezas comunes de los tests: el embedder y los modelos de chat se reemplazan por versiones simuladas."""

import zlib
from pathlib import Path

import numpy as np
import pytest

from rag_local.indice import Indice, Resultado, cargar_carpeta, tokens

RAIZ = Path(__file__).resolve().parents[1]
SINONIMOS = {"lubricante": "aceite", "almacen": "bodega", "visto": "aprueba"}


def embedder_falso(textos):
    """Bolsa de palabras con hash (4.096 dimensiones), con unos pocos sinónimos: simula un modelo de embeddings."""
    v = np.zeros((len(textos), 4096))
    for i, t in enumerate(textos):
        for w in tokens(t):
            w = SINONIMOS.get(w, w)
            v[i, zlib.crc32(w.encode()) % 4096] += 1
    return v


def resultado(trozo):
    return Resultado(trozo, 1.0, 0, 0)


@pytest.fixture(scope="session")
def trozos():
    return cargar_carpeta(RAIZ / "documentos")


@pytest.fixture(scope="session")
def indice(trozos):
    return Indice.construir(trozos, embedder_falso)


@pytest.fixture(scope="session")
def tabla_compras(trozos):
    """La sección de niveles de aprobación de la versión vigente de PR-COM-01."""
    return next(
        t for t in trozos if t.documento == "PR-COM-01-solicitud-de-compra.md" and t.seccion == "Niveles de aprobación"
    )
