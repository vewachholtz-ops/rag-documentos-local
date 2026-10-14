"""Estudio: leer por partes, tomar notas una sola vez, condensar, escribir y revisar las cifras."""

import pytest
from ollama_falso import responder_chat

from rag_local import estudio
from rag_local.estudio import Fuente, Medidas
from rag_local.web import markdown_nota

CHICAS = Medidas(ventana=200, material=300, partes=36, corta=80)


def contador():
    llamadas = []

    def chat(sistema, usuario):
        llamadas.append(sistema)
        return responder_chat(sistema, usuario)

    return chat, llamadas


def largo(n: int) -> str:
    return "\n\n".join(
        f"## Paso {i}\n\nEl paso {i} revisa el equipo número {i} con cuidado y lo anota." for i in range(n)
    )


def test_partir_respeta_parrafos_y_corta_los_enormes():
    partes = estudio.partir("uno dos\n\ntres cuatro\n\n" + "palabra " * 40, 60)
    assert partes[0] == "uno dos\n\ntres cuatro" and all(len(p) <= 60 for p in partes)
    assert " ".join(" ".join(partes).split()) == " ".join(("uno dos tres cuatro " + "palabra " * 40).split())


def test_elegir_reparte_parejo():
    assert estudio.elegir(10, 3) == [0, 4, 9] and estudio.elegir(3, 5) == [0, 1, 2] and estudio.elegir(10, 1) == [0]


def test_si_cabe_entra_tal_cual_sin_llamar_al_modelo():
    chat, llamadas = contador()
    texto, leido = estudio.material([Fuente("a", "a.md", "Texto corto.")], chat, "m", CHICAS)
    assert texto == "## Fuente: a.md\n\nTexto corto." and leido == 1 and llamadas == []


def test_un_documento_largo_se_lee_por_partes_una_sola_vez():
    chat, llamadas = contador()
    fuente = Fuente("a", "manual.md", largo(8))
    avisos = []
    texto, leido = estudio.material(
        [fuente, Fuente("b", "corta.md", "Una nota corta.")], chat, "m", CHICAS, avisos.append
    )
    n = len(estudio.partir(fuente.texto, CHICAS.ventana))
    assert llamadas.count(estudio.SISTEMA_NOTAS) == n and len(fuente.notas) == n and leido == 1
    assert avisos[0] == f"Leyendo «manual.md» (parte 1 de {n})"
    assert len(texto) <= CHICAS.material and "## Fuente:" in texto
    llamadas.clear()
    estudio.material([fuente], chat, "m", CHICAS)
    assert estudio.SISTEMA_NOTAS not in llamadas  # las notas guardadas sirven
    estudio.material([fuente], chat, "otro-modelo", CHICAS)
    assert llamadas.count(estudio.SISTEMA_NOTAS) == n  # con otro modelo, se vuelve a leer


def test_con_demasiadas_partes_lee_una_muestra_de_todo_el_documento():
    chat, llamadas = contador()
    pocas = Medidas(ventana=200, material=300, partes=4, corta=80)
    fuente = Fuente("a", "manual.md", largo(40))
    _, leido = estudio.material([fuente], chat, "m", pocas)
    assert llamadas.count(estudio.SISTEMA_NOTAS) == 4 and 0 < leido < 0.5


def test_sin_texto_no_hay_material():
    with pytest.raises(estudio.SinMaterial):
        estudio.material([Fuente("a", "a.md", "  ")], responder_chat, "m", CHICAS)


def test_escribir_separa_el_titulo_y_limpia_el_bloque_de_codigo():
    def chat(_s, _u):
        return "```markdown\n# Guía de compras\n\n## Conceptos clave\n\n- **Orden**: el pedido.\n```"

    titulo, contenido = estudio.escribir("guia", "material", chat)
    assert titulo == "Guía de compras" and contenido.startswith("## Conceptos clave")
    assert estudio.escribir("resumen", "m", lambda _s, _u: "Sin título")[0] == "Resumen"
    with pytest.raises(estudio.SinMaterial):
        estudio.escribir("propia", "m", chat, "  ")


def test_leer_la_guia_acepta_variaciones():
    guia = estudio.leer_guia(
        "**Resumen:** Trata de compras.\nY de plazos.\n\n## Temas clave\n- Compras\n- **Plazos**\n\n"
        "PREGUNTAS:\n1. ¿Quién aprueba?\n2. ¿Cuánto demora, en días, una compra"
    )
    assert guia == {
        "resumen": "Trata de compras. Y de plazos.",
        "temas": ["Compras", "Plazos"],
        "preguntas": ["¿Quién aprueba?", "¿Cuánto demora, en días, una compra?"],
    }
    assert estudio.leer_guia("RESUMEN: x.\nTEMAS: a, b; c")["temas"] == ["a", "b", "c"]
    assert estudio.leer_guia("Un texto sin encabezados.")["resumen"] == "Un texto sin encabezados."


def test_las_cifras_que_no_estan_en_las_fuentes_se_avisan():
    contenido = "# 10. Plazos\n1. Son USD 30.000 y 45 días.\n10. En 2024 cambió.\n**12.** otra"
    assert estudio.cifras_sin_respaldo(contenido, ["Sobre 30 000 dólares, desde 2024."]) == ["45"]


def test_markdown_de_las_notas():
    html = markdown_nota(
        "# Título\n\nUn párrafo\nsigue **fuerte**, *suave*, `x<y` y [enlace](https://x.cl/?a=1&b=2).\n\n"
        "- uno\n  - uno.a\n- dos\n\n3. tres\n4. cuatro\n\n> cita\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "[malo](javascript:alert(1)) <script>x</script>"
    )
    assert "<h2>Título</h2>" in html and "<p>Un párrafo<br>sigue <strong>fuerte</strong>, <em>suave</em>" in html
    assert "<code>x&lt;y</code>" in html and 'href="https://x.cl/?a=1&amp;b=2"' in html
    assert "<ul><li>uno<ul><li>uno.a</li></ul></li><li>dos</li></ul>" in html and '<ol start="3">' in html
    assert "<blockquote><p>cita</p></blockquote>" in html and "<td>1</td>" in html
    assert "javascript:" not in html.replace("[malo](javascript:alert(1))", "") and "<script>" not in html
