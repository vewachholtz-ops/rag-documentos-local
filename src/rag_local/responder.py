"""Arma el prompt con las fuentes, pide la respuesta al modelo local y la valida.

Validar es la parte que más importa con modelos chicos: una respuesta solo se acepta si cita fuentes que
existen y si cada cifra que menciona aparece en alguna de esas fuentes. Con citas textuales (la opción por
defecto), además, el modelo copia la frase que respalda cada fuente citada y el código comprueba que esa
frase está de verdad en la fuente; así también se revisan los datos que no son cifras. La idea de pedir el
pasaje exacto viene de kotaemon (Cinnamon/kotaemon, Apache-2.0); la implementación es propia.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from .indice import Resultado

Chat = Callable[[str, str], str]
NO_ESTA = "No está en los documentos."
MEZCLA = f'dice que no está en los documentos pero agrega otras afirmaciones; si no está, responde solo "{NO_ESTA}"'

_REGLAS = """Respondes preguntas sobre los procedimientos de una empresa.
Usa SOLO las fuentes numeradas que se te entregan.
Reglas:
1. Responde en español, en una a tres oraciones.
2. Después de cada dato, cita su fuente entre corchetes, por ejemplo [2].
3. Copia las cifras tal como aparecen en la fuente (montos, plazos, porcentajes)."""

SISTEMA = _REGLAS + f"\n4. Si las fuentes no contienen la respuesta, responde exactamente: {NO_ESTA}"

SISTEMA_CON_CITAS = (
    _REGLAS
    + """
4. Después de la respuesta, deja una línea en blanco y escribe una línea por cada fuente que citaste, con \
la frase de esa fuente que respalda el dato, copiada textualmente y entre comillas, así:
[2] "frase copiada de la fuente 2"
"""
    + f"5. Si las fuentes no contienen la respuesta, responde exactamente: {NO_ESTA} y nada más."
)

# Para documentos cualesquiera (la app): respuestas algo más largas, en el idioma de la pregunta. Las reglas de
# citas y de "no está" son las mismas, así que la validación es la misma. Cada cuaderno puede pedir respuestas
# más cortas o más largas y agregar indicaciones propias (como "Configurar el chat" de NotebookLM).
LARGOS = {
    "corto": "de forma muy breve: una o dos oraciones",
    "normal": "de forma breve: un párrafo o una lista corta",
    "largo": "con detalle: varios párrafos o una lista, explicando cada punto con lo que dicen las fuentes",
}


def sistema_general(largo: str = "normal", indicaciones: str = "") -> str:
    texto = f"""Respondes preguntas sobre los documentos de una persona.
Usa SOLO las fuentes numeradas que se te entregan.
Reglas:
1. Responde en el idioma de la pregunta, {LARGOS.get(largo, LARGOS["normal"])}.
2. Después de cada dato, cita su fuente entre corchetes, por ejemplo [2].
3. Copia las cifras tal como aparecen en la fuente (montos, plazos, porcentajes).
4. Después de la respuesta, deja una línea en blanco y escribe una línea por cada fuente que citaste, con \
la frase de esa fuente que respalda el dato, copiada textualmente y entre comillas, así:
[2] "frase copiada de la fuente 2"
5. Si las fuentes no contienen la respuesta, responde exactamente: {NO_ESTA} y nada más."""
    if indicaciones.strip():
        texto += (
            "\n6. La persona pidió además, para este cuaderno (sin dejar de cumplir las reglas anteriores): "
            + " ".join(indicaciones.split())
        )
    return texto


SISTEMA_GENERAL = sistema_general()

_LINEA_CITA = re.compile(r'^\s*[-*]?\s*\[(\d+)\]\s*[:\-\u2013]?\s*["“«](.+?)["”»]\s*\.?\s*$')


@dataclass
class Respuesta:
    texto: str
    fuentes: list[Resultado]
    citas: list[int] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)

    @property
    def valida(self) -> bool:
        return not self.problemas

    @property
    def cuerpo(self) -> str:
        """La respuesta sin las líneas de citas textuales."""
        return separar(self.texto)[0]

    @property
    def textuales(self) -> list[tuple[int, str]]:
        return separar(self.texto)[1]

    @property
    def sin_respuesta(self) -> bool:
        return es_abstencion(self.cuerpo) and not self.textuales


def separar(texto: str) -> tuple[str, list[tuple[int, str]]]:
    """Separa el cuerpo de la respuesta de las líneas [n] "cita textual"."""
    cuerpo, textuales = [], []
    for linea in texto.splitlines():
        m = _LINEA_CITA.match(linea)
        if m:
            textuales.append((int(m.group(1)), m.group(2).strip()))
        else:
            cuerpo.append(linea)
    return "\n".join(cuerpo).strip(), textuales


def armar_prompt(pregunta: str, fuentes: list[Resultado]) -> str:
    bloques = [f"[{i}] {r.trozo.titulo}\n{r.trozo.texto}" for i, r in enumerate(fuentes, 1)]
    return "Fuentes:\n\n" + "\n\n".join(bloques) + f"\n\nPregunta: {pregunta}"


def es_abstencion(texto: str) -> bool:
    """True solo si la respuesta es exactamente "No está en los documentos." (sin importar tildes,
    mayúsculas, puntuación ni citas). Una respuesta que lo dice y además afirma otra cosa no cuenta."""
    sin_citas = re.sub(r"\[\d+\]", " ", texto)
    return _frase(sin_citas) == _frase(NO_ESTA)


def validar(
    texto: str, fuentes: list[Resultado], citas_textuales: bool = False, pregunta: str = "", unidades: bool = False
) -> tuple[list[int], list[str]]:
    """Devuelve las citas encontradas y los problemas: citas inexistentes, falta de citas, cifras sin respaldo,
    una respuesta que dice que no está en los documentos pero igual afirma algo y, con citas textuales,
    fuentes citadas sin su frase o frases que no están en la fuente.

    Una cifra está respaldada si aparece en las fuentes citadas o en la pregunta: repetir el monto que dio
    quien pregunta ("una compra de USD 80.000") no es inventar. Con citas textuales, cada línea [n] "frase"
    cuenta como cita de la fuente n aunque el cuerpo no la repita.

    Con unidades=True (experimento posterior a la evaluación, ver docs/evaluacion.md), además rechaza una cifra
    que en la fuente aparece solo con otra unidad: "10 horas" cuando la fuente dice "10 %"."""
    cuerpo, textuales = separar(texto) if citas_textuales else (texto, [])
    if es_abstencion(cuerpo) and not textuales:
        return [], []
    citas = sorted({int(c) for c in re.findall(r"\[(\d+)\]", cuerpo)} | {n for n, _ in textuales})
    problemas = []
    if _frase(NO_ESTA) in _frase(cuerpo):
        problemas.append(MEZCLA)
    if not citas:
        problemas.append("la respuesta no cita ninguna fuente")
    fuera = [c for c in citas if not 1 <= c <= len(fuentes)]
    if fuera:
        problemas.append(f"cita fuentes que no existen: {fuera}")
    citadas = " ".join(fuentes[c - 1].trozo.texto for c in citas if 1 <= c <= len(fuentes))
    respaldo = set(_numeros(citadas)) | set(_numeros(pregunta))
    sin_respaldo = [n for n in _numeros(re.sub(r"\[\d+\]", " ", cuerpo)) if n not in respaldo]
    if sin_respaldo:
        problemas.append(f"cifras que no aparecen en las fuentes citadas: {sorted(set(sin_respaldo))}")
    if unidades:
        problemas += contradicciones_de_unidad(cuerpo, citadas + "\n" + pregunta)
    if citas_textuales:
        problemas += _revisar_textuales(citas, textuales, fuentes)
    return citas, problemas


def _revisar_textuales(citas: list[int], textuales: list[tuple[int, str]], fuentes: list[Resultado]) -> list[str]:
    problemas = []
    con_frase = {n for n, _ in textuales}
    faltan = [c for c in citas if 1 <= c <= len(fuentes) and c not in con_frase]
    if faltan:
        problemas.append(f"faltan las frases textuales de las fuentes {faltan}")
    for n, frase in textuales:
        if not 1 <= n <= len(fuentes):
            continue
        partes = [p for p in re.split(r"\.\.\.|…", frase) if len(_frase(p).split()) >= 2]
        if len(_frase(frase).split()) < 3 or not partes:
            problemas.append(f'la frase de [{n}] es demasiado corta para comprobarla: "{frase}"')
        elif not all(_frase(p) in _frase(fuentes[n - 1].trozo.texto) for p in partes):
            problemas.append(f'la frase de [{n}] no está textual en la fuente {n}: "{frase}"')
    return problemas


def responder(
    pregunta: str,
    fuentes: list[Resultado],
    chat: Chat,
    reintentos: int = 1,
    citas_textuales: bool = True,
    unidades: bool = False,
    sistema: str | None = None,
) -> Respuesta:
    """Pide la respuesta; si no pasa la validación, la pide de nuevo indicando el problema. `sistema` cambia
    las instrucciones (la app usa SISTEMA_GENERAL; la evaluación, las de procedimientos)."""
    sistema = sistema or (SISTEMA_CON_CITAS if citas_textuales else SISTEMA)
    usuario = armar_prompt(pregunta, fuentes)
    texto = chat(sistema, usuario)
    citas, problemas = validar(texto, fuentes, citas_textuales, pregunta, unidades)
    for _ in range(reintentos):
        if not problemas:
            break
        texto = chat(
            sistema, usuario + f"\n\nTu respuesta anterior tenía estos problemas: {'; '.join(problemas)}. Corrígela."
        )
        citas, problemas = validar(texto, fuentes, citas_textuales, pregunta, unidades)
    return Respuesta(texto.strip(), fuentes, citas, problemas)


def _frase(s: str) -> str:
    """Minúsculas, sin tildes ni puntuación y con los espacios (también saltos de línea) reducidos a uno."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = re.sub(r"(?<=\d)[.\s](?=\d{3}\b)", "", s)  # 30.000 y 30 000 -> 30000
    return " ".join("".join(c for c in s if not unicodedata.combining(c) and (c.isalnum() or c.isspace())).split())


def _numeros(texto: str) -> list[str]:
    """Cifras normalizadas: '5.000', '5 000' y '5000' cuentan igual; se ignoran los números de una sola cifra
    que suelen ser parte del texto (pasos, códigos de revisión)."""
    t = re.sub(r"(?<=\d)[.\s\u00a0\u202f](?=\d{3}\b)", "", texto)
    return [n.replace(",", ".") for n in re.findall(r"\d+(?:,\d+)?", t) if len(n) > 1]


# ---------------- unidades de las cifras (experimento) ----------------
_UNIDADES = {
    "%": "%", "por ciento": "%", "hora": "horas", "horas": "horas", "hr": "horas", "hrs": "horas", "h": "horas",
    "dia": "días", "dias": "días", "semana": "semanas", "semanas": "semanas", "mes": "meses", "meses": "meses",
    "ano": "años", "anos": "años", "minuto": "minutos", "minutos": "minutos", "min": "minutos",
    "litro": "litros", "litros": "litros", "ppm": "ppm", "kg": "kg", "tonelada": "toneladas", "toneladas": "toneladas",
    "km": "km", "metro": "metros", "metros": "metros", "usd": "USD", "us$": "USD", "dolar": "USD", "dolares": "USD",
    "clp": "CLP", "pesos": "CLP", "$": "CLP", "uf": "UF",
}  # fmt: skip
_CON_UNIDAD = re.compile(
    r"(?:(usd|us\$|clp|uf|\$)\s*)?(\d+(?:[.\s]\d{3})*(?:,\d+)?)\s*"
    r"(%|por ciento|horas?|hrs?|h\b|dias?|semanas?|mes(?:es)?|anos?|minutos?|min\b|litros?|ppm|kg|toneladas?|km|"
    r"metros?|usd|clp|uf|dolares|dolar|pesos)?"
)


def cifras_con_unidad(texto: str) -> list[tuple[str, str | None]]:
    """Cada cifra con su unidad, si la tiene pegada: ("10", "%"), ("150000", "USD"), ("450", None)."""
    plano = "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))
    pares = []
    for antes, numero, despues in _CON_UNIDAD.findall(plano):
        unidad = antes or despues
        pares.append((re.sub(r"[.\s](?=\d{3})", "", numero), _UNIDADES[unidad] if unidad else None))
    return pares


def contradicciones_de_unidad(cuerpo: str, evidencia: str) -> list[str]:
    """Las cifras de la respuesta que en la evidencia aparecen solo con otra unidad. Una cifra sin unidad, o que
    en la evidencia también aparece sin unidad o con la misma, no se marca: solo las contradicciones claras."""
    vistas: dict[str, set[str | None]] = {}
    for numero, unidad in cifras_con_unidad(evidencia):
        vistas.setdefault(numero, set()).add(unidad)
    problemas = []
    for numero, unidad in cifras_con_unidad(re.sub(r"\[\d+\]", " ", cuerpo)):
        otras = vistas.get(numero, set())
        if unidad and None not in otras and unidad not in otras and otras:
            problemas.append(
                f"la cifra {numero} {unidad} aparece en la fuente como {numero} {' o '.join(sorted(otras))}"
            )
    return sorted(set(problemas))
