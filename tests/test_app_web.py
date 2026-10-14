"""La versión web en un navegador de verdad: Pyodide carga el motor, se agregan documentos, se busca, la biblioteca
sigue ahí al recargar y el modo API responde con una API de mentira que acepta pedidos de otra página.

Necesita la versión web construida con una copia local de Pyodide (sin internet) y esa copia:

    cd interfaz && VITE_WEB=1 VITE_PYODIDE=/pyodide/ npm run build && cd ..
    uv run python scripts/construir_web.py
    RAG_PYODIDE=/ruta/a/pyodide uv run pytest tests/test_app_web.py

La carpeta de RAG_PYODIDE es la de pyodide-core de la versión 0.27.7 con las ruedas de numpy y pyodide-http.
Sin esa variable, las pruebas se saltan.
"""

import functools
import http.server
import os
import re
import threading
from pathlib import Path
from typing import ClassVar

import pytest
from archivos import pdf_simple
from ollama_falso import Estado, manejador

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "site" / "app"
PYODIDE = Path(os.environ.get("RAG_PYODIDE", ""))
if not os.environ.get("RAG_PYODIDE") or not (PYODIDE / "pyodide.mjs").exists() or not (WEB / "py").exists():
    pytest.skip("falta la versión web construida o RAG_PYODIDE", allow_module_level=True)

MD = "# Compras\n\n## Aprobaciones\n\nSobre USD 50.000 aprueba el gerente de operaciones de la faena.\n"


class _Archivos(http.server.SimpleHTTPRequestHandler):
    """Sirve /app/ (la versión web) y /pyodide/ (la copia local) como GitHub Pages: archivos y nada más."""

    extensions_map: ClassVar[dict[str, str]] = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".mjs": "text/javascript",
        ".js": "text/javascript",
    }

    def translate_path(self, path):
        ruta = path.split("?", 1)[0].split("#", 1)[0]
        for prefijo, carpeta in (("/app/", WEB), ("/pyodide/", PYODIDE)):
            if ruta.startswith(prefijo):
                return str(carpeta / ruta[len(prefijo) :])
        return str(WEB / "no-existe")

    def log_message(self, *args):
        pass


class _ApiConCors(manejador(Estado(set(), 0))):
    """La API compatible con OpenAI de las pruebas, con las cabeceras que deja llamarla desde otra página."""

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


def _servir(clase):
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), clase)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


@pytest.fixture(scope="module")
def url():
    servidor = _servir(functools.partial(_Archivos, directory=str(WEB)))
    yield f"http://127.0.0.1:{servidor.server_address[1]}/app/"
    servidor.shutdown()


@pytest.fixture(scope="module")
def api():
    servidor = _servir(_ApiConCors)
    yield f"http://127.0.0.1:{servidor.server_address[1]}/v1"
    servidor.shutdown()


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
def pagina(navegador):
    contexto = navegador.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    pg = contexto.new_page()
    errores: list[str] = []
    pg.on("pageerror", lambda e: errores.append(str(e)))
    yield pg
    contexto.close()
    assert not errores, errores


@pytest.fixture
def archivos(tmp_path):
    (tmp_path / "compras.md").write_text(MD, encoding="utf-8")
    (tmp_path / "bodega.pdf").write_bytes(pdf_simple(["Bodega central", "La bodega abre a las 8 de la manana."]))
    return tmp_path


def crear_cuaderno(pg, url, nombre="Compras"):
    pg.goto(url)
    expect(pg.get_by_role("heading", name="Pregúntale a tus documentos")).to_be_visible(timeout=120_000)
    expect(pg.get_by_text("Versión web.")).to_be_visible()
    pg.get_by_role("button", name="Crear el primer cuaderno").click()
    pg.get_by_label("Nombre").fill(nombre)
    pg.get_by_role("button", name="Crear cuaderno").click()
    expect(pg.get_by_text("Agrega tus documentos")).to_be_visible()


def fuentes(pg):
    return pg.get_by_role("region", name="Fuentes", exact=True)


def test_agregar_buscar_y_recargar(pagina, url, archivos):
    crear_cuaderno(pagina, url)
    pagina.set_input_files(
        '[data-prueba="elegir-archivos"]', [str(archivos / "compras.md"), str(archivos / "bodega.pdf")]
    )
    expect(fuentes(pagina).locator("article")).to_have_count(2, timeout=60_000)
    expect(fuentes(pagina)).to_contain_text("PDF · 2 páginas")
    pagina.get_by_role("textbox", name="Pregunta").fill("¿Quién aprueba sobre USD 50.000?")
    pagina.keyboard.press("Enter")
    chat = pagina.get_by_role("region", name="Chat")
    expect(chat).to_contain_text("pasajes que más calzan", timeout=60_000)
    expect(chat).to_contain_text("gerente de operaciones")
    # sin enlaces ni carpetas: el navegador no puede leer otros sitios ni el disco
    fuentes(pagina).get_by_role("button", name="Agregar fuente").click()
    menu = pagina.get_by_role("menu")
    expect(menu).not_to_contain_text("enlace")
    expect(menu).not_to_contain_text("carpeta")
    pagina.keyboard.press("Escape")
    # la biblioteca queda en el navegador
    pagina.reload()
    expect(fuentes(pagina).locator("article")).to_have_count(2, timeout=120_000)
    # el original se baja desde la memoria
    fuentes(pagina).get_by_role("button", name="Ver compras.md").click()
    with pagina.expect_download() as descarga:
        pagina.get_by_role("dialog").get_by_role("button", name="Descargar el original").click()
    assert descarga.value.suggested_filename == "compras.md"
    assert Path(descarga.value.path()).read_text(encoding="utf-8") == MD


def test_modelos_sin_ollama_y_con_una_api(pagina, url, api, archivos):
    pagina.goto(f"{url}#/ajustes")
    expect(pagina.get_by_role("heading", name="Modelos")).to_be_visible(timeout=120_000)
    expect(pagina.get_by_text("Ollama, en este computador")).to_have_count(0)
    pagina.get_by_text("API compatible con OpenAI").first.click()
    pagina.locator("#url-api").fill(api)
    pagina.locator("#modelo-api").fill("modelo-de-prueba")
    pagina.locator("#clave-api").fill("clave-de-prueba")
    pagina.get_by_role("button", name="Guardar").click()
    expect(pagina.get_by_text("Queda guardada en este navegador")).to_be_visible()
    expect(pagina.get_by_role("button", name="Borrar la clave guardada")).to_be_visible()  # ya se guardó

    crear_cuaderno(pagina, url)
    pagina.set_input_files('[data-prueba="elegir-archivos"]', [str(archivos / "compras.md")])
    expect(fuentes(pagina).locator("article")).to_have_count(1, timeout=60_000)
    pagina.get_by_role("textbox", name="Pregunta").fill("¿Quién aprueba sobre USD 50.000?")
    pagina.keyboard.press("Enter")
    expect(pagina.locator(".prosa:has(.cita)").last).to_contain_text("gerente de operaciones", timeout=60_000)
    notas = pagina.get_by_role("region", name="Notas").locator("article")
    pagina.get_by_role("region", name="Estudio").get_by_role("button", name="Mapa de ideas", exact=True).click()
    expect(notas).to_have_count(1, timeout=60_000)
    expect(notas.first).to_contain_text(re.compile("Mapa de ideas"))
