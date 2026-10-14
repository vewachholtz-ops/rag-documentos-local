"""La app publicada: fiel a las corridas guardadas, incluso cuando son incorrectas, y sin nada externo."""

import json
import re
import runpy
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(RAIZ / "scripts/construir_sitio.py"))


@pytest.fixture(scope="module")
def archivos():
    return BUILD["archivos"]()


@pytest.fixture(scope="module")
def datos(archivos):
    return json.loads(archivos["datos.json"])


def test_exporta_las_74_preguntas_en_ambas_versiones_sin_alterar_la_evaluacion(archivos, datos):
    ev = json.loads(archivos["evaluacion.json"])
    assert len(datos["preguntas"]) == 74
    for version in ("v1", "v2"):
        guardadas = {f["id"]: f for f in ev["respuestas"][version]["detalle"]}
        assert set(datos["respuestas"][version]) == set(guardadas)
        for id_, r in datos["respuestas"][version].items():
            assert r["correcta"] == guardadas[id_]["correcta"]
            assert [f["n"] for f in r["fuentes"]] == list(range(1, len(guardadas[id_]["fuentes"]) + 1))
    assert archivos["evaluacion.json"] == (RAIZ / "resultados/evaluacion.json").read_bytes()


def test_una_cita_valida_en_una_respuesta_incorrecta_se_muestra_como_limite_del_validador(datos):
    p72 = datos["respuestas"]["v2"]["p72"]  # trampa: cita una frase real, pero debía abstenerse
    assert not p72["correcta"] and p72["aviso"] and p72["estado"]["tipo"] == "literal"
    assert not datos["respuestas"]["v2"]["p22"]["aviso"]  # correcta: sin aviso


def test_cada_fuente_tiene_su_texto_y_las_frases_citadas_quedan_marcadas(datos):
    for version in ("v1", "v2"):
        for r in datos["respuestas"][version].values():
            numeros = {f["n"] for f in r["frases"]}
            for f in r["fuentes"]:
                texto = f.get("html") or datos["secciones"][f["seccion_id"]]
                assert texto
                if f["n"] in numeros:
                    assert "<mark>" in f["html"]


def test_las_preguntas_de_inicio_y_los_documentos_existen(datos):
    ids = {p["id"] for p in datos["preguntas"]}
    assert {d["id"] for d in datos["destacadas"]} <= ids and all(d["etiqueta"] for d in datos["destacadas"])
    assert len(datos["documentos"]) == 24
    assert [d["codigo"] for d in datos["documentos"] if d["obsoleto"]] == ["PR-COM-01"]
    assert {p["area"] for p in datos["preguntas"]} <= set(datos["areas"])


def test_la_pagina_no_depende_de_servicios_externos(archivos):
    pagina = archivos["index.html"].decode()
    assert not re.search(r'<(script|link)[^>]+(src|href)="https?:', pagina)
    assert "fetch('http" not in archivos["app.js"].decode()
    assert json.loads(archivos["api/estado"]) == {"vivo": False, "modelo": "", "motivo": ""}


def test_lo_que_app_js_busca_existe_en_la_pagina(archivos):
    pagina, app = archivos["index.html"].decode(), archivos["app.js"].decode()
    for id_ in set(re.findall(r"\$\('#([\w-]+)", app)):
        assert f'id="{id_}"' in pagina, id_
    for nombre in set(re.findall(r"icono\('([\w-]+)'", app)):
        assert f'id="i-{nombre}"' in pagina, nombre


def test_una_fuente_ausente_no_puede_desplazar_la_numeracion(monkeypatch):
    original = BUILD["trocear_documentos"]

    def sin_una(documentos):
        trozos = original(documentos)
        return [
            t
            for t in trozos
            if t.titulo != "PR-SEG-03 Bloqueo y etiquetado de energías > Retiro de un candado olvidado"
        ]

    monkeypatch.setitem(BUILD["datos"].__globals__, "trocear_documentos", sin_una)
    with pytest.raises(ValueError, match="No renumerar"):
        BUILD["datos"]()
