from conftest import resultado

from rag_local.indice import Trozo
from rag_local.responder import (
    MEZCLA,
    NO_ESTA,
    SISTEMA,
    SISTEMA_CON_CITAS,
    Respuesta,
    armar_prompt,
    cifras_con_unidad,
    contradicciones_de_unidad,
    es_abstencion,
    responder,
    separar,
    validar,
)

FRASE = '[1] "Más de USD 50.000 y hasta USD 250.000 | Gerente de operaciones"'


def test_prompt_numera_las_fuentes(tabla_compras, trozos):
    p = armar_prompt("¿Quién aprueba?", [resultado(tabla_compras), resultado(trozos[0])])
    assert p.startswith("Fuentes:\n\n[1] PR-COM-01") and "\n\n[2] " in p and p.endswith("Pregunta: ¿Quién aprueba?")


# ---------------- validación de cifras y citas (v1) ----------------
def test_validar(tabla_compras):
    fuentes = [resultado(tabla_compras)]
    assert validar("Lo aprueba el gerente de operaciones, hasta USD 250.000 [1].", fuentes) == ([1], [])
    _, p = validar("Lo aprueba el gerente de operaciones.", fuentes)
    assert p == ["la respuesta no cita ninguna fuente"]
    _, p = validar("Hasta USD 300.000 [1].", fuentes)
    assert p == ["cifras que no aparecen en las fuentes citadas: ['300000']"]
    _, p = validar("Gerente general [7].", fuentes)
    assert "cita fuentes que no existen: [7]" in p
    assert validar(NO_ESTA, fuentes) == ([], [])


def test_no_esta_en_los_documentos_solo_vale_como_respuesta_completa(tabla_compras):
    fuentes = [resultado(tabla_compras)]
    for texto in [NO_ESTA, "no esta en los documentos", "No está en los\ndocumentos [1]."]:
        assert es_abstencion(texto) and validar(texto, fuentes) == ([], [])
    # Decir que no está y después afirmar algo sin respaldo no puede pasar la validación.
    mezcla = NO_ESTA + " Igual lo aprueba el gerente general, hasta USD 900.000."
    assert not es_abstencion(mezcla)
    _, p = validar(mezcla, fuentes)
    assert MEZCLA in p and "la respuesta no cita ninguna fuente" in p
    assert "cifras que no aparecen en las fuentes citadas: ['900000']" in p
    assert not Respuesta(mezcla, fuentes).sin_respuesta


# ---------------- citas textuales (v2) ----------------
def test_las_cifras_de_la_pregunta_no_cuentan_como_inventadas(tabla_compras):
    f = [resultado(tabla_compras)]
    texto = "Una compra de USD 80.000 la aprueba el gerente de operaciones [1]."
    _, p = validar(texto, f)
    assert p == ["cifras que no aparecen en las fuentes citadas: ['80000']"]
    assert validar(texto, f, pregunta="¿Quién aprueba una compra de USD 80.000?") == ([1], [])
    _, p = validar("Hasta USD 90.000 [1].", f, pregunta="¿Quién aprueba una compra de USD 80.000?")
    assert p == ["cifras que no aparecen en las fuentes citadas: ['90000']"]


def test_la_linea_de_frase_cuenta_como_cita(tabla_compras):
    f = [resultado(tabla_compras)]
    assert validar(f"Lo aprueba el gerente de operaciones.\n\n{FRASE}", f, citas_textuales=True) == ([1], [])


def test_separar_cuerpo_y_frases():
    cuerpo, frases = separar('El gerente de operaciones [1].\n\n[1] "Gerente de operaciones"\n- [2]: “otra frase”')
    assert cuerpo == "El gerente de operaciones [1]." and frases == [(1, "Gerente de operaciones"), (2, "otra frase")]


def test_validar_frases_textuales(tabla_compras):
    f = [resultado(tabla_compras)]
    ok = f"Lo aprueba el gerente de operaciones [1].\n\n{FRASE}"
    assert validar(ok, f, citas_textuales=True) == ([1], [])
    # gpt-oss escribe los miles con espacio fino; la frase igual se reconoce
    assert validar(ok.replace("50.000", "50\u202f000"), f, citas_textuales=True) == ([1], [])
    _, p = validar("Lo aprueba el gerente de operaciones [1].", f, citas_textuales=True)
    assert p == ["faltan las frases textuales de las fuentes [1]"]
    _, p = validar(
        'Lo aprueba el gerente general [1].\n\n[1] "Más de USD 80.000 lo aprueba el gerente general"', f, True
    )
    assert len(p) == 1 and "no está textual en la fuente 1" in p[0]
    _, p = validar('Lo aprueba el gerente de operaciones [1].\n\n[1] "Gerente"', f, True)
    assert "demasiado corta" in p[0]
    # con puntos suspensivos, cada parte tiene que estar en la fuente
    partes = 'El gerente de operaciones [1].\n\n[1] "Más de USD 50.000 … Gerente de operaciones"'
    assert validar(partes, f, citas_textuales=True) == ([1], [])
    assert validar(NO_ESTA, f, citas_textuales=True) == ([], [])


def test_la_frase_no_cuenta_como_respuesta(tabla_compras):
    r = Respuesta(f"No sé quién [1].\n\n{FRASE}", [resultado(tabla_compras)])
    assert r.cuerpo == "No sé quién [1]." and r.textuales == [(1, FRASE[5:-1])]
    assert not r.sin_respuesta


def test_responder_reintenta_si_la_respuesta_no_pasa(tabla_compras):
    llamadas = []

    def chat(sistema, usuario):
        llamadas.append((sistema, usuario))
        return "Hasta USD 999.999." if len(llamadas) == 1 else f"El gerente de operaciones [1].\n\n{FRASE}"

    r = responder("¿Quién aprueba?", [resultado(tabla_compras)], chat)
    assert len(llamadas) == 2 and "Corrígela" in llamadas[1][1] and llamadas[0][0] == SISTEMA_CON_CITAS
    assert r.valida and r.citas == [1] and r.cuerpo == "El gerente de operaciones [1]."


def test_responder_sin_citas_textuales_usa_el_prompt_de_la_v1(tabla_compras):
    vistos = []
    r = responder(
        "x", [resultado(tabla_compras)], lambda s, u: vistos.append(s) or "Gerente [1].", citas_textuales=False
    )
    assert vistos == [SISTEMA] and r.valida


# ---------------- unidades de las cifras (experimento posterior a la evaluación) ----------------
TOLERANCIA = "Una pauta se puede atrasar como máximo un 10 % de su intervalo (la PM2 entre las 450 y las 550 horas)."


def test_marca_una_cifra_que_en_la_fuente_tiene_otra_unidad():
    # el error real de la v2 en p09: la fuente dice 10 %, la respuesta dice 10 horas
    assert contradicciones_de_unidad("Hasta 10 horas [1].", TOLERANCIA) == [
        "la cifra 10 horas aparece en la fuente como 10 %"
    ]
    assert contradicciones_de_unidad("Hasta USD 300.000 [1].", "un fondo fijo de CLP 300.000") == [
        "la cifra 300000 USD aparece en la fuente como 300000 CLP"
    ]


def test_no_marca_lo_que_no_es_una_contradiccion_clara():
    assert contradicciones_de_unidad("Hasta las 550 horas [1].", TOLERANCIA) == []  # misma unidad
    assert contradicciones_de_unidad("Entre 450 horas [1].", TOLERANCIA) == []  # en la fuente va sin unidad
    assert contradicciones_de_unidad("Un 10 [1].", TOLERANCIA) == []  # la respuesta no dice unidad
    assert contradicciones_de_unidad("En 30 días [1].", TOLERANCIA) == []  # la cifra no está: otra revisión
    assert cifras_con_unidad("USD 150.000 y 24 meses") == [("150000", "USD"), ("24", "meses")]


def test_la_comprobacion_de_unidades_es_opcional_y_pide_corregir(tabla_compras):
    fuente = Trozo("x#1", "x.md", "PR-MAN-02 Mantención > Tolerancia", TOLERANCIA)
    texto = 'Hasta 10 horas [1].\n\n[1] "como máximo un 10 % de su intervalo"'
    assert validar(texto, [resultado(fuente)], True) == ([1], [])  # la validación de la evaluación no cambia
    _, problemas = validar(texto, [resultado(fuente)], True, unidades=True)
    assert problemas == ["la cifra 10 horas aparece en la fuente como 10 %"]
    pedidos = []

    def chat(sistema, usuario):
        pedidos.append(usuario)
        if "aparece en la fuente como 10 %" in usuario:
            return 'Hasta las 550 horas [1].\n\n[1] "la PM2 entre las 450 y las 550 horas"'
        return texto

    r = responder("¿Hasta cuántas horas puedo atrasar la PM2?", [resultado(fuente)], chat, unidades=True)
    assert len(pedidos) == 2 and r.valida and "550 horas" in r.cuerpo
