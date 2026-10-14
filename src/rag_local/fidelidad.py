"""Fidelidad (faithfulness): ¿cada afirmación de la respuesta se deduce de las fuentes?

Como en ragas (vibrantlabsai/ragas, `_faithfulness.py`) y en el FaithfulnessEvaluator de haystack: el modelo
parte la respuesta en afirmaciones simples y juzga cada una con 1 (respaldada) o 0. El puntaje es la
fracción respaldada. Se usa solo para evaluar, no al responder.

Un juez también se equivoca. Antes de usarlo, `calibrar` lo prueba con casos cuyo puntaje se conoce.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .responder import Chat

SISTEMA = "Revisas si lo que dice una respuesta está respaldado por las fuentes que se le dieron."
PROMPT = """Fuentes:

{fuentes}

Respuesta:
{respuesta}

Parte la respuesta en afirmaciones simples, sin pronombres y sin las citas entre corchetes. Para cada \
afirmación, pon 1 si se deduce directamente de las fuentes y 0 si no. Responde solo con JSON, así:
{{"afirmaciones": [{{"texto": "...", "respaldada": 1}}]}}"""


@dataclass
class Juicio:
    afirmaciones: list[tuple[str, int]]

    @property
    def puntaje(self) -> float | None:
        if not self.afirmaciones:
            return None
        return sum(v for _, v in self.afirmaciones) / len(self.afirmaciones)


def juzgar(respuesta: str, fuentes: list[str], chat: Chat) -> Juicio:
    bloques = "\n\n".join(f"[{i}] {f}" for i, f in enumerate(fuentes, 1))
    texto = chat(SISTEMA, PROMPT.format(fuentes=bloques, respuesta=respuesta))
    return Juicio(leer_afirmaciones(texto))


def leer_afirmaciones(texto: str) -> list[tuple[str, int]]:
    """Lee el JSON del juez aunque venga dentro de un bloque de código o con texto alrededor."""
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if not m:
        return []
    try:
        datos = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    salida = []
    for a in datos.get("afirmaciones", []):
        if isinstance(a, dict) and "texto" in a and a.get("respaldada") in (0, 1, "0", "1"):
            salida.append((str(a["texto"]), int(a["respaldada"])))
    return salida


# Casos con puntaje conocido: fuentes, respuesta y fracción de afirmaciones respaldadas.
CASOS_CALIBRACION = [
    (["| Hasta USD 5.000 | Jefe del área solicitante |"], "Lo aprueba el jefe del área solicitante [1].", 1.0),
    (["| Hasta USD 5.000 | Jefe del área solicitante |"], "Lo aprueba el gerente general [1].", 0.0),
    (
        ["El curso dura 8 horas y se renueva cada 2 años."],
        "El curso dura 8 horas [1] y se renueva cada 3 años [1].",
        0.5,
    ),
    (["PM2: cambio de aceite de motor y filtros, cada 500 horas."], "El aceite se cambia cada 500 horas [1].", 1.0),
    (
        ["Los candados personales son rojos y tienen una sola llave, que guarda su dueño."],
        "Son rojos [1] y los entrega el supervisor al inicio del turno [1].",
        0.5,
    ),
    (
        ["El material dañado se deja en la zona de cuarentena (zona Q, al fondo del galpón 2)."],
        "Se deja en la zona de cuarentena, al fondo del galpón 2 [1].",
        1.0,
    ),
]


def calibrar(chat: Chat, tolerancia: float = 0.25) -> dict:
    """Corre el juez sobre los casos conocidos y cuenta en cuántos acierta."""
    detalle = []
    for fuentes, respuesta, esperado in CASOS_CALIBRACION:
        p = juzgar(respuesta, fuentes, chat).puntaje
        detalle.append({"respuesta": respuesta, "esperado": esperado, "obtenido": p})
    aciertos = sum(d["obtenido"] is not None and abs(d["obtenido"] - d["esperado"]) <= tolerancia for d in detalle)
    return {"aciertos": aciertos, "casos": len(detalle), "detalle": detalle}
