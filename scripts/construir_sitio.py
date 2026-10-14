"""Genera la app web en site/: la misma página sirve en GitHub Pages y con `uv run rag servir`.

En Pages responde con lo guardado en la evaluación (las 74 preguntas, en la v1 y en la v2); con el servidor
local, la página detecta la API y pregunta a Ollama. Lo que cambia entre una y otra está en web/app.js.

Las respuestas se arman con rag_local.web, igual que en el servidor: escape, citas, fuentes con la frase
marcada. Una fuente que ya no existe detiene todo en vez de correr la numeración de las citas.
"""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from string import Template

from rag_local.evaluar import cargar_preguntas
from rag_local.indice import cargar_documentos, es_obsoleto, trocear_documentos
from rag_local.resaltar import marcar
from rag_local.web import AREAS, area, markdown_html, respuesta

RAIZ = Path(__file__).resolve().parents[1]
REPO = "https://github.com/vewachholtz-ops/rag-documentos-local"
URL = "https://vewachholtz-ops.github.io/rag-documentos-local/"  # para la vista previa del enlace (og:url, og:image)
DESCRIPCION = (
    "Las respuestas reales del motor de Tesela, un RAG local con Ollama, en una evaluación con {total} preguntas "
    "sobre los procedimientos de una mina ficticia, con la fuente de cada una a la vista."
)
TRAMPAS = "No están en los documentos"
# Los ejemplos de la pantalla de inicio: una pregunta coloquial, un monto que está en una tabla y una pregunta
# cuya respuesta no está en los documentos. El error conocido (p72) va aparte, como enlace.
DESTACADAS = {
    "p22": "Dicha con otras palabras",
    "p47": "La respuesta está en una tabla",
    "p32": "No está en los documentos",
}
# Íconos de 24 por 24 con trazo, en un solo <svg> de símbolos que usan la página y app.js.
ICONOS = {
    "cerrar": '<path d="M6 6l12 12M18 6 6 18"/>',
    "codigo": '<path d="m8 7-5 5 5 5M16 7l5 5-5 5"/>',
    "libro": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 '
    '23H20v-5"/>',
    "nueva": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "grafico": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "marca": '<path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z"/>'
    '<path d="M14 3v5h5M8.5 12.5h7M8.5 16h4"/>',
    "enviar": '<path d="M12 19V5M5.5 11.5 12 5l6.5 6.5"/>',
    "doc": '<path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z"/>'
    '<path d="M14 3v5h5"/>',
    "ok": '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.8 2.8L16.5 9.5"/>',
    "mal": '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    "alerta": '<path d="M12 3.5 21.5 20h-19L12 3.5z"/><path d="M12 10v4.5M12 17.2v.1"/>',
    "neutro": '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
    # comillas: la cita se encontró textual en la fuente (no dice nada sobre si la conclusión es correcta)
    "literal": '<path d="M9.5 7H6a1 1 0 0 0-1 1v3.5a1 1 0 0 0 1 1h3v.5c0 1.7-1 3-2.5 3.5"/>'
    '<path d="M18.5 7H15a1 1 0 0 0-1 1v3.5a1 1 0 0 0 1 1h3v.5c0 1.7-1 3-2.5 3.5"/>',
    "cargando": '<path d="M21 12a9 9 0 1 1-6.2-8.6"/>',
    "reloj": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "abrir": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "volver": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "buscar": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
}


def simbolos() -> str:
    cuerpo = "".join(
        f'<symbol id="i-{nombre}" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{trazo}</g></symbol>'
        for nombre, trazo in ICONOS.items()
    )
    return f'<svg width="0" height="0" style="position:absolute" aria-hidden="true">{cuerpo}</svg>'


def icono(nombre: str) -> str:
    if nombre not in ICONOS:
        raise KeyError(nombre)
    return f'<svg aria-hidden="true"><use href="#i-{nombre}"/></svg>'


def lo_esperado(pregunta: dict) -> str:
    if pregunta.get("fuente") is None:
        return "Debía decir que no está en los documentos."
    partes = [
        f"«{x}»" if isinstance(x, str) else " o ".join(f"«{y}»" for y in x) for x in pregunta.get("debe_contener", [])
    ]
    return "Debía mencionar " + " y ".join(partes) + "."


def porcentaje(x: float) -> str:
    return f"{100 * x:.0f}\u00a0%"


def cifras(v1: dict, v2: dict, primero_v1: float, primero_v2: float) -> str:
    filas = [
        (f"{v2['con_respuesta_correctas']} de {v2['con_respuesta_total']}", "respuestas correctas",
         f"versión inicial: {v1['con_respuesta_correctas']}"),
        (f"{v2['trampa_rechazadas']} de {v2['trampa_total']}", "trampas rechazadas",
         f"versión inicial: {v1['trampa_rechazadas']}"),
        (porcentaje(primero_v2), "con la sección correcta en primer lugar",
         f"versión inicial: {porcentaje(primero_v1)}"),
        (f"{v2['segundos_promedio']:.0f}\u00a0s", "por respuesta en un portátil",
         f"versión inicial: {v1['segundos_promedio']:.0f}\u00a0s"),
    ]  # fmt: skip
    return "".join(
        f'<div class="cifra"><strong>{escape(valor)}</strong><span>{escape(texto)}</span>'
        f"<small>{escape(antes)}</small></div>"
        for valor, texto, antes in filas
    )


def barras(busqueda: dict, mejor: str) -> str:
    filas = []
    for nombre, valores in busqueda.items():
        clase = "barra v2" if nombre == mejor else "barra"
        valor = valores["acierto@1"]
        filas.append(
            f'<div class="{clase}"><span>{escape(nombre)}</span>'
            f'<i style="width: {100 * valor:.1f}%"></i><b>{porcentaje(valor)}</b></div>'
        )
    return f'<div class="barras">{"".join(filas)}</div>'


def documentos() -> tuple[list[dict], dict[str, str]]:
    """Los procedimientos para el panel de fuentes, y de cada título vigente, su archivo."""
    lista, por_titulo = [], {}
    for archivo, md in cargar_documentos(RAIZ / "documentos", incluir_obsoletos=True).items():
        encabezado = next((linea[2:].strip() for linea in md.splitlines() if linea.startswith("# ")), archivo)
        codigo, _, titulo = encabezado.partition(" ")
        obsoleto = es_obsoleto(md)
        if not obsoleto:
            por_titulo[encabezado] = archivo
        lista.append(
            {
                "archivo": archivo,
                "codigo": codigo,
                "titulo": titulo,
                "area": area(codigo),
                "obsoleto": obsoleto,
                "html": markdown_html(marcar(md, [])),
            }
        )
    return lista, por_titulo


def datos() -> dict:
    evaluacion = json.loads((RAIZ / "resultados/evaluacion.json").read_text(encoding="utf-8"))
    preguntas = cargar_preguntas(RAIZ / "evaluacion/preguntas.json")
    trozos = {t.titulo: t for t in trocear_documentos(cargar_documentos(RAIZ / "documentos"))}
    docs, por_titulo = documentos()
    # Una sección sin frases marcadas es igual en todas las respuestas que la usan: se guarda una vez.
    secciones: dict[str, str] = {}
    respuestas: dict[str, dict] = {}
    for version in ("v2", "v1"):
        detalle = {f["id"]: f for f in evaluacion["respuestas"][version]["detalle"]}
        if set(detalle) != {p["id"] for p in preguntas}:
            raise ValueError("Preguntas y evaluación no corresponden; actualizar antes de exportar.")
        respuestas[version] = {}
        for p in preguntas:
            fila = detalle[p["id"]]
            try:
                r = respuesta(fila["respuesta"], fila["fuentes"], trozos, fila.get("problemas") or [])
            except ValueError as error:
                raise ValueError(f"{p['id']} ({version}): {error}") from None
            for fuente, titulo in zip(r["fuentes"], fila["fuentes"], strict=True):
                fuente["archivo"] = por_titulo.get(fuente["documento"])
                if not any(f["n"] == fuente["n"] for f in r["frases"]):
                    secciones.setdefault(titulo, fuente["html"])
                    fuente["seccion_id"] = titulo
                    del fuente["html"]
            r.update(
                correcta=fila["correcta"],
                segundos=round(fila["segundos"]),
                aviso=fila["valida"] and not fila["correcta"] and not r["abstencion"],
            )
            respuestas[version][p["id"]] = r
    return {
        "preguntas": [
            {
                "id": p["id"],
                "texto": p["pregunta"],
                "area": TRAMPAS if p["fuente"] is None else area(p["fuente"]),
                "tipo": p["tipo"],
                "esperado": lo_esperado(p),
            }
            for p in preguntas
        ],
        "areas": [*dict.fromkeys(AREAS.values()), TRAMPAS],
        "destacadas": [{"id": id_, "etiqueta": etiqueta} for id_, etiqueta in DESTACADAS.items()],
        "documentos": docs,
        "secciones": secciones,
        "respuestas": respuestas,
    }


def archivos() -> dict[str, bytes]:
    evaluacion = json.loads((RAIZ / "resultados/evaluacion.json").read_text(encoding="utf-8"))
    v1, v2 = evaluacion["respuestas"]["v1"]["resumen"], evaluacion["respuestas"]["v2"]["resumen"]
    busqueda = evaluacion["busqueda"]
    mejor = evaluacion["respuestas"]["v2"]["busqueda"]
    contenido = datos()
    pagina = Template((RAIZ / "web/plantilla.html").read_text(encoding="utf-8")).substitute(
        simbolos=simbolos(),
        repo=REPO,
        url=URL,
        descripcion=escape(DESCRIPCION.format(total=len(contenido["preguntas"]))),
        configuraciones=len(busqueda),
        total=len(contenido["preguntas"]),
        documentos=len(contenido["documentos"]),
        con_respuesta=v2["con_respuesta_total"],
        trampas=v2["trampa_total"],
        cifras=cifras(v1, v2, busqueda["Híbrido (v1)"]["acierto@1"], busqueda[mejor]["acierto@1"]),
        barras=barras(busqueda, mejor),
        **{f"icono_{nombre}": icono(nombre) for nombre in ICONOS},
    )
    return {
        "index.html": pagina.encode("utf-8"),
        ".nojekyll": b"",
        # La página pregunta por api/estado para saber si hay un modelo; aquí, publicada, la respuesta es que no.
        # El servidor local (`rag servir`) contesta esa ruta antes de llegar a este archivo.
        "api/estado": b'{"vivo": false, "modelo": "", "motivo": ""}\n',
        "style.css": (RAIZ / "web/style.css").read_bytes(),
        "app.js": (RAIZ / "web/app.js").read_bytes(),
        "datos.json": json.dumps(contenido, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "evaluacion.json": (RAIZ / "resultados/evaluacion.json").read_bytes(),
        "assets/geist.woff2": (RAIZ / "static/geist-latin-wght-normal.woff2").read_bytes(),
        "assets/geist-OFL.txt": (RAIZ / "static/geist-OFL.txt").read_bytes(),
        "assets/vista-previa.png": (RAIZ / "docs/vista-previa.png").read_bytes(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Falla si site/ quedó desactualizado.")
    args = parser.parse_args()
    sitio = RAIZ / "site"
    esperados = archivos()
    # site/app/ es la versión web de Tesela: la generan la interfaz (VITE_WEB=1) y scripts/construir_web.py
    sobrantes = sorted(
        f.relative_to(sitio).as_posix()
        for f in sitio.rglob("*")
        if f.is_file()
        and f.relative_to(sitio).as_posix() not in esperados
        and not f.relative_to(sitio).as_posix().startswith("app/")
    )
    if args.check:
        for nombre, contenido in esperados.items():
            destino = sitio / nombre
            if not destino.exists() or destino.read_bytes() != contenido:
                raise SystemExit(f"Sitio desactualizado: {nombre}. Ejecuta python scripts/construir_sitio.py")
        if sobrantes:
            raise SystemExit(f"Sobran archivos en site/: {', '.join(sobrantes)}. Ejecuta el generador.")
        print("Sitio verificado.")
        return
    for nombre in sobrantes:
        (sitio / nombre).unlink()
    for nombre, contenido in esperados.items():
        destino = sitio / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
    print("Sitio generado en site/." + (f" Se borraron {len(sobrantes)} archivos sin uso." if sobrantes else ""))


if __name__ == "__main__":
    main()
