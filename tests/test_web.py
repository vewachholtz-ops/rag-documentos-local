"""Lo que la página muestra de una respuesta: escapada, con citas que se pueden pulsar y la frase marcada."""

import pytest

from rag_local.indice import Trozo
from rag_local.web import area, estado, markdown_html, respuesta, respuesta_html

TABLA = "| Cargo | Monto |\n|---|---|\n| Jefe de área | **500** |"


def trozo(titulo: str, texto: str) -> Trozo:
    return Trozo(titulo, "doc.md", titulo, texto)


def test_area_por_el_codigo_del_procedimiento():
    assert area("PR-RRHH-02 Turnos") == "Personas y turnos"
    assert area("PR-FIN-01-fondos.md") == "Compras y gastos"
    assert area("OTRO-01") == "Otros"


def test_markdown_de_los_procedimientos():
    html = markdown_html("# Título\n\nUn párrafo\nque sigue.\n\n- uno\n- **dos**\n\n1. primero\n\n" + TABLA)
    assert "<h3>Título</h3>" in html and "<p>Un párrafo que sigue.</p>" in html
    assert "<ul><li>uno</li><li><strong>dos</strong></li></ul>" in html and "<ol><li>primero</li></ol>" in html
    assert '<div class="tabla"><table><thead><tr><th>Cargo</th>' in html and "<td><strong>500</strong></td>" in html


def test_un_titulo_con_sangria_no_traba_el_lector():
    # antes, «   ## Apartado» no calzaba con ningún caso y el ciclo no avanzaba
    html = markdown_html("Texto\n   ## Apartado\n   sigue")
    assert "<h4>Apartado</h4>" in html and "<p>sigue</p>" in html


def test_la_respuesta_se_escapa_y_las_citas_se_pueden_pulsar():
    html = respuesta_html("<b>Hola</b> [1]\n\nOtro párrafo [2].")
    assert "<b>" not in html and "&lt;b&gt;" in html
    assert '<button type="button" class="cita" data-n="1">1</button>' in html
    assert html.count("<p>") == 2


def test_estado_dice_exactamente_lo_que_se_comprobo():
    alerta = estado("Dato [1].", ["la cifra 9 no está en [1]"], False)
    assert alerta["tipo"] == "alerta" and "la cifra 9" in alerta["detalle"]
    assert estado("No está en los documentos.", [], False)["tipo"] == "neutro"
    con_frases = estado("Dato [1].", [], True)
    assert con_frases["tipo"] == "literal" and "textuales" in con_frases["texto"]
    # no promete más de lo que hace responder.validar: cifras de dos dígitos o más, y pueden venir de la pregunta
    assert "dos o más dígitos" in con_frases["detalle"] and "o en la pregunta" in con_frases["detalle"]
    assert "No se comprueba que la conclusión sea correcta." in con_frases["detalle"]
    assert "comprobad" not in con_frases["texto"].lower()


def test_respuesta_completa_con_fuente_citada_marcada_y_otra_sin_citar():
    texto = 'El jefe aprueba hasta 500 [1].\n\n[1] "Jefe de área | 500"'
    trozos = {"A > Montos": trozo("A > Montos", TABLA), "B > Otra": trozo("B > Otra", "Nada <script>")}
    r = respuesta(texto, ["A > Montos", "B > Otra"], trozos, [])
    assert [f["citada"] for f in r["fuentes"]] == [True, False]
    assert r["fuentes"][0]["seccion"] == "Montos" and r["fuentes"][0]["documento"] == "A"
    assert "<mark>" in r["fuentes"][0]["html"] and "<script>" not in r["fuentes"][1]["html"]
    assert r["frases"] == [{"n": 1, "texto": "Jefe de área | 500"}]
    assert "Jefe de área" not in r["html"] and r["estado"]["tipo"] == "literal" and not r["abstencion"]


def test_una_fuente_citada_solo_con_la_frase_copiada_igual_lleva_su_numero():
    r = respuesta(
        'El gerente aprueba.\n\n[1] "Jefe de área"', ["A > Montos"], {"A > Montos": trozo("A > Montos", TABLA)}, []
    )
    assert r["html"].endswith('aprueba. <button type="button" class="cita" data-n="1">1</button></p>')


def test_una_fuente_ausente_detiene_todo():
    with pytest.raises(ValueError, match="No renumerar"):
        respuesta("Dato [2].", ["ya no existe", "B"], {"B": trozo("B", "x")}, [])
