"""La app en un navegador de verdad (Chromium con Playwright): lo que las pruebas de Python no ven.

Se saltan si no hay navegador. Para correrlas: `uv run playwright install chromium` una vez. Con un Chromium
ya instalado en otra parte, se puede indicar con la variable RAG_CHROMIUM.
"""

import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

SITIO = Path(__file__).resolve().parents[1] / "site"


class Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


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


def levantar(servidor) -> str:
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{servidor.server_address[1]}/"


@pytest.fixture(scope="module")
def publicada():
    """Como en GitHub Pages: archivos estáticos, sin modelo."""
    s = ThreadingHTTPServer(("127.0.0.1", 0), partial(Silencioso, directory=str(SITIO)))
    yield levantar(s)
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


def preguntar(pg, texto):
    pg.fill("#pregunta", texto)
    pg.keyboard.press("Enter")
    pg.wait_for_selector("#mensajes .msg-asistente:last-child:not([aria-busy])")
    return pg.locator("#mensajes .msg-asistente").last


@pytest.mark.parametrize(
    "texto",
    [
        "¿Qué nivel de servicio tienen los repuestos clase C?",  # guardada: clase B
        "¿Quién aprueba una solicitud de compra de USD 15.000?",  # guardada: USD 150.000
        "¿Quién aprueba una solicitud de compra de CLP 150.000?",  # otra moneda
        "¿No puedo pagar con la caja chica una compra de 80 lucas?",  # negación
    ],
)
def test_una_pregunta_parecida_se_sugiere_y_no_se_responde_con_otra(pagina, publicada, texto):
    pagina.goto(publicada)
    msg = preguntar(pagina, texto)
    assert msg.locator(".opciones .opcion").count() == 3
    assert msg.locator(".meta").count() == 0


def test_la_misma_pregunta_escrita_distinto_si_se_responde(pagina, publicada):
    pagina.goto(publicada)
    msg = preguntar(pagina, "quien aprueba una solicitud de compra de usd 150.000")
    assert msg.locator(".origen").inner_text() == "Guardada, versión mejorada"
    assert "gerente de operaciones" in msg.locator(".respuesta").inner_text().lower()
    assert pagina.locator("#vista-fuente mark").count() > 0  # la fuente se abre al lado, con la frase marcada


def test_mientras_responde_no_se_puede_mandar_otra_y_cada_mensaje_dice_su_version(navegador, publicada):
    contexto = navegador.new_context(viewport={"width": 1440, "height": 900})  # con la animación
    pg = contexto.new_page()
    pg.goto(publicada)
    pg.click(".sugerencia >> nth=0")
    pg.fill("#pregunta", "otra pregunta")
    assert pg.locator(".enviar").is_disabled() and pg.locator("#nueva").is_disabled()
    pg.wait_for_selector(".msg-asistente:not([aria-busy]) .meta")
    assert pg.locator(".msg-asistente .origen").inner_text() == "Guardada, versión mejorada"
    pg.click(".msg-asistente [data-otra]")
    assert pg.locator(".msg-asistente .origen").inner_text() == "Guardada, versión inicial"
    assert "v=v1" in pg.url
    contexto.close()


def test_el_error_conocido_muestra_el_limite_del_validador(pagina, publicada):
    pagina.goto(publicada)
    pagina.click("#inicio [data-preguntar=p72]")
    pagina.wait_for_selector(".msg-asistente .meta")
    assert "Incorrecta en la evaluación" in pagina.inner_text(".msg-asistente .meta")
    assert pagina.locator(".msg-asistente .aviso").is_visible()


def test_en_movil_los_paneles_cerrados_no_se_alcanzan_con_el_teclado(navegador, publicada):
    contexto = navegador.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = contexto.new_page()
    pg.goto(publicada)
    pg.wait_for_selector(".sugerencia")
    inerte = "s => document.querySelector(s).inert"
    assert pg.evaluate(inerte, "#panel-fuentes") and pg.evaluate(inerte, "#panel-detalle")
    pg.click("[data-abrir=panel-fuentes]")
    assert not pg.evaluate(inerte, "#panel-fuentes") and pg.evaluate(inerte, "#contenido")
    assert pg.evaluate("document.activeElement.dataset.cerrar") == "panel-fuentes"
    pg.keyboard.press("Escape")
    assert pg.evaluate(inerte, "#panel-fuentes") and not pg.evaluate(inerte, "#contenido")
    assert pg.evaluate("document.activeElement.dataset.abrir") == "panel-fuentes"
    contexto.close()
