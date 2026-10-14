"""Responder en la app: la misma búsqueda y validación de la evaluación, sobre la biblioteca de la persona.

Si la pregunta sigue una conversación ("¿y si es más de USD 300.000?"), primero se reescribe como pregunta
completa con la anterior, para que la búsqueda sepa de qué se habla (lo mismo que hacen los chats con
documentos: condensar la pregunta). Después: búsqueda híbrida, reescritura, reordenamiento, respuesta con
citas textuales y comprobación, como la versión mejorada evaluada, pero con instrucciones para documentos
cualesquiera.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable

from .biblioteca import Biblioteca
from .busqueda import Busqueda, buscar
from .indice import Embedder
from .resaltar import marcar_palabras
from .responder import SISTEMA_GENERAL, Chat, responder
from .web import markdown_html, respuesta_de_trozos

SISTEMA_CONDENSAR = "Reescribes preguntas de una conversación para que se entiendan solas."
PROMPT_CONDENSAR = """Conversación:
{historial}

Última pregunta: {pregunta}

Reescribe la última pregunta para que se entienda sin la conversación, con los nombres, montos o temas a los \
que se refiere. Si ya se entiende sola, cópiala igual. Responde solo con la pregunta."""


def condensar(pregunta: str, historial: list[dict], chat: Chat) -> str:
    """La pregunta completa, usando las últimas dos vueltas de la conversación."""
    if not historial:
        return pregunta
    lineas = []
    for vuelta in historial[-2:]:
        lineas.append(f"Pregunta: {str(vuelta.get('pregunta', ''))[:500]}")
        respuesta = re.sub(r"\[\d+\]", "", str(vuelta.get("respuesta", "")))
        lineas.append(f"Respuesta: {' '.join(respuesta.split())[:600]}")
    texto = chat(SISTEMA_CONDENSAR, PROMPT_CONDENSAR.format(historial="\n".join(lineas), pregunta=pregunta))
    completa = " ".join(texto.strip().strip('"“”').split())
    return completa if 3 <= len(completa) <= 400 else pregunta


def responder_en_biblioteca(
    biblioteca: Biblioteca,
    pregunta: str,
    ids: list[str] | None,
    historial: list[dict],
    chat: Chat,
    aux: Chat,
    embedder: Embedder | None,
    a_fondo: bool = True,
    avisar: Callable[[str], None] = lambda _texto: None,
    k: int = 5,
    sistema: str = SISTEMA_GENERAL,
) -> dict:
    """La respuesta con citas comprobadas. `sistema` son las instrucciones del cuaderno (responder.sistema_general)."""
    t0 = time.perf_counter()
    indice = biblioteca.indice(ids)
    if indice is None:
        raise ValueError("No hay documentos elegidos para responder.")
    consulta = pregunta
    if historial:
        avisar("Leyendo la conversación")
        consulta = condensar(pregunta, historial, aux)
    # Sin embeddings en algún documento elegido, se busca solo por palabras (BM25).
    modo = "hibrido" if indice.vectores is not None and embedder is not None else "bm25"
    config = Busqueda(modo=modo, reescribir=a_fondo, reordenar=a_fondo, textos="general")
    fuentes = buscar(indice, consulta, k, embedder, config, aux, avisar=_en_tus_documentos(avisar))
    avisar(f"Leyendo {len(fuentes)} pasajes y redactando la respuesta")
    r = responder(consulta, fuentes, chat, sistema=sistema)
    datos = respuesta_de_trozos(r.texto, [f.trozo for f in fuentes], r.problemas)
    nombres = {d["id"]: d for d in biblioteca.documentos()}
    for fuente, resultado in zip(datos["fuentes"], fuentes, strict=True):
        doc = nombres.get(resultado.trozo.documento, {})
        fuente.update(doc_id=resultado.trozo.documento, pagina=resultado.trozo.pagina, tipo=doc.get("tipo"))
    datos["texto"] = r.cuerpo  # para la conversación: la próxima pregunta puede referirse a esta
    datos["consulta"] = consulta if consulta != pregunta else None
    datos["segundos"] = round(time.perf_counter() - t0)
    return datos


def buscar_en_biblioteca(
    biblioteca: Biblioteca,
    consulta: str,
    ids: list[str] | None,
    embedder: Embedder | None = None,
    avisar: Callable[[str], None] = lambda _texto: None,
    k: int = 8,
) -> dict:
    """El modo solo buscar: los pasajes que más calzan, sin ningún modelo de chat. Con embeddings (Ollama
    abierto) la búsqueda es híbrida; si no, por palabras. Cada pasaje trae las palabras de la consulta marcadas."""
    t0 = time.perf_counter()
    indice = biblioteca.indice(ids)
    if indice is None:
        raise ValueError("No hay documentos elegidos para buscar.")
    modo = "hibrido" if indice.vectores is not None and embedder is not None else "bm25"
    avisar("Buscando en tus documentos")
    resultados = indice.buscar(consulta, k=k, embedder=embedder, modo=modo)
    documentos = {d["id"]: d for d in biblioteca.documentos()}
    pasajes = []
    for n, r in enumerate(resultados, 1):
        trozo = r.trozo
        nombre, _, seccion = trozo.titulo.partition(" > ")
        pasajes.append(
            {
                "n": n,
                "documento": nombre,
                "seccion": seccion or nombre,
                "doc_id": trozo.documento,
                "pagina": trozo.pagina,
                "tipo": documentos.get(trozo.documento, {}).get("tipo"),
                "html": markdown_html(marcar_palabras(trozo.texto, consulta)),
            }
        )
    return {"pasajes": pasajes, "busqueda": "por significado y palabras" if modo == "hibrido" else "por palabras",
            "segundos": round(time.perf_counter() - t0, 2)}  # fmt: skip


def _en_tus_documentos(avisar: Callable[[str], None]) -> Callable[[str], None]:
    """Los pasos de buscar() hablan de procedimientos; en la app, de tus documentos."""
    return lambda texto: avisar(texto.replace("en los procedimientos", "en tus documentos"))
