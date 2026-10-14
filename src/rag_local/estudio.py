"""Estudio: lo que Tesela escribe a partir de las fuentes, como el panel Studio de NotebookLM y las
transformaciones de Open Notebook. Hay dos cosas:

- la **guía de cada fuente**: de qué trata, sus temas y preguntas para empezar;
- **notas generadas** con las fuentes del chat: resumen, guía de estudio, preguntas frecuentes, cronología,
  cuestionario, tarjetas de memoria, mapa de ideas o lo que la persona pida.

Un modelo local no lee un documento largo de una vez: Ollama trabaja con un contexto de 8.192 fichas. Por eso se
lee por partes, como se estudia un libro: de cada parte se toman notas fieles (ideas, cifras, fechas, nombres y
definiciones) y lo que se escribe al final sale de esas notas; si las notas no caben, primero se condensan. Es la
técnica map-reduce de los resúmenes de documentos largos. Las notas de cada parte se guardan con el documento
(ver Biblioteca.anexo), así que la segunda guía o resumen que usa el mismo documento no lo vuelve a leer.

Al final se revisan las cifras: las que el texto escrito menciona y no están en ninguna fuente se avisan, como en
las respuestas del chat.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .responder import Chat, _numeros

VERSION = 1  # cambia si cambian las instrucciones de las notas de lectura: las guardadas dejan de servir
Avisar = Callable[[str], None]


@dataclass(frozen=True)
class Medidas:
    ventana: int  # caracteres de cada parte que se lee para tomar notas
    material: int  # caracteres que entran en la escritura final
    partes: int  # partes que se leen como máximo, sumando todas las fuentes
    corta: int  # una fuente de hasta estos caracteres entra tal cual, sin notas


# Ollama: 12.000 caracteres son unas 3.500 fichas; con las instrucciones, el razonamiento y el texto que se
# escribe, cabe en las 8.192 de num_ctx. Una API en la nube suele tener mucho más contexto.
LOCAL = Medidas(ventana=12_000, material=12_000, partes=36, corta=3_000)
NUBE = Medidas(ventana=40_000, material=40_000, partes=36, corta=10_000)


@dataclass
class Fuente:
    id: str
    nombre: str
    texto: str
    notas: dict[str, str] = field(default_factory=dict)  # huella de una parte → sus notas (se guarda)


class SinMaterial(Exception):
    """No hay texto con qué escribir."""


# ---------------- tipos de nota generada ----------------
@dataclass(frozen=True)
class Tipo:
    nombre: str
    que: str  # para el aviso «Escribiendo …»
    tarea: str


TIPOS: dict[str, Tipo] = {
    "resumen": Tipo(
        "Resumen",
        "el resumen",
        "Escribe un resumen para alguien que no ha leído las fuentes: un párrafo inicial con lo esencial; luego "
        "una sección «## » por cada tema principal, con sus datos clave en viñetas; y al final una sección "
        "«## Conclusiones» con lo más importante en tres a cinco viñetas.",
    ),
    "guia": Tipo(
        "Guía de estudio",
        "la guía de estudio",
        "Escribe una guía de estudio con estas secciones: «## Conceptos clave» (cada concepto en negrita, con su "
        "explicación en una o dos oraciones), «## Preguntas de repaso» (8 preguntas de respuesta corta, "
        "numeradas), «## Respuestas» (la respuesta de cada pregunta, con el mismo número) y «## Glosario» (los "
        "términos y su definición, en viñetas).",
    ),
    "faq": Tipo(
        "Preguntas frecuentes",
        "las preguntas frecuentes",
        "Escribe de 8 a 12 preguntas frecuentes que alguien haría sobre estas fuentes. Cada pregunta va como "
        "subtítulo «### ¿…?», seguida de su respuesta en un párrafo corto.",
    ),
    "cronologia": Tipo(
        "Cronología",
        "la cronología",
        "Escribe una cronología con dos secciones: «## Línea de tiempo», una lista en orden cronológico donde "
        "cada viñeta empieza con la fecha en negrita y sigue con lo que pasó; y «## Personas y organizaciones», "
        "una lista con cada persona u organización y su papel. Si las fuentes no tienen fechas, dilo en una línea "
        "y ordena los hechos en el orden en que ocurren.",
    ),
    "cuestionario": Tipo(
        "Cuestionario",
        "el cuestionario",
        "Escribe un cuestionario de 10 preguntas de alternativas sobre lo más importante. Cada pregunta va en una "
        "línea que empieza con su número («1. »), y debajo sus cuatro alternativas, una por línea: «a) …», "
        "«b) …», «c) …» y «d) …»; solo una es correcta. Al final escribe una sección «## Respuestas» con una línea "
        "por pregunta: el número, la letra correcta y por qué, así: «1. b) porque …».",
    ),
    "tarjetas": Tipo(
        "Tarjetas",
        "las tarjetas",
        "Escribe 12 tarjetas de memoria para repasar. Cada tarjeta son dos líneas seguidas: la primera empieza con "
        "«P: » y trae una pregunta o un concepto; la segunda empieza con «R: » y trae la respuesta en una o dos "
        "oraciones. Deja una línea en blanco entre tarjetas.",
    ),
    "mapa": Tipo(
        "Mapa de ideas",
        "el mapa de ideas",
        "Escribe un mapa de ideas como una lista anidada: el título es el tema central; debajo, una viñeta «- » "
        "por cada tema principal y, con dos espacios más de sangría, las ideas y datos que dependen de él, hasta "
        "tres niveles. Frases cortas, de dos a ocho palabras. Escribe solo el título y la lista.",
    ),
    "propia": Tipo("Personalizado", "lo que pediste", ""),
}

SISTEMA_NOTAS = "Tomas notas de lectura fieles al texto, sin agregar nada."
PROMPT_NOTAS = """Documento: {nombre} (parte {parte} de {partes})

{texto}

Toma notas de esta parte en el idioma del documento: una lista de viñetas con las ideas principales y los \
datos concretos (cifras, fechas, plazos, nombres, definiciones y conclusiones). Copia las cifras tal como \
aparecen. Si el texto dice la página, agrégala al final de la viñeta, así: (p. 4). No agregues nada que no esté \
en el texto. Escribe solo la lista."""

SISTEMA_CONDENSAR = "Condensas notas de lectura sin perder datos."
PROMPT_CONDENSAR = """{notas}

Junta estas notas en una lista más corta: une lo repetido y conserva todas las cifras, fechas, nombres y \
definiciones. Mantén los títulos «## Fuente: …» que haya. Escribe solo las notas."""

SISTEMA_GUIA = "Preparas guías de lectura de documentos, fieles al texto."
PROMPT_GUIA = """Documento: {nombre}

{material}

Escribe la guía de este documento en su idioma, con estos tres encabezados exactos:
RESUMEN: un párrafo de tres a cinco oraciones con de qué trata y lo más importante.
TEMAS: de tres a seis temas clave, uno por línea, empezando con «- », de una a cuatro palabras cada uno.
PREGUNTAS: tres preguntas que alguien podría hacerle a este documento, una por línea, empezando con «- ».
Usa solo lo que dice el documento."""

SISTEMA_ESTUDIO = "Escribes material de estudio a partir de las fuentes de una persona, usando solo lo que dicen."
PROMPT_ESTUDIO = """Fuentes:

{material}

Tarea: {tarea}

Reglas:
- Usa solo lo que dicen las fuentes; si no alcanzan para alguna parte, dilo en vez de inventar.
- Escribe en el idioma de las fuentes, en Markdown.
- Copia las cifras, fechas y nombres tal como aparecen.
- Empieza con un título de una línea que comience con «# ».
- Escribe solo el documento, sin comentarios sobre la tarea."""


# ---------------- leer por partes ----------------
def partir(texto: str, ventana: int) -> list[str]:
    """Partes de hasta `ventana` caracteres, cortadas entre párrafos (o entre palabras, si un párrafo es enorme)."""
    partes: list[str] = []
    actual = ""
    for parrafo in re.split(r"\n\s*\n", texto.strip()):
        while len(parrafo) > ventana:  # un párrafo que no cabe se corta en la última palabra que entra
            corte = parrafo.rfind(" ", 0, ventana)
            corte = corte if corte > ventana // 2 else ventana
            if actual:
                partes.append(actual)
                actual = ""
            partes.append(parrafo[:corte].strip())
            parrafo = parrafo[corte:].strip()
        if actual and len(actual) + 2 + len(parrafo) > ventana:
            partes.append(actual)
            actual = ""
        actual = f"{actual}\n\n{parrafo}" if actual else parrafo
    if actual.strip():
        partes.append(actual)
    return [p for p in partes if p.strip()]


def elegir(n: int, k: int) -> list[int]:
    """k índices repartidos parejo entre 0 y n-1 (todos si k >= n): si no se lee todo, se lee de todas partes."""
    if k >= n:
        return list(range(n))
    if k <= 1:
        return [0]
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def huella(modelo: str, parte: str) -> str:
    return hashlib.sha1(f"{VERSION}|{modelo}|{parte}".encode()).hexdigest()[:20]


def _repartir(cuantas: dict[str, int], maximo: int) -> dict[str, int]:
    """Cuántas partes se leen de cada fuente para no pasar del máximo: en proporción a su largo, al menos una."""
    total = sum(cuantas.values())
    if total <= maximo:
        return dict(cuantas)
    if len(cuantas) > maximo:
        raise SinMaterial(f"Hay demasiadas fuentes largas. Incluye como máximo {maximo} para esta tarea de Estudio.")
    cupos = {k: 1 for k in cuantas}
    for _ in range(maximo - len(cupos)):
        clave = max((k for k in cuantas if cupos[k] < cuantas[k]), key=lambda k: cuantas[k] / cupos[k])
        cupos[clave] += 1
    return cupos


def _juntar(pares: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"## Fuente: {nombre}\n\n{texto.strip()}" for nombre, texto in pares)


def material(
    fuentes: list[Fuente], aux: Chat, modelo: str, medidas: Medidas, avisar: Avisar = lambda _t: None
) -> tuple[str, float]:
    """El texto con que se escribe: las fuentes tal cual si caben; si no, notas de lectura de cada parte
    (condensadas si hace falta). Devuelve también qué fracción del texto se leyó. Las notas nuevas quedan en
    `fuente.notas`, para guardarlas."""
    fuentes = [f for f in fuentes if f.texto.strip()]
    if not fuentes:
        raise SinMaterial("Las fuentes no tienen texto.")
    total = sum(len(f.texto) for f in fuentes)
    if total <= medidas.material:
        return _juntar([(f.nombre, f.texto) for f in fuentes]), 1.0
    partes = {f.id: partir(f.texto, medidas.ventana) for f in fuentes if len(f.texto) > medidas.corta}
    cupo = _repartir({k: len(v) for k, v in partes.items()}, medidas.partes)
    total = sum(sum(len(p) for p in partes[f.id]) if f.id in partes else len(f.texto) for f in fuentes)
    leido = 0
    pares: list[tuple[str, str]] = []
    for f in fuentes:
        if f.id not in partes:
            pares.append((f.nombre, f.texto))
            leido += len(f.texto)
            continue
        todas = partes[f.id]
        notas = []
        for n in elegir(len(todas), cupo[f.id]):
            clave = huella(modelo, todas[n])
            if clave not in f.notas:
                avisar(f"Leyendo «{f.nombre}» (parte {n + 1} de {len(todas)})")
                respuesta = aux(
                    SISTEMA_NOTAS, PROMPT_NOTAS.format(nombre=f.nombre, parte=n + 1, partes=len(todas), texto=todas[n])
                )
                f.notas[clave] = limpiar(respuesta)
            notas.append(f.notas[clave])
            leido += len(todas[n])
        pares.append((f.nombre, "\n".join(notas)))
    texto = _juntar(pares)
    for _ in range(3):  # condensar hasta que quepa (tres rondas bastan: cada una deja las notas mucho más cortas)
        if len(texto) <= medidas.material:
            break
        bloques = partir(texto, medidas.material)
        avisar("Ordenando las notas" if len(bloques) == 1 else f"Ordenando las notas ({len(bloques)} partes)")
        texto = "\n\n".join(limpiar(aux(SISTEMA_CONDENSAR, PROMPT_CONDENSAR.format(notas=b))) for b in bloques)
    return texto[: medidas.material], min(1.0, leido / total)


# ---------------- escribir ----------------
def limpiar(texto: str) -> str:
    """Sin el bloque de código con que algunos modelos envuelven el Markdown."""
    texto = texto.strip()
    m = re.fullmatch(r"```[a-zA-Z]*\n(.*?)\n?```", texto, flags=re.S)
    return (m.group(1) if m else texto).strip()


def separar_titulo(texto: str, otro: str) -> tuple[str, str]:
    """El título «# …» de las primeras líneas, y el resto. Sin título, `otro`."""
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas[:3]):
        m = re.match(r"^\s*#\s+(.+?)\s*#*\s*$", linea)
        if m:
            titulo = m.group(1).strip().strip("*").strip()
            return titulo[:200] or otro, "\n".join(lineas[:i] + lineas[i + 1 :]).strip()
    return otro, texto.strip()


def escribir(tipo: str, material_: str, chat: Chat, instruccion: str = "") -> tuple[str, str]:
    """(título, contenido en Markdown) de una nota generada."""
    t = TIPOS[tipo]
    tarea = instruccion.strip() if tipo == "propia" else t.tarea
    if not tarea:
        raise SinMaterial("Escribe qué quieres que haga.")
    texto = limpiar(chat(SISTEMA_ESTUDIO, PROMPT_ESTUDIO.format(material=material_, tarea=tarea)))
    if not texto:
        raise SinMaterial("El modelo respondió vacío. Vuelve a intentarlo.")
    return separar_titulo(texto, t.nombre)


_ENCABEZADO = re.compile(
    r"^[#*_\s]*(resumen|temas(?: clave)?|preguntas(?: sugeridas)?)[*_\s]*(?::|$)[*_\s]*(.*)$", re.IGNORECASE
)


def leer_guia(texto: str) -> dict:
    """Separa la respuesta del modelo en resumen, temas y preguntas. Acepta variaciones: «**Resumen:**»,
    «## Temas», el resumen en la misma línea del encabezado, temas separados por comas."""
    secciones: dict[str, list[str]] = {"resumen": [], "temas": [], "preguntas": []}
    actual = None
    for linea in limpiar(texto).splitlines():
        if m := _ENCABEZADO.match(linea):
            actual = m.group(1).split()[0].lower()
            if m.group(2).strip(" *"):
                secciones[actual].append(m.group(2).strip(" *"))
        elif actual and linea.strip():
            secciones[actual].append(linea.strip())

    def items(lineas: list[str], comas: bool = False) -> list[str]:
        salida = []
        for linea in lineas:
            vineta = re.match(r"^\s*([-*•]|\d+[.)])\s", linea)
            partes = re.split(r"[,;]\s*", linea) if comas and not vineta else [linea]
            for p in partes:
                p = re.sub(r"^\s*([-*•]|\d+[.)])\s*", "", p).strip().strip("*").strip().rstrip(".")
                if p:
                    salida.append(p)
        return salida

    resumen = " ".join(secciones["resumen"]).strip()
    temas = [t[:60] for t in items(secciones["temas"], comas=True)][:8]
    preguntas = [p[:200] for p in items(secciones["preguntas"]) if len(p) > 5][:5]
    preguntas = [p if p.endswith("?") else f"{p}?" for p in preguntas]
    if not resumen and not temas:
        resumen = " ".join(limpiar(texto).split())[:1500]
    return {"resumen": resumen, "temas": temas, "preguntas": preguntas}


def escribir_guia(nombre: str, material_: str, chat: Chat) -> dict:
    texto = chat(SISTEMA_GUIA, PROMPT_GUIA.format(nombre=nombre, material=material_))
    guia = leer_guia(texto)
    if not guia["resumen"]:
        raise SinMaterial("El modelo respondió vacío. Vuelve a intentarlo.")
    return guia


def cifras_sin_respaldo(contenido: str, textos: list[str]) -> list[str]:
    """Las cifras de dos o más dígitos del texto escrito que no aparecen en ninguna fuente (sin contar la
    numeración de las listas ni de los títulos)."""
    sin_numeracion = re.sub(r"(?m)^\s*(?:#{1,6}\s*)?(?:\*\*)?\d{1,3}[.)](?:\*\*)?\s", " ", contenido)
    respaldo = set()
    for texto in textos:
        respaldo |= set(_numeros(texto))
    return sorted({n for n in _numeros(sin_numeracion) if n not in respaldo})[:12]
