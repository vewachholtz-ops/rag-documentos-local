"""Configuraciones de búsqueda sobre el índice: reescritura de la consulta y reordenamiento con el modelo.

- Reescribir: el modelo propone otras consultas con el vocabulario de un procedimiento y los resultados de
  todas se fusionan con RRF. Idea de onyx (consultas de palabras clave para el buscador léxico) y del
  QueryFusionRetriever de llama_index. La pregunta original pesa 1 y cada reescritura 0,5: una reescritura
  sola no le gana a la pregunta, pero tres que coinciden sí.
- Reordenar: el modelo recibe los mejores candidatos numerados y devuelve el orden según cuánto sirven
  para responder (listwise, como RankGPT; Sun et al., 2023). Ollama no tiene un endpoint de reranking, así
  que se usa el mismo modelo de chat y todo sigue siendo local.

Los prompts no traen ejemplos sacados de las preguntas de evaluación, para no ajustarlos a ellas.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .indice import Embedder, Indice, Resultado
from .responder import Chat


@dataclass(frozen=True)
class Busqueda:
    modo: str = "hibrido"  # "bm25", "vector" o "hibrido"
    reescribir: bool = False
    reordenar: bool = False
    candidatos: int = 20  # cuántos trozos ve el modelo al reordenar
    textos: str = "procedimientos"  # los prompts: "procedimientos" (la evaluación) o "general" (la app)


SISTEMA_REESCRIBIR = "Reformulas preguntas para buscar en los procedimientos internos de una empresa minera."
PROMPT_REESCRIBIR = """Pregunta: {pregunta}

Escribe 3 consultas de búsqueda distintas para encontrar la sección del procedimiento que responde esta \
pregunta. Usa el vocabulario formal y técnico con que se escribe un procedimiento, con sinónimos de las \
palabras coloquiales o de jerga. No respondas la pregunta. Escribe una consulta por línea, sin numerarlas."""

SISTEMA_REORDENAR = "Ordenas pasajes de procedimientos según cuánto sirven para responder una pregunta."
PROMPT_REORDENAR = """Pregunta: {pregunta}

Pasajes:

{pasajes}

Ordena los números de los pasajes del más útil al menos útil para responder la pregunta. \
Responde solo con los números separados por comas, por ejemplo: 3, 1, 2."""

# Los mismos pasos para documentos cualesquiera (la app). Los de arriba quedan igual: con ellos se evaluó.
SISTEMA_REESCRIBIR_GENERAL = "Reformulas preguntas para buscar en los documentos de una persona."
PROMPT_REESCRIBIR_GENERAL = """Pregunta: {pregunta}

Escribe 3 consultas de búsqueda distintas para encontrar el pasaje que responde esta pregunta. Usa el \
vocabulario con que lo diría el documento, con sinónimos de las palabras coloquiales. No respondas la \
pregunta. Escribe una consulta por línea, sin numerarlas."""
SISTEMA_REORDENAR_GENERAL = "Ordenas pasajes de documentos según cuánto sirven para responder una pregunta."
TEXTOS = {
    "procedimientos": (SISTEMA_REESCRIBIR, PROMPT_REESCRIBIR, SISTEMA_REORDENAR),
    "general": (SISTEMA_REESCRIBIR_GENERAL, PROMPT_REESCRIBIR_GENERAL, SISTEMA_REORDENAR_GENERAL),
}


def buscar(
    indice: Indice,
    pregunta: str,
    k: int,
    embedder: Embedder | None,
    config: Busqueda | None = None,
    chat: Chat | None = None,
    avisar: Callable[[str], None] | None = None,
) -> list[Resultado]:
    """Los k trozos más útiles. avisar (opcional) recibe cada paso a medida que empieza, para mostrarlo."""
    avisar = avisar or (lambda _texto: None)
    config = config or Busqueda()
    if (config.reescribir or config.reordenar) and chat is None:
        raise ValueError("Reescribir o reordenar necesita un modelo de chat.")
    n = max(k, config.candidatos) if config.reordenar else k
    if config.reescribir:
        avisar("Reformulando la pregunta")
    consultas = [pregunta] + (reescribir(pregunta, chat, textos=config.textos) if config.reescribir else [])
    avisar("Buscando en los procedimientos")
    listas = [indice.buscar(c, k=n, embedder=embedder, modo=config.modo) for c in consultas]
    pesos = [1.0] + [0.5] * (len(listas) - 1)
    candidatos = listas[0] if len(listas) == 1 else fusionar(listas, pesos)[:n]
    if config.reordenar:
        avisar(f"Ordenando {len(candidatos)} pasajes según cuánto sirven")
        candidatos = reordenar(pregunta, candidatos, chat, textos=config.textos)
    return candidatos[:k]


def reescribir(pregunta: str, chat: Chat, maximo: int = 3, textos: str = "procedimientos") -> list[str]:
    sistema, prompt, _ = TEXTOS[textos]
    texto = chat(sistema, prompt.format(pregunta=pregunta))
    consultas: list[str] = []
    for linea in texto.splitlines():
        c = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", linea).strip().strip('"“”')
        if c and c.lower() != pregunta.lower() and c not in consultas:
            consultas.append(c)
    return consultas[:maximo]


def fusionar(listas: list[list[Resultado]], pesos: list[float] | None = None, k_rrf: int = 60) -> list[Resultado]:
    """Fusión por rango recíproco (ponderada) de varias listas de resultados, una por consulta."""
    pesos = pesos or [1.0] * len(listas)
    puntaje: dict[str, float] = {}
    primero: dict[str, Resultado] = {}
    for lista, peso in zip(listas, pesos, strict=True):
        for rango, r in enumerate(lista):
            puntaje[r.trozo.id] = puntaje.get(r.trozo.id, 0.0) + peso / (k_rrf + rango)
            primero.setdefault(r.trozo.id, r)
    orden = sorted(puntaje, key=lambda i: -puntaje[i])
    return [Resultado(primero[i].trozo, puntaje[i], primero[i].rango_bm25, primero[i].rango_vector) for i in orden]


def reordenar(
    pregunta: str, candidatos: list[Resultado], chat: Chat, palabras: int = 120, textos: str = "procedimientos"
) -> list[Resultado]:
    pasajes = "\n\n".join(
        f"[{i}] {r.trozo.titulo}\n{_recortar(r.trozo.texto, palabras)}" for i, r in enumerate(candidatos, 1)
    )
    texto = chat(TEXTOS[textos][2], PROMPT_REORDENAR.format(pregunta=pregunta, pasajes=pasajes))
    orden: list[int] = []
    for n in re.findall(r"\d+", texto):
        i = int(n) - 1
        if 0 <= i < len(candidatos) and i not in orden:
            orden.append(i)
    orden += [i for i in range(len(candidatos)) if i not in orden]  # lo que el modelo no nombró queda al final
    return [candidatos[i] for i in orden]


def _recortar(texto: str, palabras: int) -> str:
    p = texto.split()
    return texto if len(p) <= palabras else " ".join(p[:palabras]) + " …"
