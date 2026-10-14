"""La app (la interfaz en React de app/) en un navegador de verdad, Chromium con Playwright, con un Ollama de
mentira.

Se saltan si no hay navegador: `uv run playwright install chromium` las habilita (o la variable RAG_CHROMIUM).
Si fallan porque app/ está desactualizada: `cd interfaz && npm ci && npm run build`.
"""

import os
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from archivos import pdf_simple
from ollama_falso import iniciar
from test_servidor import sitio  # noqa: F401  (el sitio web de mentira)

from rag_local import enlaces, ollama
from rag_local.biblioteca import NO_SE_PUEDE, Biblioteca
from rag_local.servidor import App, crear

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
APP = Path(__file__).resolve().parents[1] / "app"
MD = "# Compras\n\n## Aprobaciones\n\nSobre USD 50.000 aprueba el gerente de operaciones de la faena.\n"
PREGUNTA = "¿Quién aprueba sobre USD 50.000?"


@pytest.fixture(scope="module")
def navegador():
    with sync_api.sync_playwright() as p:
        opciones = {"executable_path": os.environ["RAG_CHROMIUM"]} if os.environ.get("RAG_CHROMIUM") else {}
        try:
            b = p.chromium.launch(**opciones)
        except Exception as error:
            pytest.skip(f"Sin navegador para las pruebas ({error.__class__.__name__}).")
        yield b
        b.close()


@pytest.fixture
def falso(monkeypatch):
    s, estado, url = iniciar(demora=0.02)
    monkeypatch.setattr(ollama, "URL", url)
    yield estado
    s.shutdown()
    s.server_close()


@pytest.fixture
def fuente(tmp_path, falso):
    app = App(Biblioteca(tmp_path / "biblioteca"))
    s = crear(APP, app, 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield SimpleNamespace(url=f"http://127.0.0.1:{s.server_address[1]}/", app=app)
    s.shutdown()
    s.server_close()


@pytest.fixture
def pagina(navegador):
    contexto = navegador.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    pg = contexto.new_page()
    errores = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    yield pg
    contexto.close()
    assert not errores, errores


@pytest.fixture
def archivos(tmp_path):
    (tmp_path / "compras.md").write_text(MD, encoding="utf-8")
    (tmp_path / "bodega.pdf").write_bytes(pdf_simple(["Bodega central", "La bodega abre a las 8 de la manana."]))
    return tmp_path


def abrir_cuaderno(pg, fuente, nombre="Compras"):
    c = fuente.app.cuadernos.crear(nombre)
    pg.goto(f"{fuente.url}#/cuadernos/{c['id']}")
    expect(pg.get_by_role("button", name=re.compile(f"^Nombre del cuaderno: {nombre}"))).to_be_visible()
    return c["id"]


def fuentes(pg):
    return pg.get_by_role("region", name="Fuentes", exact=True)


def chat(pg):
    return pg.get_by_role("region", name="Chat")


def agregar(pg, *rutas):
    pg.set_input_files('[data-prueba="elegir-archivos"]', [str(r) for r in rutas])
    expect(fuentes(pg).locator("article")).to_have_count(len(rutas), timeout=10_000)


def preguntar(pg, texto):
    antes = pg.locator(".prosa:has(.cita), ol:has(> li button .prosa)").count()
    pg.get_by_role("textbox", name="Pregunta").fill(texto)
    pg.keyboard.press("Enter")
    pg.wait_for_function(
        "n => document.querySelectorAll('.prosa:has(.cita), ol:has(> li button .prosa)').length > n", arg=antes
    )


def test_la_primera_vez_invita_a_crear_un_cuaderno(pagina, fuente):
    pagina.goto(fuente.url)
    expect(pagina.get_by_role("heading", name="Pregúntale a tus documentos")).to_be_visible()
    pagina.get_by_role("button", name="Crear el primer cuaderno").click()
    pagina.get_by_label("Nombre").fill("Contratos")
    pagina.get_by_role("button", name="Crear cuaderno").click()
    expect(pagina.get_by_text("Agrega tus documentos")).to_be_visible()
    caja = pagina.get_by_role("textbox", name="Pregunta")
    expect(caja).to_be_disabled()
    expect(caja).to_have_attribute("placeholder", "Agrega una fuente para preguntar")
    assert [c["nombre"] for c in fuente.app.cuadernos.lista()] == ["Contratos"]


def test_agregar_preguntar_y_ver_el_pasaje(pagina, fuente, archivos):
    abrir_cuaderno(pagina, fuente)
    agregar(pagina, archivos / "compras.md", archivos / "bodega.pdf")
    expect(fuentes(pagina)).to_contain_text("PDF · 2 páginas")
    preguntar(pagina, PREGUNTA)
    respuesta = pagina.locator(".prosa:has(.cita)").last
    expect(respuesta).to_contain_text("gerente de operaciones")
    respuesta.locator(".cita").first.click()
    dialogo = pagina.get_by_role("dialog")
    expect(dialogo).to_contain_text("compras.md")
    expect(dialogo.locator("mark").first).to_be_visible()
    pagina.keyboard.press("Escape")
    preguntar(pagina, "¿A qué hora abre la bodega?")
    expect(pagina.get_by_role("list", name="Fuentes citadas").last).to_contain_text("página 2")


def test_guardar_una_respuesta_como_nota(pagina, fuente, archivos):
    abrir_cuaderno(pagina, fuente)
    agregar(pagina, archivos / "compras.md")
    preguntar(pagina, PREGUNTA)
    pagina.get_by_role("button", name="Guardar como nota").click()
    notas = pagina.get_by_role("region", name="Notas")
    expect(notas).to_contain_text(PREGUNTA)
    expect(notas).to_contain_text("Respuesta")
    notas.get_by_role("button", name=f"Abrir la nota {PREGUNTA}").click()
    expect(pagina.get_by_role("dialog")).to_contain_text("[1] compras.md")
    pagina.get_by_role("button", name="Editar").click()
    expect(pagina.get_by_label("Contenido")).to_have_value(re.compile(r"Fuentes:\n\[1\] compras\.md"))


def test_dejar_una_fuente_fuera_del_chat(pagina, fuente, archivos):
    abrir_cuaderno(pagina, fuente)
    agregar(pagina, archivos / "compras.md", archivos / "bodega.pdf")
    expect(chat(pagina)).to_contain_text("Las 2 fuentes entran al chat")
    pagina.get_by_role("button", name="Dejar compras.md fuera del chat").click()
    expect(chat(pagina)).to_contain_text("1 de 2 fuentes entran al chat")
    pagina.get_by_role("button", name="Dejar bodega.pdf fuera del chat").click()
    expect(pagina.get_by_role("textbox", name="Pregunta")).to_be_disabled()


def test_solo_buscar_sin_ia(pagina, fuente, falso, archivos):
    falso.modelos = set()
    pagina.goto(f"{fuente.url}#/ajustes")
    pagina.get_by_label(re.compile("^Solo buscar")).check()
    expect(pagina.get_by_role("link", name=re.compile("Solo buscar"))).to_be_visible()
    abrir_cuaderno(pagina, fuente)
    agregar(pagina, archivos / "compras.md")
    preguntar(pagina, "gerente aprueba")
    expect(pagina.get_by_text("buscados por palabras")).to_be_visible()
    expect(pagina.locator("ol button mark").first).to_have_text(re.compile("aprueba|gerente", re.I))
    assert "/api/chat" not in falso.llamadas


def test_sin_modelo_ofrece_descargarlo(pagina, fuente, falso):
    falso.modelos = {"nomic-embed-text:latest"}
    abrir_cuaderno(pagina, fuente)
    expect(chat(pagina).get_by_text("Falta descargar gpt-oss:20b")).to_be_visible()
    pagina.get_by_role("button", name="Descargar gpt-oss:20b").click()
    expect(chat(pagina).get_by_text("Falta descargar gpt-oss:20b")).to_be_hidden(timeout=15_000)
    assert "gpt-oss:20b" in falso.modelos


def test_sin_ollama_ofrece_solo_buscar(pagina, fuente, monkeypatch):
    monkeypatch.setattr(ollama, "URL", "http://127.0.0.1:9")
    abrir_cuaderno(pagina, fuente)
    expect(chat(pagina).get_by_text("Ollama está cerrado")).to_be_visible()
    pagina.get_by_role("button", name="Usar solo buscar").click()
    expect(chat(pagina).get_by_text("Ollama está cerrado")).to_be_hidden()
    assert fuente.app.proveedores.modo == "buscar"


def test_varias_conversaciones_que_siguen_al_recargar(pagina, fuente, archivos):
    abrir_cuaderno(pagina, fuente)
    agregar(pagina, archivos / "compras.md")
    preguntar(pagina, PREGUNTA)
    pagina.reload()
    expect(pagina.locator(".prosa:has(.cita)")).to_contain_text("gerente de operaciones")
    pagina.get_by_role("button", name="Nueva conversación").click()
    expect(pagina.locator(".prosa:has(.cita)")).to_have_count(0)
    preguntar(pagina, "¿Qué aprueba el gerente de operaciones?")
    pagina.get_by_role("button", name="Conversación: ¿Qué aprueba el gerente de operaciones?. Cambiar").click()
    pagina.get_by_role("menuitem", name=re.compile(re.escape(PREGUNTA))).click()
    expect(pagina.locator(".prosa:has(.cita)")).to_have_count(1)
    expect(chat(pagina).locator("p").get_by_text(PREGUNTA, exact=True)).to_be_visible()
    pagina.get_by_role("button", name=f"Conversación: {PREGUNTA}. Cambiar").click()
    pagina.get_by_role("menuitem", name="Borrar esta conversación").click()
    pagina.get_by_role("button", name="Borrar conversación").click()
    expect(chat(pagina).locator("p").get_by_text(PREGUNTA, exact=True)).to_be_hidden()
    assert [v["titulo"] for v in fuente.app.cuadernos.conversaciones(fuente.app.cuadernos.lista()[0]["id"])] == [
        "¿Qué aprueba el gerente de operaciones?"
    ]


def test_pegar_texto_desde_el_boton_nuevo(pagina, fuente):
    cid = abrir_cuaderno(pagina, fuente)
    pagina.get_by_role("button", name="Nuevo", exact=True).click()
    pagina.get_by_role("menuitem", name="Fuente").click()
    pagina.get_by_role("tab", name="Pegar texto").click()
    pagina.get_by_label("Título (opcional)").fill("Correo del proveedor")
    pagina.get_by_label("Texto", exact=True).fill("El despacho llega el martes a las 10:00.")
    pagina.get_by_label("Cuaderno", exact=True).select_option(cid)
    pagina.get_by_role("button", name="Agregar texto").click()
    expect(pagina.get_by_text("Agregaste «Correo del proveedor.md»")).to_be_visible(timeout=10_000)
    pagina.keyboard.press("Escape")
    expect(fuentes(pagina)).to_contain_text("Correo del proveedor.md")


def test_conectar_una_carpeta(pagina, fuente, archivos):
    abrir_cuaderno(pagina, fuente)
    fuentes(pagina).get_by_role("button", name="Agregar fuente").click()
    pagina.get_by_role("menuitem", name="Conectar una carpeta").click()
    pagina.get_by_label("Ruta de la carpeta").fill("documentos")
    pagina.get_by_role("button", name="Conectar y leer").click()
    expect(pagina.get_by_role("alert")).to_contain_text("ruta completa")
    pagina.get_by_label("Ruta de la carpeta").fill(str(archivos))
    pagina.get_by_role("button", name="Conectar y leer").click()
    expect(pagina.get_by_role("dialog").get_by_text("2 nuevos")).to_be_visible(timeout=15_000)
    pagina.get_by_role("button", name="Listo").click()
    expect(fuentes(pagina).locator("article")).to_have_count(2)
    expect(fuentes(pagina).get_by_role("list", name="Carpetas conectadas")).to_contain_text(archivos.name)
    (archivos / "compras.md").unlink()
    fuentes(pagina).get_by_role("button", name=f"Sincronizar {archivos.name}").click()
    expect(fuentes(pagina).locator("article")).to_have_count(1, timeout=15_000)
    expect(pagina.get_by_text("1 quitado")).to_be_visible()


def test_un_archivo_que_no_sirve_se_explica(pagina, fuente, tmp_path):
    (tmp_path / "foto.png").write_bytes(b"x")
    (tmp_path / "planilla.xlsx").write_bytes(b"x")
    abrir_cuaderno(pagina, fuente)
    pagina.set_input_files(
        '[data-prueba="elegir-archivos"]', [str(tmp_path / "foto.png"), str(tmp_path / "planilla.xlsx")]
    )
    expect(fuentes(pagina)).to_contain_text(NO_SE_PUEDE)
    expect(fuentes(pagina)).to_contain_text("El archivo no es un Excel (.xlsx) válido.")


def test_la_clave_de_la_api_no_vuelve_y_avisa_que_sale_del_pc(pagina, fuente):
    pagina.goto(f"{fuente.url}#/ajustes")
    pagina.get_by_label(re.compile("^API compatible")).check()
    pagina.get_by_role("button", name="Groq").click()
    pagina.get_by_label("Modelo", exact=True).fill("llama-3.3-70b")
    pagina.get_by_label("Clave").fill("gsk-secreta")
    expect(pagina.get_by_text("se envían a api.groq.com")).to_be_visible()
    pagina.get_by_role("button", name="Guardar", exact=True).click()
    expect(pagina.get_by_label("Clave")).to_have_attribute("placeholder", re.compile("^Guardada"))
    expect(pagina.get_by_label("Clave")).to_have_value("")
    assert fuente.app.proveedores.publico()["openai"]["hay_clave"]


def test_en_el_celular_las_columnas_son_pestanas(navegador, fuente, archivos):
    contexto = navegador.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = contexto.new_page()
    abrir_cuaderno(pg, fuente)
    expect(pg.get_by_role("tab", name="Chat")).to_have_attribute("aria-selected", "true")
    expect(pg.get_by_role("region", name="Fuentes")).to_be_hidden()
    pg.get_by_role("tab", name="Fuentes").click()
    expect(pg.get_by_role("region", name="Fuentes")).to_be_visible()
    ancho = pg.evaluate("document.documentElement.scrollWidth")
    assert ancho <= 390, f"la página se sale de la pantalla: {ancho}px"
    contexto.close()


def estudio(pg):
    return pg.get_by_role("region", name="Estudio")


def generar(pg, tipo):
    notas = pg.get_by_role("region", name="Notas").locator("article")
    antes = notas.count()
    estudio(pg).get_by_role("button", name=tipo, exact=True).click()
    expect(notas).to_have_count(antes + 1, timeout=15_000)


def test_estudio_escribe_un_mapa_un_cuestionario_y_tarjetas(pagina, fuente, archivos):
    abrir_cuaderno(pagina, fuente)
    agregar(pagina, archivos / "compras.md")
    generar(pagina, "Mapa de ideas")
    notas = pagina.get_by_role("region", name="Notas")
    expect(notas).to_contain_text("Mapa de ideas")
    notas.get_by_role("button", name=re.compile("^Abrir la nota")).first.click()
    mapa = pagina.get_by_role("tree")
    expect(mapa).to_be_visible()
    mapa.get_by_role("button", name="Aprobaciones", exact=True).click()  # pregunta por esa idea en el chat
    expect(pagina.get_by_role("dialog")).to_be_hidden()
    expect(chat(pagina)).to_contain_text("Explícame «Aprobaciones» según las fuentes.")
    expect(pagina.locator("[data-vuelta]")).to_have_count(1, timeout=10_000)

    generar(pagina, "Cuestionario")
    notas.get_by_role("button", name=re.compile("^Abrir la nota Cuestionario")).click()
    pagina.get_by_role("group", name="Alternativas de la pregunta 1").get_by_role("button").first.click()
    expect(pagina.get_by_role("dialog")).to_contain_text("Correcta.")
    expect(pagina.get_by_role("dialog")).to_contain_text("Respondiste 1 de")
    pagina.keyboard.press("Escape")

    generar(pagina, "Tarjetas")
    notas.get_by_role("button", name=re.compile("^Abrir la nota Tarjetas")).click()
    tarjeta = pagina.get_by_role("button", name=re.compile("^Pregunta: "))
    tarjeta.click()
    expect(pagina.get_by_role("button", name=re.compile("^Respuesta: "))).to_be_visible()
    pagina.get_by_role("button", name="Tarjeta siguiente").click()
    expect(pagina.get_by_text(re.compile("^2 de "))).to_be_visible()


def test_estudio_personalizado_y_cancelar(pagina, fuente, falso, archivos):
    abrir_cuaderno(pagina, fuente)
    agregar(pagina, archivos / "compras.md")
    estudio(pagina).get_by_role("button", name="Personalizado").click()
    pagina.get_by_label("Qué escribir").fill("Una lista de quién aprueba qué")
    pagina.get_by_role("button", name="Escribir", exact=True).click()
    expect(pagina.get_by_text(re.compile("^Listo: «"))).to_be_visible(timeout=15_000)
    notas = fuente.app.cuadernos.obtener(fuente.app.cuadernos.lista()[0]["id"])["notas"]
    assert notas[0]["instruccion"] == "Una lista de quién aprueba qué"
    # mientras escribe se puede cancelar
    falso.demora = 1.0
    estudio(pagina).get_by_role("button", name="Resumen").click()
    expect(estudio(pagina).get_by_text("Escribiendo el resumen")).to_be_visible()
    estudio(pagina).get_by_role("button", name="Cancelar").click()
    expect(pagina.get_by_text("Cancelado")).to_be_visible()
    expect(estudio(pagina).get_by_text("Escribiendo el resumen")).to_be_hidden()


def test_leer_la_fuente_desde_su_guia_y_descargar_el_original(pagina, fuente, archivos):
    abrir_cuaderno(pagina, fuente)
    agregar(pagina, archivos / "compras.md")
    fuentes(pagina).get_by_role("button", name="Ver compras.md").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_role("button", name="Leer en Tesela").click()
    expect(dialogo.get_by_role("tab", name="Documento completo")).to_have_attribute("aria-selected", "true")
    expect(dialogo.get_by_role("heading", name="Aprobaciones")).to_be_visible()
    expect(dialogo).to_contain_text("Sobre USD 50.000 aprueba el gerente")
    assert len(pagina.context.pages) == 1
    with pagina.expect_download() as descarga:
        dialogo.get_by_role("button", name="Descargar el original").click()
    assert descarga.value.suggested_filename == "compras.md"
    assert Path(descarga.value.path()).read_text(encoding="utf-8") == MD
    assert len(pagina.context.pages) == 1
    expect(dialogo.get_by_role("heading", name="Aprobaciones")).to_be_visible()


def test_la_guia_de_una_fuente_sugiere_preguntas(pagina, fuente, archivos):
    abrir_cuaderno(pagina, fuente)
    agregar(pagina, archivos / "compras.md")
    fuentes(pagina).get_by_role("button", name="Ver compras.md").click()
    dialogo = pagina.get_by_role("dialog")
    expect(dialogo.get_by_role("tab", name="Guía")).to_have_attribute("aria-selected", "true")
    dialogo.get_by_role("button", name="Escribir la guía").click()
    expect(dialogo.get_by_text("Preguntas para empezar")).to_be_visible(timeout=15_000)
    expect(dialogo).to_contain_text("Escrita por gpt-oss:20b")
    pregunta = dialogo.get_by_role("button", name=re.compile(r"^¿Qué dice sobre")).first
    texto = pregunta.inner_text()
    pregunta.click()
    expect(dialogo).to_be_hidden()
    expect(chat(pagina).get_by_text(texto, exact=True)).to_be_visible()
    expect(pagina.locator("[data-vuelta]")).to_have_count(1, timeout=10_000)
    pagina.get_by_role("button", name="Nueva conversación").click()
    expect(chat(pagina).get_by_text("Para empezar")).to_be_visible()


def test_agregar_una_pagina_web(pagina, fuente, sitio, monkeypatch):  # noqa: F811
    monkeypatch.setattr(enlaces, "PERMITIR_LOCALES", True)
    abrir_cuaderno(pagina, fuente)
    fuentes(pagina).get_by_role("button", name="Agregar fuente").click()
    pagina.get_by_role("menuitem", name="Agregar un enlace").click()
    pagina.get_by_label("Enlace de la página").fill(f"{sitio}/politica")
    pagina.get_by_role("button", name="Agregar página").click()
    expect(pagina.get_by_text("Agregaste «Política de compras.md»")).to_be_visible(timeout=10_000)
    pagina.keyboard.press("Escape")
    expect(fuentes(pagina)).to_contain_text("Página web · 127.0.0.1")
    preguntar(pagina, PREGUNTA)
    expect(pagina.locator(".prosa:has(.cita)").last).to_contain_text("gerente de operaciones")


def test_convertir_nota_ia_conserva_origen_fuentes_y_advertencias(pagina, fuente):
    cid = abrir_cuaderno(pagina, fuente)
    nota = fuente.app.cuadernos.crear_nota(
        cid,
        "Resumen derivado",
        "El monto es 123.",
        "generada",
        {
            "tipo": "resumen",
            "modelo": "modelo de prueba",
            "fuentes": [{"id": "a" * 12, "nombre": "compras.md"}],
            "avisos": ["123"],
        },
    )
    pagina.reload()
    pagina.get_by_role("button", name="Abrir la nota Resumen derivado").click()
    pagina.get_by_role("button", name="Convertir en fuente").click()
    expect(pagina.get_by_text("«Resumen derivado.md» ya es una fuente")).to_be_visible(timeout=10_000)
    doc = fuente.app.biblioteca.documentos()[0]
    texto = fuente.app.biblioteca.texto(doc["id"])
    assert "Origen: texto generado por IA" in texto and nota["id"] in texto
    assert "compras.md" in texto and "Modelo: modelo de prueba" in texto
    assert "Advertencia de la nota original: 123" in texto and "El monto es 123." in texto


def test_configurar_el_chat_y_convertir_una_nota_en_fuente(pagina, fuente, archivos):
    cid = abrir_cuaderno(pagina, fuente)
    pagina.get_by_role("button", name="Configurar el chat").click()
    pagina.get_by_label(re.compile("^Detalladas")).check()
    pagina.get_by_label("Indicaciones para este cuaderno (opcional)").fill("Con ejemplos.")
    pagina.get_by_role("button", name="Guardar", exact=True).click()
    expect(pagina.get_by_text("Listo: así responde el chat de este cuaderno")).to_be_visible()
    assert fuente.app.cuadernos.obtener(cid)["estilo"] == {"largo": "largo", "instrucciones": "Con ejemplos."}

    estudio(pagina).get_by_role("button", name="Escribir nota").click()
    pagina.get_by_label("Título").fill("Turnos")
    pagina.get_by_label("Contenido").fill("El turno de noche parte a las **20:00**.")
    pagina.get_by_role("button", name="Guardar nota").click()
    pagina.get_by_role("button", name="Abrir la nota Turnos").click()
    expect(pagina.get_by_role("dialog").locator("strong")).to_have_text("20:00")
    pagina.get_by_role("button", name="Editar").click()
    pagina.get_by_label("Contenido").fill("El turno de noche parte a las **21:00**.")
    pagina.get_by_role("button", name="Guardar nota").click()
    expect(pagina.get_by_role("dialog").locator("strong")).to_have_text("21:00")  # se ve lo editado
    pagina.get_by_role("button", name="Convertir en fuente").click()
    expect(pagina.get_by_text("«Turnos.md» ya es una fuente")).to_be_visible(timeout=10_000)
    pagina.keyboard.press("Escape")
    expect(fuentes(pagina).locator("article")).to_have_count(1)
    expect(fuentes(pagina)).to_contain_text("Turnos.md")
