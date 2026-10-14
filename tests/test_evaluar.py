import json
from collections import Counter

import pytest
from conftest import RAIZ, embedder_falso, resultado

from rag_local.busqueda import SISTEMA_REESCRIBIR, SISTEMA_REORDENAR, Busqueda
from rag_local.contexto import SISTEMA as SISTEMA_CONTEXTO
from rag_local.evaluar import (
    cargar_preguntas,
    contiene,
    contiene_alguno,
    es_correcta,
    es_respuesta_correcta,
    evaluar_busqueda,
    evaluar_respuestas,
    repuntuar,
)
from rag_local.experimentos import CONFIGS, Modelos, correr, informe
from rag_local.fidelidad import CASOS_CALIBRACION, calibrar, juzgar, leer_afirmaciones
from rag_local.responder import NO_ESTA

PREGUNTAS = cargar_preguntas(RAIZ / "evaluacion" / "preguntas.json")
TIPOS = {"directa", "coloquial", "parecida", "versión", "trampa", "trampa casi"}


# ---------------- preguntas ----------------
def test_preguntas_de_evaluacion_bien_formadas():
    docs = {p.name for p in (RAIZ / "documentos").glob("PR-*.md")}
    assert len({p["id"] for p in PREGUNTAS}) == len(PREGUNTAS) == 74
    for p in PREGUNTAS:
        assert p["tipo"] in TIPOS, p["id"]
        if p["fuente"] is None:
            assert p["tipo"].startswith("trampa") and p["seccion"] is None and p["debe_contener"] == []
            todos = " ".join(d.read_text(encoding="utf-8") for d in (RAIZ / "documentos").glob("PR-*.md"))
            assert all(contiene_alguno(todos, x) for x in p.get("tambien_contiene", [])), p["id"]
            continue
        assert p["fuente"] in docs and "-v4-" not in p["fuente"], p["id"]  # la fuente correcta es la vigente
        texto = (RAIZ / "documentos" / p["fuente"]).read_text(encoding="utf-8")
        seccion = texto.split(f"\n## {p['seccion']}\n")[1].split("\n## ")[0]  # la sección existe
        assert all(contiene_alguno(seccion, x) for x in p["debe_contener"]), p["id"]  # y contiene el dato


def test_la_version_obsoleta_da_otras_respuestas():
    obsoleta = (RAIZ / "documentos" / "PR-COM-01-v4-solicitud-de-compra.md").read_text(encoding="utf-8")
    vigente = (RAIZ / "documentos" / "PR-COM-01-solicitud-de-compra.md").read_text(encoding="utf-8")
    assert "| Más de USD 100.000 | Gerente general |" in obsoleta  # p47: USD 150.000
    assert "| Más de USD 50.000 y hasta USD 250.000 | Gerente de operaciones |" in vigente
    assert "| Más de USD 25.000 y hasta USD 100.000 | Gerente de operaciones |" in obsoleta  # p48: USD 30.000
    assert (
        "más de USD 5.000: se piden al menos dos" in obsoleta and "más de USD 10.000: se piden al menos tres" in vigente
    )
    assert "USD 20.000" in obsoleta and "72 horas" in obsoleta and "USD 30.000" in vigente and "48 horas" in vigente
    assert {p["id"] for p in PREGUNTAS if p["tipo"] == "versión"} == {"p02", "p03", "p47", "p48", "p49"}


# ---------------- puntaje ----------------
def test_puntaje_acepta_otras_formas_de_escribir_cifras():
    assert contiene("Hasta USD 30\u202f000 [1], en 48 horas [1].", "30.000")
    assert contiene("La meta es 88% [1].", "88 %")
    assert contiene("Se multiplica por √(L+R) [1].", "√(L + R)")
    assert contiene("Lo aprueba el Gerente de Operaciones [1].", "gerente de operaciones")
    assert not contiene("Hasta USD 300.000 [1].", "30.000")


def test_respuesta_correcta_con_formas_alternativas():
    p = {"fuente": "x.md", "debe_contener": [["550", "50 horas"], "PM2"]}
    assert es_respuesta_correcta("La PM2 se puede atrasar hasta 50 horas [1].", False, p)
    assert es_respuesta_correcta("La PM2 hasta las 550 horas [1].", False, p)
    assert not es_respuesta_correcta("La PM2 hasta las 500 horas [1].", False, p)
    assert not es_respuesta_correcta("No está en los documentos.", True, p)
    trampa = {"fuente": None, "debe_contener": [], "tambien_contiene": ["PR-EXP-01"]}
    assert es_respuesta_correcta("No está en los documentos.", True, trampa)
    assert es_respuesta_correcta("Está en el procedimiento PR-EXP-01 [2].", False, trampa)
    assert not es_respuesta_correcta("Lo recibe el jefe de bodega [1].", False, trampa)
    assert not es_respuesta_correcta("Lo recibe el jefe [1].", False, {"fuente": None, "debe_contener": []})


def test_es_correcta_por_seccion(tabla_compras, trozos):
    p = {"fuente": tabla_compras.documento, "seccion": "Niveles de aprobación"}
    otra = next(t for t in trozos if t.documento == tabla_compras.documento and t.seccion == "Cotizaciones")
    assert es_correcta(resultado(tabla_compras), p) and not es_correcta(resultado(otra), p)


# ---------------- búsqueda ----------------
def test_evaluar_busqueda_por_seccion(indice):
    r = evaluar_busqueda(indice, PREGUNTAS, embedder_falso, Busqueda("bm25"))
    assert {"acierto@1", "acierto@3", "acierto@5", "mrr@5", "acierto_documento@4", "fallas"} <= set(r)
    assert 0 < r["acierto@1"] <= r["acierto@3"] <= r["acierto@5"] <= 1
    assert r["acierto@1"] <= r["mrr@5"] <= r["acierto@5"]
    assert set(r["acierto@5_por_tipo"]) == TIPOS - {"trampa", "trampa casi"}


# ---------------- respuestas ----------------
def test_evaluacion_de_respuestas_con_modelos_simulados(indice):
    preguntas = [
        {"id": "a", "tipo": "directa", "pregunta": "¿De qué color son los candados personales?",
         "fuente": "PR-SEG-03-bloqueo-y-etiquetado.md", "seccion": "Reglas básicas", "debe_contener": ["rojo"]},
        {"id": "b", "tipo": "trampa", "pregunta": "¿Cuántos días de vacaciones hay?", "fuente": None,
         "seccion": None, "debe_contener": []},
    ]  # fmt: skip

    def chat(sistema, usuario):
        if "candados" not in usuario.split("Pregunta:")[1]:
            return NO_ESTA
        fuentes = usuario.split("Pregunta:")[0]
        n = next(i for i in range(1, 5) if "rojos" in fuentes.split(f"[{i}] ")[1].split("\n\n[")[0])
        return f'Son rojos [{n}].\n\n[{n}] "Los candados personales son rojos"'

    def juez(sistema, usuario):
        return '{"afirmaciones": [{"texto": "Los candados son rojos", "respaldada": 1}]}'

    config = Busqueda("bm25")
    resumen, detalle = evaluar_respuestas(indice, preguntas, embedder_falso, chat, config=config, juez=juez)
    assert resumen["correctas"] == 2 and resumen["trampa_rechazadas"] == 1
    assert resumen["citan_seccion_correcta"] == 1 and resumen["respuestas_que_no_pasan_validacion"] == 0
    assert resumen["fidelidad_promedio"] == 1.0 and "fidelidad" not in detalle[1]  # la abstención no se juzga
    assert json.dumps(detalle, ensure_ascii=False)


def test_el_dato_en_la_frase_textual_no_cuenta_como_respuesta(indice):
    p = [{"id": "a", "tipo": "directa", "pregunta": "¿De qué color son los candados personales?",
          "fuente": "PR-SEG-03-bloqueo-y-etiquetado.md", "seccion": "Reglas básicas",
          "debe_contener": ["rojo"]}]  # fmt: skip
    resumen, _ = evaluar_respuestas(
        indice, p, embedder_falso, lambda s, u: 'No sé el color [1].\n\n[1] "Los candados personales son rojos"'
    )
    assert resumen["correctas"] == 0


def test_trampa_no_cuenta_como_rechazada_si_la_respuesta_inventa(indice):
    preguntas = [{"id": "t", "pregunta": "¿Cuántos días de vacaciones hay?", "fuente": None, "debe_contener": []}]
    resumen, detalle = evaluar_respuestas(indice, preguntas, embedder_falso, lambda s, u: NO_ESTA + " Pero 15 días.")
    assert resumen["trampa_rechazadas"] == 0 and not detalle[0]["valida"]


# ---------------- juez de fidelidad ----------------
def test_leer_afirmaciones_del_juez():
    texto = '```json\n{"afirmaciones": [{"texto": "A", "respaldada": 1}, {"texto": "B", "respaldada": "0"}]}\n```'
    assert leer_afirmaciones(texto) == [("A", 1), ("B", 0)]
    assert leer_afirmaciones("no es json") == [] and leer_afirmaciones("{malo") == []
    assert juzgar("x", ["f"], lambda s, u: texto).puntaje == 0.5
    assert juzgar("x", ["f"], lambda s, u: "nada").puntaje is None


def test_calibrar_cuenta_los_aciertos_del_juez():
    esperado = {r: e for _, r, e in CASOS_CALIBRACION}

    def juez_perfecto(sistema, usuario):
        e = esperado[usuario.split("Respuesta:\n")[1].split("\n\n")[0]]
        votos = [1, 1] if e == 1.0 else [0] if e == 0.0 else [1, 0]
        return json.dumps({"afirmaciones": [{"texto": "a", "respaldada": v} for v in votos]})

    assert calibrar(juez_perfecto)["aciertos"] == len(CASOS_CALIBRACION)
    assert calibrar(lambda s, u: '{"afirmaciones": [{"texto": "a", "respaldada": 1}]}')["aciertos"] == 3


# ---------------- experimento completo con modelos simulados ----------------
def test_experimento_completo_con_modelos_simulados():
    preguntas = [p for p in PREGUNTAS if p["id"] in {"p01", "p03", "p47", "p22", "p30"}]
    llamadas = Counter()

    def aux(sistema, usuario):
        llamadas[sistema] += 1
        if sistema == SISTEMA_CONTEXTO:
            return "Contexto del trozo."
        if sistema == SISTEMA_REESCRIBIR:
            return "repuesto obsoleto\ninventario"
        if sistema == SISTEMA_REORDENAR:
            return "1, 2"
        return '{"afirmaciones": [{"texto": "a", "respaldada": 1}]}'

    m = Modelos(embedder_falso, embedder_falso, lambda s, u: NO_ESTA, aux, {"respuestas": "falso"})
    r = correr(RAIZ / "documentos", preguntas, m, avance=lambda s: None)
    assert set(r["busqueda"]) == {c[0] for c in CONFIGS}
    assert r["busqueda"]["Híbrido sin descartar obsoletos"]["version_con_obsoleto_primero"].endswith("/2")
    assert r["respuestas"]["v2"]["busqueda"] not in {"BM25", "Vectores", "Híbrido sin descartar obsoletos"}
    assert r["respuestas"]["v1"]["resumen"]["trampa_rechazadas"] == 1
    assert llamadas[SISTEMA_CONTEXTO] == len(r["indices"]["contexto"].trozos)
    md = informe(r)
    assert "| Híbrido (v1) |" in md and "### Respuestas" in md and "casos de calibración" in md


@pytest.mark.parametrize("config", [c[0] for c in CONFIGS])
def test_configuraciones_con_nombre_unico(config):
    assert [c[0] for c in CONFIGS].count(config) == 1


def test_guiones_tipograficos_no_cambian_el_puntaje():
    assert contiene("Está en PR\u2011EXP\u201101 [2].", "PR-EXP-01")


def test_repuntuar_sin_modelo():
    preguntas = [
        {"id": "a", "tipo": "trampa", "pregunta": "x", "fuente": None, "seccion": None, "debe_contener": [],
         "tambien_contiene": ["PR-EXP-01"]},
        {"id": "b", "tipo": "directa", "pregunta": "y", "fuente": "f.md", "seccion": "S",
         "debe_contener": [["550", "50 horas"]]},
    ]  # fmt: skip
    respuestas = {
        "v1": {"detalle": [
            {"id": "a", "tipo": "trampa", "respuesta": "En PR\u2011EXP\u201101 [2].", "correcta": False, "valida": True,
             "cita_seccion_correcta": True, "segundos": 1.0},
            {"id": "b", "tipo": "directa", "respuesta": "Hasta 50 horas [1].", "correcta": False, "valida": True,
             "cita_seccion_correcta": True, "segundos": 3.0},
        ]}
    }  # fmt: skip
    r = repuntuar(respuestas, preguntas)["v1"]["resumen"]
    assert r["trampa_rechazadas"] == 1 and r["con_respuesta_correctas"] == 1 and r["segundos_promedio"] == 2.0


def test_experimento_de_unidades_sin_modelo_revisa_lo_guardado():
    from rag_local.experimentos import experimento_unidades, informe_unidades

    previa = {"respuestas": {v: {"busqueda": "Híbrido (v1)", "resumen": {}, "detalle": [
        {"id": "a", "respuesta": 'Hasta 10 horas [1].\n\n[1] "un 10 % de su intervalo"', "correcta": False,
         "fuentes": ["T > Tolerancia"]},
        {"id": "b", "respuesta": "Hasta las 550 horas [1].", "correcta": True, "fuentes": ["T > Tolerancia"]},
    ]} for v in ("v1", "v2")}}  # fmt: skip
    preguntas = [{"id": "a", "pregunta": "¿Cuántas horas?"}, {"id": "b", "pregunta": "¿Hasta qué hora?"}]
    textos = {"T > Tolerancia": "un 10 % de su intervalo, entre las 450 y las 550 horas"}
    r = experimento_unidades(previa, preguntas, textos, None, None)
    assert [m["id"] for m in r["sin_modelo"]["v2"]] == ["a"] and "con_modelo" not in r
    texto = informe_unidades(r, previa)
    assert "marca 1 de 2 respuestas: 1 de sus 1 incorrectas y 0 correctas" in texto
