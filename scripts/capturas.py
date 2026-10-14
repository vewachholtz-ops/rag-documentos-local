"""Las capturas del README, con el modelo simulado de las pruebas (tests/ollama_falso.py).

El modelo simulado responde copiando la oración que más calza: sirve para mostrar la app, no su exactitud.
Necesita la interfaz construida (cd interfaz && npm ci && npm run build) y Chromium para Playwright.

Uso: uv run python scripts/capturas.py [carpeta]      (por defecto, docs/)
     RAG_CHROMIUM=/ruta/al/chrome uv run python scripts/capturas.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "tests"), str(RAIZ / "src")]

from archivos import docx_simple, pdf_simple  # noqa: E402
from ollama_falso import iniciar  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

from rag_local import ollama  # noqa: E402
from rag_local.biblioteca import Biblioteca  # noqa: E402
from rag_local.servidor import App, crear  # noqa: E402

PROCEDIMIENTOS = [
    "PR-COM-01-solicitud-de-compra.md",
    "PR-MAN-03-mantencion-preventiva-palas.md",
    "PR-SEG-05-trabajo-en-altura.md",
]
MANUAL = [
    "Manual de bodega 2026.\nFaena Cerro Alto.\nVersion 5, vigente desde el 15 de enero de 2026.",
    "Recepcion de materiales.\nTodo material se recibe con su guia de despacho.\n"
    "El bodeguero revisa cantidades y estado.",
    "La bodega central abre a las 7:30 y cierra a las 20:00 de lunes a sabado.\n"
    "Los domingos atiende solo la bodega de emergencia.",
]


def fuentes_de_prueba(carpeta: Path) -> list[Path]:
    carpeta.mkdir(parents=True)
    rutas = [shutil.copy(RAIZ / "documentos" / n, carpeta / n) for n in PROCEDIMIENTOS]
    manual = carpeta / "Manual de bodega 2026.pdf"
    manual.write_bytes(pdf_simple(MANUAL))
    return [Path(rutas[0]), manual, *map(Path, rutas[1:])]


def carpeta_de_contratos(carpeta: Path) -> Path:
    """Una carpeta para conectar: tres documentos que se leen y un Word dañado, que se explica."""
    carpeta.mkdir(parents=True)
    (carpeta / "Contrato transporte de personal.md").write_text(
        "# Contrato de transporte de personal\n\nEl contratista traslada a los turnos A y B desde Calama.\n",
        encoding="utf-8",
    )
    (carpeta / "Anexo de tarifas 2026.docx").write_bytes(
        docx_simple([("titulo", "Anexo de tarifas"), ("parrafo", "La tarifa por viaje se reajusta cada seis meses.")])
    )
    (carpeta / "Seguro de responsabilidad.pdf").write_bytes(
        pdf_simple(["Seguro de responsabilidad civil\nCubre danos a terceros durante los traslados."])
    )
    (carpeta / "Contrato antiguo.docx").write_bytes(b"esto no es un Word")
    return carpeta


def main() -> None:
    salida = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "docs"
    salida.mkdir(parents=True, exist_ok=True)
    _, _, url = iniciar(demora=0.0)
    ollama.URL = url
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        tmp = Path(tmp)
        app = App(Biblioteca(tmp / "biblioteca"))
        servidor = crear(RAIZ / "app", app, 0)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{servidor.server_address[1]}/"
        archivos = fuentes_de_prueba(tmp / "fuentes")
        contratos = carpeta_de_contratos(tmp / "Contratos 2026")

        navegador = p.chromium.launch(executable_path=os.environ.get("RAG_CHROMIUM") or None)
        contexto = navegador.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        pg = contexto.new_page()

        # la primera vez
        pg.goto(base)
        expect(pg.get_by_role("heading", name="Pregúntale a tus documentos")).to_be_visible()
        pg.screenshot(path=salida / "tesela-inicio.png")

        # un cuaderno con cuatro fuentes, dos respuestas y dos notas de Estudio
        c = app.cuadernos.crear(
            "Abastecimiento y mantención",
            "Procedimientos de Faena Cerro Alto que uso en el ramo de gestión de operaciones.",
        )
        pg.set_viewport_size({"width": 1440, "height": 860})
        pg.goto(f"{base}#/cuadernos/{c['id']}")
        fuentes = pg.get_by_role("region", name="Fuentes", exact=True)
        pg.set_input_files('[data-prueba="elegir-archivos"]', [str(a) for a in archivos])
        expect(fuentes.locator("article")).to_have_count(4, timeout=20_000)
        for pregunta in ("¿Quién puede crear una solicitud de pedido?", "¿A qué hora abre la bodega central?"):
            antes = pg.locator(".prosa:has(.cita)").count()
            pg.get_by_role("textbox", name="Pregunta").fill(pregunta)
            pg.keyboard.press("Enter")
            expect(pg.locator(".prosa:has(.cita)")).to_have_count(antes + 1, timeout=20_000)
        notas = pg.get_by_role("region", name="Notas").locator("article")
        for tipo in ("Mapa de ideas", "Guía de estudio"):
            antes = notas.count()
            pg.get_by_role("region", name="Estudio").get_by_role("button", name=tipo, exact=True).click()
            expect(notas).to_have_count(antes + 1, timeout=20_000)
        # los avisos de «Listo» no van en las capturas
        pg.add_style_tag(content="[data-sonner-toaster]{visibility:hidden !important}")
        pg.get_by_role("region", name="Chat").get_by_text(
            "¿Quién puede crear una solicitud de pedido?"
        ).last.scroll_into_view_if_needed()
        pg.mouse.move(5, 5)
        pg.wait_for_timeout(300)
        pg.screenshot(path=salida / "tesela-cuaderno.png")

        # el pasaje citado del PDF, con la frase marcada
        pg.locator(".prosa:has(.cita)").last.locator(".cita").first.click()
        expect(pg.get_by_role("dialog").locator("mark").first).to_be_visible()
        pg.wait_for_timeout(300)
        pg.screenshot(path=salida / "tesela-cita.png")
        pg.keyboard.press("Escape")

        # la guía de una fuente
        fuentes.get_by_role("button", name=f"Ver {PROCEDIMIENTOS[0]}").click()
        dialogo = pg.get_by_role("dialog")
        dialogo.get_by_role("button", name="Escribir la guía").click()
        expect(dialogo.get_by_text("Preguntas para empezar")).to_be_visible(timeout=20_000)
        pg.wait_for_timeout(300)
        pg.screenshot(path=salida / "tesela-guia.png")
        pg.keyboard.press("Escape")

        # el mapa de ideas
        pg.set_viewport_size({"width": 1440, "height": 1060})
        mapa = pg.get_by_role("region", name="Notas").locator("article", has_text="Mapa de ideas")
        mapa.get_by_role("button", name=re.compile("^Abrir la nota")).first.click()
        expect(pg.get_by_role("tree")).to_be_visible()
        pg.wait_for_timeout(300)
        pg.screenshot(path=salida / "tesela-mapa.png")
        pg.keyboard.press("Escape")

        # el mismo cuaderno en modo oscuro
        oscuro = navegador.new_context(
            viewport={"width": 1440, "height": 860}, reduced_motion="reduce", color_scheme="dark"
        )
        po = oscuro.new_page()
        po.goto(f"{base}#/cuadernos/{c['id']}")
        expect(po.locator(".prosa:has(.cita)")).to_have_count(2, timeout=20_000)
        po.wait_for_timeout(500)
        po.screenshot(path=salida / "tesela-oscuro.png")
        oscuro.close()

        # conectar una carpeta
        pg.set_viewport_size({"width": 1440, "height": 860})
        fuentes.get_by_role("button", name="Agregar fuente").click()
        pg.get_by_role("menuitem", name="Conectar una carpeta").click()
        pg.get_by_label("Ruta de la carpeta").fill(str(contratos))
        pg.get_by_role("button", name="Conectar y leer").click()
        expect(pg.get_by_role("dialog").get_by_text("3 nuevos")).to_be_visible(timeout=20_000)
        pg.wait_for_timeout(300)
        pg.screenshot(path=salida / "tesela-carpeta.png")
        pg.get_by_role("button", name="Listo").click()
        navegador.close()
        servidor.shutdown()
    print("capturas en", salida)


if __name__ == "__main__":
    main()
