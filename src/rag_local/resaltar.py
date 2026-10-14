"""Ubica en la fuente la frase que el modelo copió y la marca, para mostrar de dónde sale cada dato.

La búsqueda ignora mayúsculas, tildes, puntuación, espacios y cómo se escriben los miles (igual que la
validación), pero marca el texto original. Si la frase cruza celdas de una tabla en Markdown, marca cada
celda por separado para no romper la tabla.
"""

from __future__ import annotations

import html
import re
import unicodedata


def _normalizar_con_mapa(texto: str) -> tuple[str, list[int]]:
    """Texto normalizado y, para cada carácter suyo, la posición del carácter original de donde viene."""
    salida: list[str] = []
    mapa: list[int] = []
    previo_espacio = True
    for i, c in enumerate(texto):
        # separador de miles entre dígitos (5.000, 5 000): se omite
        if c in ".\u00a0\u202f " and 0 < i < len(texto) - 3 and texto[i - 1].isdigit():
            if re.match(r"\d{3}(?!\d)", texto[i + 1 : i + 5]):
                continue
        base = "".join(x for x in unicodedata.normalize("NFKD", c.lower()) if not unicodedata.combining(x))
        if base.isalnum():
            salida.append(base)
            mapa.append(i)
            previo_espacio = False
        elif not previo_espacio:
            salida.append(" ")
            mapa.append(i)
            previo_espacio = True
    while salida and salida[-1] == " ":
        salida.pop()
        mapa.pop()
    return "".join(salida), mapa


def ubicar(texto: str, frase: str) -> tuple[int, int] | None:
    """Posición (inicio, fin) de la frase dentro del texto original, o None si no está."""
    norm_texto, mapa = _normalizar_con_mapa(texto)
    norm_frase, _ = _normalizar_con_mapa(frase)
    if not norm_frase:
        return None
    k = norm_texto.find(norm_frase)
    if k < 0:
        return None
    return mapa[k], mapa[k + len(norm_frase) - 1] + 1


def ubicar_todas(texto: str, frases: list[str]) -> list[tuple[int, int]]:
    """Posiciones de cada frase (o de cada parte, si la frase trae puntos suspensivos), sin solaparse."""
    tramos = []
    for frase in frases:
        for parte in re.split(r"\.\.\.|…", frase):
            pos = ubicar(texto, parte) if parte.strip() else None
            if pos:
                tramos.append(pos)
    tramos.sort()
    unidos: list[tuple[int, int]] = []
    for a, b in tramos:
        if unidos and a <= unidos[-1][1]:
            unidos[-1] = (unidos[-1][0], max(b, unidos[-1][1]))
        else:
            unidos.append((a, b))
    return unidos


def marcar(texto: str, frases: list[str], etiqueta: str = "mark") -> str:
    """El texto con HTML escapado y las frases envueltas en <mark>; respeta las celdas de las tablas."""
    partes: list[str] = []
    cursor = 0
    for a, b in ubicar_todas(texto, frases):
        partes.append(html.escape(texto[cursor:a], quote=False))
        # dentro del tramo, cada segmento entre "|" o saltos de línea se marca por separado
        for trozo in re.split(r"(\||\n)", texto[a:b]):
            if trozo in {"|", "\n"} or not trozo.strip():
                partes.append(html.escape(trozo, quote=False))
            else:
                sin_espacios = trozo.strip()
                izq = trozo[: len(trozo) - len(trozo.lstrip())]
                der = trozo[len(trozo.rstrip()) :]
                partes.append(f"{izq}<{etiqueta}>{html.escape(sin_espacios, quote=False)}</{etiqueta}>{der}")
        cursor = b
    partes.append(html.escape(texto[cursor:], quote=False))
    return "".join(partes)


def marcar_palabras(texto: str, consulta: str, etiqueta: str = "mark") -> str:
    """El texto con HTML escapado y cada palabra de la consulta envuelta en <mark> (sin tildes ni mayúsculas;
    las palabras vacías no se marcan). Para el modo solo buscar, donde no hay frase citada que marcar."""
    from .indice import tokens  # aquí para no crear un ciclo de importación

    buscadas = {w for w in tokens(consulta) if len(w) > 2 or w.isdigit()}
    partes: list[str] = []
    cursor = 0
    for m in re.finditer(r"\w+(?:[.,]\d{3})*", texto):
        palabra = tokens(m.group())
        if palabra and palabra[0] in buscadas:
            partes.append(html.escape(texto[cursor : m.start()], quote=False))
            partes.append(f"<{etiqueta}>{html.escape(m.group(), quote=False)}</{etiqueta}>")
            cursor = m.end()
    partes.append(html.escape(texto[cursor:], quote=False))
    return "".join(partes)
