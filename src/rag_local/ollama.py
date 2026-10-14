"""Cliente mínimo de la API local de Ollama (http://localhost:11434), sin dependencias.

Todo corre en el computador: ningún texto sale a internet.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence

import numpy as np

URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
MODELO_EMBEDDINGS = os.environ.get("RAG_EMBEDDINGS", "nomic-embed-text")
MODELO_CHAT = os.environ.get("RAG_MODELO", "gpt-oss:20b")
# Modelo para las tareas auxiliares (contexto de cada trozo, reescribir, reordenar, juzgar). Por defecto, el mismo.
MODELO_AUX = os.environ.get("RAG_MODELO_AUX", MODELO_CHAT)

# Algunos modelos de embeddings se entrenaron con un prefijo que dice si el texto es un documento o una
# consulta, y rinden peor sin él. nomic-embed-text lo exige (ver su ficha en Hugging Face).
PREFIJOS = {"nomic-embed-text": ("search_document: ", "search_query: ")}


class ErrorOllama(Exception):
    def __init__(self, codigo: int, detalle: str):
        super().__init__(f"Ollama respondió {codigo}: {detalle}")
        self.codigo = codigo


class SinConexion(Exception):
    """Ollama no está abierto o no responde. Es una excepción normal (no SystemExit) para que el servidor web
    pueda avisarlo en la página; el comando `rag` la convierte en un mensaje de salida."""


def _post(ruta: str, cuerpo: dict, timeout: float = 900) -> dict:
    datos = json.dumps(cuerpo).encode()
    req = urllib.request.Request(f"{URL}{ruta}", data=datos, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ErrorOllama(e.code, e.read().decode(errors="replace")[:300]) from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise SinConexion(
            f"No se pudo conectar con Ollama en {URL} ({e}). ¿Está abierto? "
            f"¿Están descargados los modelos? (ollama pull {MODELO_EMBEDDINGS})"
        ) from e


def modelos_instalados(timeout: float = 1) -> set[str] | None:
    """Los modelos que tiene Ollama, o None si no responde."""
    try:
        with urllib.request.urlopen(f"{URL}/api/tags", timeout=timeout) as r:
            return {m.get("name", "") for m in json.loads(r.read()).get("models", [])}
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return None


def faltan(instalados: set[str], necesarios: Sequence[str]) -> list[str]:
    """Los modelos necesarios que no están: «nomic-embed-text» cuenta como «nomic-embed-text:latest»."""
    nombres = instalados | {n.removesuffix(":latest") for n in instalados}
    return [m for m in dict.fromkeys(necesarios) if m not in nombres]


def embeber(textos: Sequence[str], modelo: str = MODELO_EMBEDDINGS) -> np.ndarray:
    vectores = []
    for i in range(0, len(textos), 32):
        vectores += _post("/api/embed", {"model": modelo, "input": list(textos[i : i + 32])})["embeddings"]
    return np.array(vectores, dtype=float)


def embeber_documentos(textos: Sequence[str]) -> np.ndarray:
    """Embeddings de los trozos del índice, con el prefijo de documento si el modelo lo usa."""
    return embeber([_prefijos(MODELO_EMBEDDINGS)[0] + t for t in textos], MODELO_EMBEDDINGS)


def embeber_consulta(textos: Sequence[str]) -> np.ndarray:
    """Embeddings de las preguntas, con el prefijo de consulta si el modelo lo usa."""
    return embeber([_prefijos(MODELO_EMBEDDINGS)[1] + t for t in textos], MODELO_EMBEDDINGS)


def _prefijos(modelo: str) -> tuple[str, str]:
    return PREFIJOS.get(modelo.split(":")[0], ("", ""))


def cuerpo_chat(sistema: str, usuario: str, modelo: str, razonamiento: str | None = None) -> dict:
    cuerpo = {
        "model": modelo,
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    # gpt-oss acepta un nivel de razonamiento ("low", "medium", "high"); con "low" las tareas auxiliares
    # tardan bastante menos. Otros modelos no lo reciben.
    if razonamiento and modelo.startswith("gpt-oss"):
        cuerpo["think"] = razonamiento
    return cuerpo


def chatear(sistema: str, usuario: str, modelo: str = MODELO_CHAT, razonamiento: str | None = None) -> str:
    try:
        r = _post("/api/chat", cuerpo_chat(sistema, usuario, modelo, razonamiento))
    except ErrorOllama as e:
        if e.codigo != 400 or not razonamiento:
            raise
        r = _post("/api/chat", cuerpo_chat(sistema, usuario, modelo))  # versión de Ollama sin "think"
    return r["message"]["content"]


def chatear_auxiliar(sistema: str, usuario: str) -> str:
    return chatear(sistema, usuario, MODELO_AUX, razonamiento="low")


def chatear_juez(sistema: str, usuario: str) -> str:
    return chatear(sistema, usuario, MODELO_AUX, razonamiento="medium")
