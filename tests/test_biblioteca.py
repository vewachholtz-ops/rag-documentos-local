"""La biblioteca de la app: leer cada tipo de archivo, guardar, elegir, quitar y no repetir."""

import pytest
from archivos import docx_simple, pdf_simple, pptx_simple, xlsx_simple
from conftest import embedder_falso

from rag_local.biblioteca import Biblioteca, ErrorDocumento, trocear

MD = (
    "# Política de compras\n\n## Aprobaciones\n\nHasta USD 5.000 aprueba el jefe del área.\n\n"
    "## Cotizaciones\n\nSobre USD 10.000 se piden tres cotizaciones."
)


def agregar(b: Biblioteca, nombre: str, datos: bytes) -> dict:
    avisos = []
    doc = b.agregar(nombre, datos, embedder_falso, "falso", avisos.append)
    assert avisos[0] == {"tipo": "paso", "texto": "Leyendo"} and avisos[-1]["tipo"] == "progreso"
    return doc


def test_markdown_por_secciones_y_todo_queda_en_la_carpeta(tmp_path):
    b = Biblioteca(tmp_path)
    doc = agregar(b, "compras.md", MD.encode())
    assert doc["tipo"] == "md" and doc["trozos"] == 2
    for sub, ext in (("originales", ".md"), ("texto", ".md"), ("trozos", ".json"), ("vectores", ".npy")):
        assert (tmp_path / sub / f"{doc['id']}{ext}").exists()
    indice = b.indice()
    assert [t.titulo for t in indice.trozos] == ["compras.md > Aprobaciones", "compras.md > Cotizaciones"]
    assert indice.buscar("cotizaciones", 1, embedder_falso)[0].trozo.seccion == "Cotizaciones"
    assert [d["nombre"] for d in Biblioteca(tmp_path).documentos()] == ["compras.md"]  # sobrevive al reinicio


def test_el_mismo_archivo_no_se_agrega_dos_veces(tmp_path):
    b = Biblioteca(tmp_path)
    primero = agregar(b, "compras.md", MD.encode())
    segundo = b.agregar("copia.md", MD.encode(), embedder_falso, "falso", lambda _e: None)
    assert segundo["repetido"] and segundo["id"] == primero["id"] and len(b.documentos()) == 1


def test_quitar_borra_la_copia_y_cambia_el_indice(tmp_path):
    b = Biblioteca(tmp_path)
    uno = agregar(b, "compras.md", MD.encode())
    dos = agregar(b, "notas.txt", "Reunión: el inventario se adelanta a noviembre.".encode())
    assert len(b.indice([dos["id"]]).trozos) == 1
    assert b.quitar(uno["id"]) and not b.quitar(uno["id"])
    assert not list((tmp_path / "originales").glob(f"{uno['id']}*"))
    assert {t.documento for t in b.indice().trozos} == {dos["id"]}
    assert b.indice([uno["id"]]) is None


def test_texto_de_windows_y_utf16():
    _, trozos, _ = trocear("x", "notas.txt", "txt", "Reunión de bodega: año y señal".encode("cp1252"))
    assert "Reunión" in trozos[0].texto and "señal" in trozos[0].texto and trozos[0].seccion == "Inicio"
    _, trozos, _ = trocear("x", "notas.txt", "txt", "Planilla exportada: código".encode("utf-16"))
    assert "código" in trozos[0].texto


def test_excel_conserva_todas_las_cifras_del_original():
    valores = [1234567890.12, 1234567890123, 0.123456789012345, -9876543210.98]
    texto, _, _ = trocear("x", "montos.xlsx", "xlsx", xlsx_simple({"Montos": [["Valor"], *[[v] for v in valores]]}))
    for valor in valores:
        assert f"| {valor} |" in texto


def test_markdown_con_un_titulo_por_seccion():
    _, trozos, _ = trocear("x", "guia.md", "md", b"# Uno\n\nAlfa.\n\n# Dos\n\nBeta.")
    assert [t.seccion for t in trozos] == ["Uno", "Dos"]


def test_word_con_titulos_y_tabla():
    datos = docx_simple(
        [("titulo", "Manual de bodega"), ("subtitulo", "Horario"), ("parrafo", "Abre a las 8:00."),
         ("subtitulo", "Montos"), ("tabla", [["Cargo", "Monto"], ["Jefe", "USD 5.000"]])]
    )  # fmt: skip
    texto, trozos, paginas = trocear("x", "manual.docx", "docx", datos)
    assert paginas is None and [t.seccion for t in trozos] == ["Horario", "Montos"]
    assert "| Jefe | USD 5.000 |" in texto and "Jefe" in trozos[1].texto


def test_word_con_declaraciones_se_rechaza():
    datos = docx_simple([("parrafo", "x")], cabecera='<!DOCTYPE w [<!ENTITY a "aaaa">]>')
    with pytest.raises(ErrorDocumento, match="declaraciones"):
        trocear("x", "malo.docx", "docx", datos)
    with pytest.raises(ErrorDocumento, match="no es un Word"):
        trocear("x", "malo.docx", "docx", b"no es un zip")


def test_pdf_por_pagina_con_su_numero():
    datos = pdf_simple(["Politica de compras\nHasta USD 5.000 aprueba el jefe.", "Cotizaciones\nSe piden tres."])
    texto, trozos, paginas = trocear("x", "compras.pdf", "pdf", datos)
    assert paginas == 2 and [t.pagina for t in trozos] == [1, 2]
    assert trozos[1].titulo == "compras.pdf > Página 2" and "tres" in trozos[1].texto
    assert "## Página 2" in texto


def test_pdf_sin_texto_se_explica():
    with pytest.raises(ErrorDocumento, match="escaneado"):
        trocear("x", "escaneo.pdf", "pdf", pdf_simple([""]))
    with pytest.raises(ErrorDocumento, match="No pude leer el PDF"):
        trocear("x", "roto.pdf", "pdf", b"%PDF-1.4 nada")


def test_tipo_y_tamano(tmp_path, monkeypatch):
    b = Biblioteca(tmp_path)
    with pytest.raises(ErrorDocumento, match="tipo de archivo"):
        b.agregar("foto.png", b"x", embedder_falso, "falso", lambda _e: None)
    with pytest.raises(ErrorDocumento, match="no es un Excel"):
        b.agregar("planilla.xlsx", b"x", embedder_falso, "falso", lambda _e: None)
    monkeypatch.setattr("rag_local.biblioteca.TAMANO_MAXIMO", 10)
    with pytest.raises(ErrorDocumento, match="30 MB"):
        b.agregar("largo.txt", b"x" * 11, embedder_falso, "falso", lambda _e: None)
    assert b.documentos() == []


def test_un_nombre_con_ruta_queda_solo_como_nombre(tmp_path):
    doc = agregar(Biblioteca(tmp_path), "..\\..\\secreto/notas.txt", b"Texto de prueba suficiente.")
    assert doc["nombre"] == "notas.txt"


def test_limites_contra_archivos_que_se_inflan(monkeypatch):
    from rag_local import biblioteca

    monkeypatch.setattr(biblioteca, "PAGINAS_MAXIMAS", 1)
    with pytest.raises(ErrorDocumento, match="más de 1 páginas"):
        trocear("x", "a.pdf", "pdf", pdf_simple(["uno", "dos"]))
    monkeypatch.setattr(biblioteca, "XML_MAXIMO", 100)
    with pytest.raises(ErrorDocumento, match="demasiado grande por dentro"):
        trocear("x", "a.docx", "docx", docx_simple([("parrafo", "texto " * 50)]))
    monkeypatch.setattr(biblioteca, "TEXTO_MAXIMO", 10)
    with pytest.raises(ErrorDocumento, match="demasiado texto"):
        trocear("x", "a.txt", "txt", b"un texto largo de verdad")


def test_un_documento_con_demasiados_trozos(tmp_path, monkeypatch):
    from rag_local import biblioteca

    monkeypatch.setattr(biblioteca, "TROZOS_MAXIMOS", 1)
    md = b"# T\n\n## Uno\n\nAlgo.\n\n## Dos\n\nOtra cosa."
    with pytest.raises(ErrorDocumento, match="demasiado largo"):
        Biblioteca(tmp_path).agregar("t.md", md, None, None, lambda _e: None)


def test_powerpoint_por_diapositiva_en_el_orden_de_la_presentacion():
    pptx = pptx_simple(
        [
            ("Compras", ["Sobre USD 50.000 aprueba el gerente", "Plazo: 5 días"], "Contar el caso de la pala"),
            ("Bodega", ["Abre a las 8"], ""),
        ]
    )
    texto, trozos, paginas = trocear("p", "clase.pptx", "pptx", pptx)
    assert paginas is None and texto.index("Diapositiva 1: Compras") < texto.index("Diapositiva 2: Bodega")
    assert [t.titulo for t in trozos] == ["clase.pptx > Diapositiva 1: Compras", "clase.pptx > Diapositiva 2: Bodega"]
    assert "Notas del orador: Contar el caso de la pala" in trozos[0].texto


def test_excel_y_csv_como_tablas_que_se_parten_con_su_encabezado():
    filas = [["Equipo", "Horas"], *[[f"Pala {i}", i * 10] for i in range(1, 21)]]
    texto, trozos, _ = trocear("x", "flota.xlsx", "xlsx", xlsx_simple({"Flota": filas, "Vacía": []}))
    assert "## Hoja: Flota" in texto and "| Pala 20 | 200 |" in texto and "Vacía" not in texto
    assert texto.count("| Equipo | Horas |") == 2  # 20 filas: dos tablas de hasta 15, cada una con su encabezado
    assert all(t.titulo == "flota.xlsx > Hoja: Flota" for t in trozos)
    csv_texto, _, _ = trocear("x", "datos.csv", "csv", b"equipo;horas\nPala 1;10\n")
    assert "| equipo | horas |" in csv_texto and "| Pala 1 | 10 |" in csv_texto


def test_html_sin_menus_ni_scripts():
    pagina = (
        b"<html><head><title>Manual</title><script>alert(1)</script></head><body><nav>Inicio</nav>"
        b"<h2>Bodega</h2><p>La bodega abre a las 8.</p></body></html>"
    )
    texto, trozos, _ = trocear("x", "manual.html", "html", pagina)
    assert texto.startswith("# Manual") and "alert" not in texto and "Inicio" not in texto
    assert trozos[0].titulo == "manual.html > Bodega"


def test_anexos_y_guia_se_borran_con_el_documento(tmp_path):
    b = Biblioteca(tmp_path)
    doc = agregar(b, "compras.md", MD.encode())
    assert b.anexo(doc["id"]) == {}
    b.guardar_anexo(doc["id"], {"notas": {"abc": "- nota"}})
    b.guardar_guia(doc["id"], {"resumen": "Compras", "temas": [], "preguntas": []})
    assert Biblioteca(tmp_path).anexo(doc["id"])["notas"] == {"abc": "- nota"}
    assert Biblioteca(tmp_path).documento(doc["id"])["guia"]["resumen"] == "Compras"
    b.quitar(doc["id"])
    assert not (tmp_path / "anexos" / f"{doc['id']}.json").exists()
    b.guardar_anexo(doc["id"], {"notas": {}})  # ya no existe: no se crea nada
    assert not (tmp_path / "anexos" / f"{doc['id']}.json").exists()


def test_un_documento_que_vino_de_una_pagina_guarda_su_enlace(tmp_path):
    doc = Biblioteca(tmp_path).agregar("Política.md", MD.encode(), None, None, lambda _e: None, url="https://x.cl/p")
    assert Biblioteca(tmp_path).documento(doc["id"])["url"] == "https://x.cl/p"
