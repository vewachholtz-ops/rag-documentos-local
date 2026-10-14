"""Corre todas las configuraciones con las mismas preguntas y arma las tablas de resultados.

Búsqueda: BM25, vectores, híbrido (la v1), híbrido sin descartar documentos obsoletos y el híbrido con
Contextual Retrieval, con y sin reescritura de la consulta y reordenamiento.
Respuestas: la v1 (búsqueda híbrida, validación de cifras y citas) contra la v2 (la mejor búsqueda por MRR,
más citas textuales verificadas), ambas con el juez de fidelidad calibrado antes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .busqueda import Busqueda, buscar
from .contexto import agregar_contexto
from .evaluar import evaluar_busqueda, evaluar_respuestas, revisar_unidades
from .fidelidad import calibrar
from .indice import Embedder, Indice, cargar_documentos, trocear_documentos
from .responder import Chat

CONFIGS: list[tuple[str, str, Busqueda]] = [
    ("BM25", "base", Busqueda("bm25")),
    ("Vectores", "base", Busqueda("vector")),
    ("Híbrido (v1)", "base", Busqueda()),
    ("Híbrido sin descartar obsoletos", "con_obsoletos", Busqueda()),
    ("Híbrido + contexto", "contexto", Busqueda()),
    ("Híbrido + contexto + reescritura", "contexto", Busqueda(reescribir=True)),
    ("Híbrido + contexto + reordenamiento", "contexto", Busqueda(reordenar=True)),
    ("Híbrido + contexto + reescritura + reordenamiento", "contexto", Busqueda(reescribir=True, reordenar=True)),
]
NO_ELEGIBLES = {"BM25", "Vectores", "Híbrido sin descartar obsoletos"}


@dataclass
class Modelos:
    embeber_documentos: Embedder
    embeber_consulta: Embedder
    chat: Chat  # responde
    aux: Chat  # contexto, reescritura y reordenamiento
    nombres: dict[str, str] = field(default_factory=dict)
    juez: Chat | None = None  # fidelidad; si no se indica, el auxiliar

    def reloj(self) -> float:
        """Segundos transcurridos más los que habrían tomado las respuestas sacadas de la caché."""
        llms = {id(x): x for x in (self.chat, self.aux, self.juez) if x is not None}.values()
        return time.perf_counter() + sum(getattr(x, "ahorrados", 0.0) for x in llms)


def construir_indices(carpeta: Path, m: Modelos, avance: Callable[[str], None]) -> dict[str, Indice]:
    vigentes = cargar_documentos(carpeta)
    todos = cargar_documentos(carpeta, incluir_obsoletos=True)
    trozos = trocear_documentos(vigentes)
    obsoletos = len(todos) - len(vigentes)
    avance(f"{len(trozos)} trozos de {len(vigentes)} documentos vigentes ({obsoletos} obsoletos)")
    base = Indice.construir(trozos, m.embeber_documentos)
    con_obsoletos = Indice.construir(trocear_documentos(todos), m.embeber_documentos)
    con_contexto = []
    for i, t in enumerate(trozos, 1):
        con_contexto += agregar_contexto([t], vigentes, m.aux)
        avance(f"contexto {i}/{len(trozos)}")
    return {
        "base": base,
        "con_obsoletos": con_obsoletos,
        "contexto": Indice.construir(con_contexto, m.embeber_documentos),
    }


def correr(carpeta: Path, preguntas: list[dict], m: Modelos, avance: Callable[[str], None] = print) -> dict:
    tiempos: dict[str, float] = {}
    t0 = time.perf_counter()
    indices = construir_indices(carpeta, m, avance)
    tiempos["indices"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    juez = m.juez or m.aux
    calibracion = calibrar(juez)
    avance(f"juez: {calibracion['aciertos']} de {calibracion['casos']} casos de calibración")
    tiempos["calibracion"] = time.perf_counter() - t0

    obsoletos = {t.documento for t in indices["con_obsoletos"].trozos} - {t.documento for t in indices["base"].trozos}
    busqueda = {}
    for nombre, idx, cfg in CONFIGS:
        t0 = time.perf_counter()
        busqueda[nombre] = evaluar_busqueda(
            indices[idx], preguntas, m.embeber_consulta, cfg, m.aux, avance=lambda s, n=nombre: avance(f"{n}: {s}")
        )
        if idx == "con_obsoletos":
            version = [p for p in preguntas if p.get("tipo") == "versión"]
            primero = [buscar(indices[idx], p["pregunta"], 1, m.embeber_consulta, cfg)[0] for p in version]
            n_obsoleto = sum(r.trozo.documento in obsoletos for r in primero)
            busqueda[nombre]["version_con_obsoleto_primero"] = f"{n_obsoleto}/{len(version)}"
        tiempos[f"busqueda: {nombre}"] = time.perf_counter() - t0

    elegibles = [c for c in CONFIGS if c[0] not in NO_ELEGIBLES]
    nombre_v2, idx_v2, cfg_v2 = max(elegibles, key=lambda c: (busqueda[c[0]]["mrr@5"], busqueda[c[0]]["acierto@3"]))
    avance(f"configuración elegida para la v2: {nombre_v2}")

    respuestas = {}
    t0 = time.perf_counter()
    resumen, detalle = evaluar_respuestas(
        indices["base"], preguntas, m.embeber_consulta, m.chat, citas_textuales=False, juez=juez,
        avance=lambda s: avance(f"v1: {s}"), reloj=m.reloj,
    )  # fmt: skip
    respuestas["v1"] = {"busqueda": "Híbrido (v1)", "citas_textuales": False, "resumen": resumen, "detalle": detalle}
    tiempos["respuestas v1"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    resumen, detalle = evaluar_respuestas(
        indices[idx_v2], preguntas, m.embeber_consulta, m.chat, config=cfg_v2, chat_aux=m.aux,
        citas_textuales=True, juez=juez, avance=lambda s: avance(f"v2: {s}"), reloj=m.reloj,
    )  # fmt: skip
    respuestas["v2"] = {"busqueda": nombre_v2, "citas_textuales": True, "resumen": resumen, "detalle": detalle}
    tiempos["respuestas v2"] = time.perf_counter() - t0

    return {
        "modelos": m.nombres,
        "preguntas": len(preguntas),
        "calibracion_juez": calibracion,
        "busqueda": busqueda,
        "respuestas": respuestas,
        "minutos": {k: round(v / 60, 1) for k, v in tiempos.items()},
        "indices": indices,
    }


def informe(r: dict) -> str:
    """Tablas en Markdown, listas para el README."""
    pct = lambda x: f"{100 * x:.0f} %"  # noqa: E731
    b = r["busqueda"]
    n_con = r["respuestas"]["v1"]["resumen"]["con_respuesta_total"]
    lineas = [
        f"### Búsqueda ({n_con} preguntas con respuesta; ¿está la sección correcta entre las k recuperadas?)",
        "",
        "| Configuración | Acierto@1 | Acierto@3 | Acierto@5 | MRR@5 | Documento correcto en 4 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for nombre, _, _ in CONFIGS:
        x = b[nombre]
        lineas.append(
            f"| {nombre} | {pct(x['acierto@1'])} | {pct(x['acierto@3'])} | {pct(x['acierto@5'])} | "
            f"{x['mrr@5']:.2f} | {pct(x['acierto_documento@4'])} |"
        )
    obsoleto = b.get("Híbrido sin descartar obsoletos", {}).get("version_con_obsoleto_primero")
    if obsoleto:
        n, total = obsoleto.split("/")
        lineas += [
            "",
            f"Sin descartar el documento obsoleto, en {n} de {total} preguntas de versión el primer resultado "
            "es la versión obsoleta.",
        ]
    tipos = list(next(iter(b.values()))["acierto@5_por_tipo"])
    lineas += ["", "Acierto@5 por tipo de pregunta:", "", "| Configuración | " + " | ".join(tipos) + " |"]
    lineas.append("|---|" + "---:|" * len(tipos))
    for nombre, _, _ in CONFIGS:
        x = b[nombre]["acierto@5_por_tipo"]
        lineas.append(f"| {nombre} | " + " | ".join(pct(x[t]) for t in tipos) + " |")
    v = r["respuestas"]
    lineas += [
        "",
        "### Respuestas",
        "",
        "| | v1 | v2 |",
        "|---|---:|---:|",
        f"| Búsqueda | {v['v1']['busqueda']} | {v['v2']['busqueda']} |",
        "| Citas textuales verificadas | no | sí |",
    ]

    def fidelidad(s: dict) -> str:
        return "—" if s["fidelidad_promedio"] is None else f"{s['fidelidad_promedio']:.2f}"

    filas = [
        (
            "Correctas, preguntas con respuesta",
            lambda s: f"{s['con_respuesta_correctas']} de {s['con_respuesta_total']}",
        ),
        ("Trampas rechazadas", lambda s: f"{s['trampa_rechazadas']} de {s['trampa_total']}"),
        ("Citan la sección correcta", lambda s: f"{s['citan_seccion_correcta']} de {s['con_respuesta_total']}"),
        ("No pasan la validación", lambda s: str(s["respuestas_que_no_pasan_validacion"])),
        ("Fidelidad promedio (juez)", fidelidad),
        ("Segundos por pregunta", lambda s: f"{s['segundos_promedio']:.0f}"),
    ]
    for etiqueta, f in filas:
        lineas.append(f"| {etiqueta} | {f(v['v1']['resumen'])} | {f(v['v2']['resumen'])} |")
    c = r["calibracion_juez"]
    lineas += [
        "",
        f"Juez de fidelidad: acierta {c['aciertos']} de {c['casos']} casos de calibración con puntaje conocido.",
    ]
    return "\n".join(lineas) + "\n"


def experimento_unidades(
    previa: dict, preguntas: list[dict], textos: dict[str, str], indice: Indice | None, m: Modelos | None, avance=print
) -> dict:
    """La comprobación de unidades, medida después de la evaluación sin tocarla.

    Sin modelo: qué respuestas guardadas habría marcado (¿marca errores?, ¿marca respuestas correctas?).
    Con modelo e índice: vuelve a responder con la configuración de la v2 más la comprobación. Con la caché de la
    evaluación, solo las respuestas que ahora no pasan piden una llamada nueva (el reintento)."""
    salida = {"sin_modelo": {v: revisar_unidades(previa["respuestas"][v]["detalle"], preguntas, textos)
                             for v in ("v1", "v2")}}  # fmt: skip
    if indice is None or m is None:
        return salida
    nombre = previa["respuestas"]["v2"]["busqueda"]
    config = next(c for n, _, c in CONFIGS if n == nombre)
    resumen, detalle = evaluar_respuestas(
        indice, preguntas, m.embeber_consulta, m.chat, config=config, chat_aux=m.aux, citas_textuales=True,
        juez=m.juez, avance=lambda s: avance(f"v2 + unidades: {s}"), reloj=m.reloj, unidades=True,
    )  # fmt: skip
    antes = {f["id"]: f for f in previa["respuestas"]["v2"]["detalle"]}
    cambios = [
        {"id": f["id"], "antes": antes[f["id"]]["respuesta"], "despues": f["respuesta"],
         "correcta_antes": antes[f["id"]]["correcta"], "correcta_despues": f["correcta"], "problemas": f["problemas"]}
        for f in detalle
        if f["respuesta"] != antes[f["id"]]["respuesta"]
    ]  # fmt: skip
    salida["con_modelo"] = {"busqueda": nombre, "resumen": resumen, "detalle": detalle, "cambios": cambios}
    return salida


def informe_unidades(r: dict, previa: dict) -> str:
    lineas = [
        "# Experimento: la unidad de las cifras",
        "",
        "La validación revisa que cada cifra de la respuesta aparezca en la fuente, pero no con qué unidad: en la",
        'evaluación, la v2 respondió "hasta 10 horas" donde la fuente dice "10 %". Este experimento agrega esa',
        "comprobación (`validar(..., unidades=True)`) y la mide sin cambiar la evaluación guardada.",
        "",
        "## Sin modelo: sobre las respuestas guardadas",
        "",
    ]
    for v in ("v1", "v2"):
        detalle = previa["respuestas"][v]["detalle"]
        marcadas = r["sin_modelo"][v]
        malas = sum(not f["correcta"] for f in detalle)
        mal_marcadas = sum(not f["correcta"] for f in marcadas)
        lineas.append(
            f"- **{v}:** marca {len(marcadas)} de {len(detalle)} respuestas: {mal_marcadas} de sus {malas} "
            f"incorrectas y {len(marcadas) - mal_marcadas} correctas."
        )
        lineas += [f"  - {f['id']}: {'; '.join(f['problemas'])}" for f in marcadas]
    if "con_modelo" not in r:
        lineas += ["", "Falta la parte con modelo: `uv run rag evaluar --unidades` con Ollama abierto."]
        return "\n".join(lineas) + "\n"
    c, v2 = r["con_modelo"], previa["respuestas"]["v2"]["resumen"]
    s = c["resumen"]
    lineas += [
        "",
        "## Con modelo: la v2 más la comprobación",
        "",
        "| | v2 | v2 + unidades |",
        "|---|---:|---:|",
        f"| Correctas, preguntas con respuesta | {v2['con_respuesta_correctas']} de {v2['con_respuesta_total']} | "
        f"{s['con_respuesta_correctas']} de {s['con_respuesta_total']} |",
        f"| Trampas rechazadas | {v2['trampa_rechazadas']} de {v2['trampa_total']} | "
        f"{s['trampa_rechazadas']} de {s['trampa_total']} |",
        f"| No pasan la validación | {v2['respuestas_que_no_pasan_validacion']} | "
        f"{s['respuestas_que_no_pasan_validacion']} |",
        "",
        f"Respuestas que cambiaron: {len(c['cambios'])}.",
    ]
    for cambio in c["cambios"]:
        lineas += [
            "",
            f"**{cambio['id']}** ({'correcta' if cambio['correcta_antes'] else 'incorrecta'} → "
            f"{'correcta' if cambio['correcta_despues'] else 'incorrecta'})",
            "",
            f"- Antes: {cambio['antes'].splitlines()[0]}",
            f"- Después: {cambio['despues'].splitlines()[0]}",
        ]
    return "\n".join(lineas) + "\n"
