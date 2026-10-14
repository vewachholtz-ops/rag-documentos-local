"""Contextual Retrieval: antes de indexar, el modelo escribe una frase que ubica cada trozo en su documento.

Técnica publicada por Anthropic (https://www.anthropic.com/news/contextual-retrieval); el prompt adapta al
español el de su cookbook (anthropics/claude-cookbooks, capabilities/contextual-embeddings, MIT). Un trozo
como "Tolerancia: se puede atrasar como máximo un 5 %" no dice de qué equipo habla; con el contexto
("pauta de mantención de las palas eléctricas") la búsqueda lo distingue del de los camiones.
"""

from __future__ import annotations

from dataclasses import replace

from .indice import Trozo
from .responder import Chat

SISTEMA = "Ayudas a indexar procedimientos de una empresa para un buscador."
PROMPT = """<documento>
{documento}
</documento>

Este es el trozo que queremos ubicar dentro del documento completo:
<trozo>
{trozo}
</trozo>

Escribe un contexto breve, de una o dos oraciones en español, que ubique este trozo dentro del documento \
para mejorar su búsqueda: de qué procedimiento es, qué tema trata y a qué equipos, personas o casos se \
aplica. Responde solo con el contexto."""


def agregar_contexto(trozos: list[Trozo], documentos: dict[str, str], chat: Chat) -> list[Trozo]:
    nuevos = []
    for t in trozos:
        texto = chat(SISTEMA, PROMPT.format(documento=documentos[t.documento].strip(), trozo=t.texto))
        nuevos.append(replace(t, contexto=" ".join(texto.split())))
    return nuevos
