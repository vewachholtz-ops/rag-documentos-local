"""Lo que la interfaz web necesita de una respuesta: HTML seguro, citas, fuentes con la frase marcada.

Lo usan la vitrina estática (scripts/construir_sitio.py, con las respuestas guardadas de la evaluación) y el
servidor local (servidor.py, con respuestas nuevas de Ollama), así que las dos muestran lo mismo.
"""

from __future__ import annotations

import html
import re

from .indice import Trozo
from .resaltar import marcar
from .responder import separar

AREAS = {
    "PR-COM": "Compras y gastos",
    "PR-FIN": "Compras y gastos",
    "PR-BOD": "Bodega e inventario",
    "PR-INV": "Bodega e inventario",
    "PR-MAN": "Mantención",
    "PR-SEG": "Seguridad y medio ambiente",
    "PR-AMB": "Seguridad y medio ambiente",
    "PR-RRHH": "Personas y turnos",
    "PR-PRO": "Proyectos y operación",
    "PR-OPE": "Proyectos y operación",
}


def area(nombre: str) -> str:
    """Área de un documento o sección por el código del procedimiento ("PR-COM-01 …" → compras)."""
    return next((a for prefijo, a in AREAS.items() if nombre.startswith(prefijo + "-")), "Otros")


def _en_linea(texto: str) -> str:
    """Negritas de Markdown en un texto que ya viene escapado."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", texto)


def markdown_html(escapado: str) -> str:
    """HTML de un procedimiento: títulos, párrafos, listas, tablas y negritas.

    Recibe texto ya escapado (por ejemplo, la salida de marcar()), así que no vuelve a escapar y conserva
    las etiquetas <mark>. Cubre solo lo que usan nuestros documentos, no Markdown arbitrario.
    """
    lineas, salida, i = escapado.splitlines(), [], 0
    while i < len(lineas):
        linea = lineas[i].rstrip()
        if not linea.strip():
            i += 1
        elif linea.lstrip().startswith("|"):
            filas = []
            while i < len(lineas) and lineas[i].lstrip().startswith("|"):
                celdas = [c.strip() for c in lineas[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in celdas):
                    etiqueta = "th" if not filas else "td"
                    filas.append("<tr>" + "".join(f"<{etiqueta}>{_en_linea(c)}</{etiqueta}>" for c in celdas) + "</tr>")
                i += 1
            cuerpo = "".join(filas[1:])
            salida.append(f'<div class="tabla"><table><thead>{filas[0]}</thead><tbody>{cuerpo}</tbody></table></div>')
        elif re.match(r"\s*#{1,6} ", linea):
            marca = linea.lstrip()
            nivel = min(6, len(marca) - len(marca.lstrip("#")) + 2)
            salida.append(f"<h{nivel}>{_en_linea(marca.lstrip('#').strip())}</h{nivel}>")
            i += 1
        elif re.match(r"\s*(?:[-*]|\d+\.) ", linea):
            ordenada = bool(re.match(r"\s*\d+\. ", linea))
            items = []
            while i < len(lineas) and re.match(r"\s*(?:[-*]|\d+\.) ", lineas[i]):
                items.append(f"<li>{_en_linea(re.sub(r'^\s*(?:[-*]|\d+\.) ', '', lineas[i]).strip())}</li>")
                i += 1
            etiqueta = "ol" if ordenada else "ul"
            salida.append(f"<{etiqueta}>{''.join(items)}</{etiqueta}>")
        else:
            # La primera línea entra siempre: así cada vuelta avanza aunque la línea no calce con nada.
            parrafo = [linea.strip()]
            i += 1
            while i < len(lineas) and lineas[i].strip() and not re.match(r"\s*(?:\||#{1,6} |[-*] |\d+\. )", lineas[i]):
                parrafo.append(lineas[i].strip())
                i += 1
            salida.append(f"<p>{_en_linea(' '.join(parrafo))}</p>")
    return "".join(salida)


# ---------------- notas ----------------
_ITEM = re.compile(r"^( *)([-*+]|\d{1,3}[.)]) +(.*)$")
_TABLA = re.compile(r"^\s*\|")
_FENCE = re.compile(r"^\s*```")
_TITULO = re.compile(r"^ {0,3}(#{1,6})\s+(.*)$")
_LINEA_HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_CITA = re.compile(r"^\s*&gt;\s?")
_ENLACE = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)\"<>]+)\)")


def _en_linea_nota(texto: str) -> str:
    """Código, enlaces http(s), negritas y cursivas en un texto que ya viene escapado."""
    codigos: list[str] = []

    def guardar(m: re.Match) -> str:
        codigos.append(m.group(1))
        return f"\x00{len(codigos) - 1}\x00"

    texto = re.sub(r"`([^`\n]+)`", guardar, texto)
    texto = _ENLACE.sub(r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', texto)
    texto = re.sub(r"\*\*(?!\s)(.+?)(?<!\s)\*\*", r"<strong>\1</strong>", texto)
    texto = re.sub(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])", r"<em>\1</em>", texto)
    texto = re.sub(r"(?<![\w_])_(?![\s_])(.+?)(?<![\s_])_(?![\w_])", r"<em>\1</em>", texto)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codigos[int(m.group(1))]}</code>", texto)


def _empieza_bloque(linea: str) -> bool:
    return bool(
        _ITEM.match(linea)
        or _TABLA.match(linea)
        or _FENCE.match(linea)
        or _TITULO.match(linea)
        or _LINEA_HR.match(linea)
        or _CITA.match(linea)
    )


def _lista(lineas: list[str], i: int) -> tuple[str, int]:
    """Una lista con sangrías (hasta varios niveles), numerada o no. Devuelve el HTML y la línea siguiente."""
    items: list[tuple[int, bool, int, str]] = []  # sangría, numerada, número, texto
    while i < len(lineas):
        m = _ITEM.match(lineas[i])
        if m:
            marca = m.group(2)
            numerada = marca[0].isdigit()
            if items and len(m.group(1)) <= items[0][0] and numerada != items[0][1]:
                break  # de viñetas a números (o al revés) en el primer nivel: es otra lista
            items.append((len(m.group(1)), numerada, int(marca[:-1]) if numerada else 0, m.group(3).strip()))
            i += 1
        elif items and lineas[i].startswith(" ") and lineas[i].strip() and not _empieza_bloque(lineas[i]):
            sangria, numerada, numero, texto = items[-1]
            items[-1] = (sangria, numerada, numero, f"{texto} {lineas[i].strip()}")  # el ítem sigue en otra línea
            i += 1
        elif not lineas[i].strip() and i + 1 < len(lineas) and _ITEM.match(lineas[i + 1]):
            i += 1  # una línea en blanco entre ítems no corta la lista
        else:
            break
    salida: list[str] = []
    pila: list[tuple[int, str]] = []
    for sangria, numerada, numero, texto in items:
        contenido = _en_linea_nota(texto)
        if pila and sangria <= pila[-1][0]:
            while len(pila) > 1 and sangria < pila[-1][0]:
                salida.append(f"</li></{pila.pop()[1]}>")
            salida.append(f"</li><li>{contenido}")
            continue
        etiqueta = "ol" if numerada else "ul"
        inicio = f' start="{numero}"' if numerada and numero != 1 else ""
        salida.append(f"<{etiqueta}{inicio}><li>{contenido}")
        pila.append((sangria, etiqueta))
    while pila:
        salida.append(f"</li></{pila.pop()[1]}>")
    return "".join(salida), i


def _bloques(lineas: list[str]) -> str:
    salida, i = [], 0
    while i < len(lineas):
        linea = lineas[i]
        if not linea.strip():
            i += 1
        elif _FENCE.match(linea):
            codigo = []
            i += 1
            while i < len(lineas) and not _FENCE.match(lineas[i]):
                codigo.append(lineas[i])
                i += 1
            i += 1
            salida.append("<pre><code>" + "\n".join(codigo) + "</code></pre>")
        elif _LINEA_HR.match(linea):
            salida.append("<hr>")
            i += 1
        elif m := _TITULO.match(linea):
            nivel = min(6, len(m.group(1)) + 1)  # el título de la nota va aparte: «#» queda como <h2>
            salida.append(f"<h{nivel}>{_en_linea_nota(m.group(2).strip().rstrip('#').strip())}</h{nivel}>")
            i += 1
        elif _TABLA.match(linea):
            filas = []
            while i < len(lineas) and _TABLA.match(lineas[i]):
                celdas = [c.strip() for c in lineas[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in celdas):
                    etiqueta = "th" if not filas else "td"
                    filas.append(
                        "<tr>" + "".join(f"<{etiqueta}>{_en_linea_nota(c)}</{etiqueta}>" for c in celdas) + "</tr>"
                    )
                i += 1
            cuerpo = "".join(filas[1:])
            salida.append(f'<div class="tabla"><table><thead>{filas[0]}</thead><tbody>{cuerpo}</tbody></table></div>')
        elif _CITA.match(linea):
            citadas = []
            while i < len(lineas) and _CITA.match(lineas[i]):
                citadas.append(_CITA.sub("", lineas[i], count=1))
                i += 1
            salida.append(f"<blockquote>{_bloques(citadas)}</blockquote>")
        elif _ITEM.match(linea):
            lista, i = _lista(lineas, i)
            salida.append(lista)
        else:
            parrafo = [linea.strip()]
            i += 1
            while i < len(lineas) and lineas[i].strip() and not _empieza_bloque(lineas[i]):
                parrafo.append(lineas[i].strip())
                i += 1
            salida.append("<p>" + "<br>".join(_en_linea_nota(p) for p in parrafo) + "</p>")
    return "".join(salida)


def markdown_nota(texto: str) -> str:
    """HTML seguro de una nota escrita a mano o generada: títulos, listas anidadas, tablas, citas, código,
    negritas, cursivas y enlaces http(s). Todo se escapa antes; en un párrafo, cada salto de línea se respeta."""
    escapado = html.escape(str(texto).replace("\r\n", "\n").replace("\t", "    "))
    return _bloques(escapado.split("\n"))


def respuesta_html(cuerpo: str) -> str:
    """El texto de la respuesta escapado, con cada [n] convertido en una cita que se puede pulsar."""
    seguro = html.escape("\n".join(linea.rstrip() for linea in cuerpo.strip().splitlines()), quote=False)
    seguro = re.sub(r"\[(\d+)\]", r'<button type="button" class="cita" data-n="\1">\1</button>', seguro)
    return "<p>" + seguro.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


def estado(cuerpo: str, problemas: list[str], hay_frases: bool) -> dict:
    """La comprobación de las citas: una etiqueta corta y el detalle de lo que se revisó, dicho tal como lo hace
    responder.validar. Revisa que el texto exista, no que la conclusión sea correcta; las cifras de un dígito no
    se revisan, y una cifra puede venir de la pregunta."""
    if problemas:
        return {"tipo": "alerta", "texto": "No pasó la comprobación de citas", "detalle": "; ".join(problemas) + "."}
    if "no está en los documentos" in cuerpo.lower():
        return {"tipo": "neutro", "texto": "Dijo que no está en los documentos", "detalle": ""}
    cifras = "las cifras de dos o más dígitos aparecen en las fuentes citadas o en la pregunta"
    limite = "No se comprueba que la conclusión sea correcta."
    if hay_frases:
        return {
            "tipo": "literal",
            "texto": "Citas encontradas textuales en sus fuentes",
            "detalle": f"Cada frase copiada está textual en su fuente, y {cifras}. {limite}",
        }
    return {
        "tipo": "literal",
        "texto": "Cifras encontradas en las fuentes",
        "detalle": f"{cifras[0].upper()}{cifras[1:]}. {limite}",
    }


def respuesta(texto: str, titulos: list[str], trozos: dict[str, Trozo], problemas: list[str]) -> dict:
    """Todo lo que la interfaz muestra de una respuesta del modelo y sus fuentes, en el orden de la corrida.

    Una fuente que ya no existe detiene todo: quitarla correría la numeración y cada [n] apuntaría a otra.
    """
    for titulo in titulos:
        if titulo not in trozos:
            raise ValueError(f"Fuente ausente: {titulo}. No renumerar las citas.")
    return respuesta_de_trozos(texto, [trozos[t] for t in titulos], problemas)


def respuesta_de_trozos(texto: str, fuentes: list[Trozo], problemas: list[str]) -> dict:
    """Lo mismo que respuesta(), con los trozos ya en el orden en que se le dieron al modelo."""
    cuerpo, textuales = separar(texto)
    en_linea = {int(n) for n in re.findall(r"\[(\d+)\]", cuerpo)}
    citas = en_linea | {n for n, _ in textuales}
    # A veces el modelo cita una fuente solo con la frase copiada, sin [n] en el texto: el número va al final,
    # para que toda fuente citada tenga su número en la respuesta.
    visible = cuerpo.rstrip() + "".join(f" [{n}]" for n in sorted(citas - en_linea))
    salida = []
    for n, trozo in enumerate(fuentes, 1):
        documento, _, seccion = trozo.titulo.partition(" > ")
        frases = [frase for numero, frase in textuales if numero == n]
        salida.append(
            {
                "n": n,
                "documento": documento,
                "codigo": documento.split(" ")[0],
                "seccion": seccion or documento,
                "citada": n in citas,
                "html": markdown_html(marcar(trozo.texto, frases)),
            }
        )
    return {
        "html": respuesta_html(visible),
        "frases": [{"n": n, "texto": frase} for n, frase in textuales],
        "fuentes": salida,
        "estado": estado(cuerpo, problemas, bool(textuales)),
        "abstencion": "no está en los documentos" in cuerpo.lower(),
    }
