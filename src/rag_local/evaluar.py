"""Evaluación con preguntas de respuesta conocida.

Búsqueda (sin modelo de chat, salvo que la configuración reescriba o reordene): ¿está la sección correcta
entre los k trozos recuperados? Se mide acierto@1, @3 y @5 y MRR por sección, como Pass@k en el cookbook de
Anthropic y recall@k en haystack o haiku.rag, y también acierto@4 por documento, la medida de la v1.

Respuesta (necesita Ollama): ¿la respuesta contiene el dato esperado, cita la sección correcta y pasa la
validación? En las preguntas trampa, ¿dice que no está en los documentos? Opcionalmente, fidelidad con un
juez (ver fidelidad.py).
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path

from .busqueda import Busqueda, buscar
from .fidelidad import juzgar
from .indice import Embedder, Indice, Resultado
from .responder import Chat, Respuesta, contradicciones_de_unidad, responder, separar

K_SECCION = (1, 3, 5)


def cargar_preguntas(ruta: Path) -> list[dict]:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def es_correcta(r: Resultado, p: dict) -> bool:
    """El trozo es de la sección correcta (o del documento correcto, si la pregunta no indica sección)."""
    return r.trozo.documento == p["fuente"] and (not p.get("seccion") or r.trozo.seccion == p["seccion"])


def evaluar_busqueda(
    indice: Indice,
    preguntas: list[dict],
    embedder: Embedder | None,
    config: Busqueda | None = None,
    chat: Chat | None = None,
    ks: tuple[int, ...] = K_SECCION,
    avance: Callable[[str], None] | None = None,
) -> dict:
    config = config or Busqueda()
    con_fuente = [p for p in preguntas if p["fuente"]]
    kmax = max(*ks, 4)
    aciertos, doc4, rr, fallas, por_tipo = dict.fromkeys(ks, 0), 0, 0.0, [], {}
    for i, p in enumerate(con_fuente, 1):
        res = buscar(indice, p["pregunta"], kmax, embedder, config, chat)
        rango = next((j for j, r in enumerate(res) if es_correcta(r, p)), None)
        for k in ks:
            aciertos[k] += rango is not None and rango < k
        if rango is None:
            fallas.append(p["id"])
        else:
            rr += 1 / (rango + 1)
        doc4 += any(r.trozo.documento == p["fuente"] for r in res[:4])
        t = por_tipo.setdefault(p.get("tipo", "-"), [0, 0])
        t[0] += rango is not None and rango < max(ks)
        t[1] += 1
        if avance:
            avance(f"búsqueda {i}/{len(con_fuente)}")
    n = len(con_fuente)
    return {
        **{f"acierto@{k}": aciertos[k] / n for k in ks},
        f"mrr@{max(ks)}": rr / n,
        "acierto_documento@4": doc4 / n,
        "fallas": fallas,
        f"acierto@{max(ks)}_por_tipo": {t: v[0] / v[1] for t, v in por_tipo.items()},
    }


def evaluar_respuestas(
    indice: Indice,
    preguntas: list[dict],
    embedder: Embedder | None,
    chat: Chat,
    k: int = 4,
    config: Busqueda | None = None,
    chat_aux: Chat | None = None,
    citas_textuales: bool = True,
    juez: Chat | None = None,
    avance: Callable[[str], None] | None = None,
    reloj: Callable[[], float] = time.perf_counter,
    unidades: bool = False,
) -> tuple[dict, list[dict]]:
    """`reloj` mide los segundos por pregunta; con caché, conviene que sume lo que habrían tomado las
    respuestas que salieron de ella, para que el tiempo no se vea más corto de lo que es."""
    detalle = []
    for i, p in enumerate(preguntas, 1):
        t0 = reloj()
        fuentes = buscar(indice, p["pregunta"], k, embedder, config, chat_aux)
        r = responder(p["pregunta"], fuentes, chat, citas_textuales=citas_textuales, unidades=unidades)
        segundos = reloj() - t0
        correcta = es_respuesta_correcta(r.cuerpo, r.sin_respuesta, p)
        citadas = [fuentes[c - 1] for c in r.citas if 1 <= c <= len(fuentes)]
        fila = {
            "id": p["id"],
            "tipo": p.get("tipo"),
            "pregunta": p["pregunta"],
            "respuesta": r.texto,
            "correcta": correcta,
            "valida": r.valida,
            "problemas": r.problemas,
            "cita_seccion_correcta": p["fuente"] is None or any(es_correcta(f, p) for f in citadas),
            "fuentes": [f.trozo.titulo for f in fuentes],
            "segundos": round(segundos, 1),
        }
        if juez is not None and not r.sin_respuesta:
            fila["fidelidad"] = juzgar(r.cuerpo, [f.trozo.texto for f in fuentes], juez).puntaje
        detalle.append(fila)
        if avance:
            avance(f"respuestas {i}/{len(preguntas)}")
    return resumir(detalle, preguntas), detalle


def resumir(detalle: list[dict], preguntas: list[dict]) -> dict:
    con = [d for d, p in zip(detalle, preguntas, strict=True) if p["fuente"]]
    sin = [d for d, p in zip(detalle, preguntas, strict=True) if not p["fuente"]]
    por_tipo: dict[str, list[int]] = {}
    for d in detalle:
        t = por_tipo.setdefault(d["tipo"] or "-", [0, 0])
        t[0] += d["correcta"]
        t[1] += 1
    fidelidades = [d["fidelidad"] for d in detalle if d.get("fidelidad") is not None]
    return {
        "correctas": sum(d["correcta"] for d in detalle),
        "total": len(detalle),
        "con_respuesta_correctas": sum(d["correcta"] for d in con),
        "con_respuesta_total": len(con),
        "trampa_rechazadas": sum(d["correcta"] for d in sin),
        "trampa_total": len(sin),
        "citan_seccion_correcta": sum(d["cita_seccion_correcta"] for d in con),
        "respuestas_que_no_pasan_validacion": sum(not d["valida"] for d in detalle),
        "correctas_por_tipo": {t: f"{v[0]}/{v[1]}" for t, v in por_tipo.items()},
        "fidelidad_promedio": round(sum(fidelidades) / len(fidelidades), 3) if fidelidades else None,
        "segundos_promedio": round(sum(d["segundos"] for d in detalle) / len(detalle), 1),
    }


def repuntuar(respuestas: dict, preguntas: list[dict]) -> dict:
    """Vuelve a puntuar respuestas guardadas (resultados/evaluacion.json) con el puntaje actual, sin llamar al
    modelo: corregir cómo se puntúa no debería obligar a correr todo de nuevo."""
    por_id = {p["id"]: p for p in preguntas}
    for version in respuestas.values():
        orden = [por_id[d["id"]] for d in version["detalle"]]
        for d, p in zip(version["detalle"], orden, strict=True):
            r = Respuesta(d["respuesta"], [])
            d["correcta"] = es_respuesta_correcta(r.cuerpo, r.sin_respuesta, p)
        version["resumen"] = resumir(version["detalle"], orden)
    return respuestas


def es_respuesta_correcta(cuerpo: str, sin_respuesta: bool, p: dict) -> bool:
    """Con fuente: no se abstiene y contiene cada dato esperado (un dato puede ser una lista de formas
    válidas, por ejemplo ["550", "50 horas"]). Trampa: se abstiene o, si la pregunta lo permite, contiene
    lo de "tambien_contiene" (para trampas en que los documentos sí dicen dónde está la respuesta)."""
    if p["fuente"] is None:
        alternativa = p.get("tambien_contiene")
        return sin_respuesta or bool(alternativa and all(contiene_alguno(cuerpo, x) for x in alternativa))
    return not sin_respuesta and all(contiene_alguno(cuerpo, x) for x in p["debe_contener"])


def contiene_alguno(respuesta: str, esperado: str | list[str]) -> bool:
    return any(contiene(respuesta, e) for e in ([esperado] if isinstance(esperado, str) else esperado))


def contiene(respuesta: str, esperado: str) -> bool:
    """¿La respuesta contiene el dato esperado? Sin importar mayúsculas, tildes ni cómo se escriban los miles,
    los porcentajes o los espacios: gpt-oss, por ejemplo, escribe "30 000" con espacio fino donde la fuente
    dice "30.000", y "88%" donde dice "88 %"."""
    r, e = _plano(respuesta), _plano(esperado)
    return _busca(e, r) or _busca(e.replace(" ", ""), r.replace(" ", ""))


def _busca(esperado: str, texto: str) -> bool:
    """Busca el texto esperado sin que una cifra calce dentro de otra más larga (30000 no está en 300000)."""
    patron = re.escape(esperado)
    if esperado[:1].isdigit():
        patron = r"(?<!\d)" + patron
    if esperado[-1:].isdigit():
        patron += r"(?!\d)"
    return re.search(patron, texto) is not None


def _plano(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower().replace("\u202f", " ").replace("\u00a0", " "))
    s = re.sub("[\u2010-\u2015\u2212]", "-", s)  # guiones tipográficos (gpt-oss escribe PR\u2011EXP\u201101)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"(?<=\d)[.\s](?=\d{3}\b)", "", s)  # 30.000 y 30 000 -> 30000
    s = re.sub(r"\s+%", "%", s)  # 88 % -> 88%
    return " ".join(s.split())


def revisar_unidades(detalle: list[dict], preguntas: list[dict], textos: dict[str, str]) -> list[dict]:
    """Sin modelo: qué respuestas guardadas habría marcado la comprobación de unidades (ver
    responder.contradicciones_de_unidad). textos: el texto de cada sección por su título."""
    por_id = {p["id"]: p for p in preguntas}
    marcadas = []
    for fila in detalle:
        cuerpo, textuales = separar(fila["respuesta"])
        citas = {int(c) for c in re.findall(r"\[(\d+)\]", cuerpo)} | {n for n, _ in textuales}
        citadas = [fila["fuentes"][c - 1] for c in sorted(citas) if 1 <= c <= len(fila["fuentes"])]
        evidencia = "\n".join(textos.get(t, "") for t in citadas) + "\n" + por_id[fila["id"]]["pregunta"]
        problemas = contradicciones_de_unidad(cuerpo, evidencia)
        if problemas:
            marcadas.append({"id": fila["id"], "correcta": fila["correcta"], "problemas": problemas})
    return marcadas
