"""Archivos de prueba hechos a mano: un PDF con texto por página y un Word con títulos y una tabla."""

from __future__ import annotations

import io
import zipfile


def pdf_simple(paginas: list[str]) -> bytes:
    """Un PDF mínimo y válido, con una línea de texto por renglón en cada página (fuente Helvetica)."""
    objetos: list[bytes] = []
    n_paginas = len(paginas)
    # 1: catálogo, 2: páginas, 3: fuente, después cada página y su contenido
    hijos = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_paginas))
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objetos.append(f"<< /Type /Pages /Kids [{hijos}] /Count {n_paginas} >>".encode())
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, texto in enumerate(paginas):
        lineas = []
        for j, linea in enumerate(texto.splitlines()):
            seguro = linea.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            lineas.append(f"BT /F1 11 Tf 60 {760 - 16 * j} Td ({seguro}) Tj ET")
        contenido = "\n".join(lineas).encode("cp1252")
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {5 + 2 * i} 0 R >>".encode()
        )
        objetos.append(b"<< /Length %d >>\nstream\n" % len(contenido) + contenido + b"\nendstream")
    salida = io.BytesIO()
    salida.write(b"%PDF-1.4\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, 1):
        posiciones.append(salida.tell())
        salida.write(b"%d 0 obj\n" % numero + cuerpo + b"\nendobj\n")
    inicio = salida.tell()
    salida.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1))
    for p in posiciones:
        salida.write(b"%010d 00000 n \n" % p)
    salida.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, inicio))
    return salida.getvalue()


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _p(texto: str, estilo: str = "") -> str:
    pr = f'<w:pPr><w:pStyle w:val="{estilo}"/></w:pPr>' if estilo else ""
    return f"<w:p>{pr}<w:r><w:t>{texto}</w:t></w:r></w:p>"


def docx_simple(bloques: list[tuple[str, object]], cabecera: str = "") -> bytes:
    """Un .docx con bloques ("titulo" | "subtitulo" | "parrafo", texto) o ("tabla", [[celdas]])."""
    cuerpo = []
    for tipo, valor in bloques:
        if tipo == "titulo":
            cuerpo.append(_p(valor, "Title"))
        elif tipo == "subtitulo":
            cuerpo.append(_p(valor, "Heading1"))
        elif tipo == "parrafo":
            cuerpo.append(_p(valor))
        elif tipo == "tabla":
            filas = "".join("<w:tr>" + "".join(f"<w:tc>{_p(c)}</w:tc>" for c in fila) + "</w:tr>" for fila in valor)
            cuerpo.append(f"<w:tbl>{filas}</w:tbl>")
    xml = (
        f'{cabecera}<?xml version="1.0" encoding="UTF-8"?>'
        f"<w:document {W}><w:body>{''.join(cuerpo)}</w:body></w:document>"
    )
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml.encode("utf-8"))
    return salida.getvalue()


A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
P = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _forma(textos: list[str], marcador: str = "") -> str:
    ph = f'<p:nvSpPr><p:cNvPr id="1" name="x"/><p:cNvSpPr/><p:nvPr><p:ph type="{marcador}"/></p:nvPr></p:nvSpPr>'
    parrafos = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in textos)
    return f"<p:sp>{ph if marcador else ''}<p:txBody>{parrafos}</p:txBody></p:sp>"


def pptx_simple(diapositivas: list[tuple[str, list[str], str]]) -> bytes:
    """Un .pptx con (título, viñetas, notas del orador) por diapositiva. El orden de la presentación es el
    inverso al de los nombres de archivo, para probar que se respeta presentation.xml."""
    salida = io.BytesIO()
    n = len(diapositivas)
    with zipfile.ZipFile(salida, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i + 1}"/>' for i in range(n))
        z.writestr("ppt/presentation.xml", f"<p:presentation {P} {R}><p:sldIdLst>{ids}</p:sldIdLst></p:presentation>")
        rels = "".join(f'<Relationship Id="rId{i + 1}" Target="slides/slide{n - i}.xml" Type="x"/>' for i in range(n))
        z.writestr("ppt/_rels/presentation.xml.rels", f'<Relationships xmlns="{REL}">{rels}</Relationships>')
        for i, (titulo, vinetas, notas) in enumerate(diapositivas):
            archivo = n - i
            formas = _forma([titulo], "title") + _forma(vinetas)
            z.writestr(
                f"ppt/slides/slide{archivo}.xml",
                f"<p:sld {A} {P}><p:cSld><p:spTree>{formas}</p:spTree></p:cSld></p:sld>",
            )
            if notas:
                z.writestr(
                    f"ppt/slides/_rels/slide{archivo}.xml.rels",
                    f'<Relationships xmlns="{REL}"><Relationship Id="rId9" '
                    f'Target="../notesSlides/notesSlide{archivo}.xml" Type="x"/></Relationships>',
                )
                z.writestr(
                    f"ppt/notesSlides/notesSlide{archivo}.xml",
                    f"<p:notes {A} {P}><p:cSld><p:spTree>{_forma([notas], 'body')}</p:spTree></p:cSld></p:notes>",
                )
    return salida.getvalue()


S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def xlsx_simple(hojas: dict[str, list[list[object]]]) -> bytes:
    """Un .xlsx con textos compartidos y números. Cada hoja es una lista de filas."""
    compartidos: list[str] = []
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        lista = "".join(
            f'<sheet name="{nombre}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, nombre in enumerate(hojas)
        )
        z.writestr("xl/workbook.xml", f"<workbook {S} {R}><sheets>{lista}</sheets></workbook>")
        rels = "".join(
            f'<Relationship Id="rId{i + 1}" Target="worksheets/sheet{i + 1}.xml" Type="x"/>' for i in range(len(hojas))
        )
        z.writestr("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{REL}">{rels}</Relationships>')
        for i, filas in enumerate(hojas.values()):
            xml_filas = []
            for f, fila in enumerate(filas, 1):
                celdas = []
                for c, valor in enumerate(fila):
                    ref = f"{chr(65 + c)}{f}"
                    if isinstance(valor, str):
                        compartidos.append(valor)
                        celdas.append(f'<c r="{ref}" t="s"><v>{len(compartidos) - 1}</v></c>')
                    elif valor is not None:
                        celdas.append(f'<c r="{ref}"><v>{valor}</v></c>')
                xml_filas.append(f'<row r="{f}">{"".join(celdas)}</row>')
            z.writestr(
                f"xl/worksheets/sheet{i + 1}.xml",
                f"<worksheet {S}><sheetData>{''.join(xml_filas)}</sheetData></worksheet>",
            )
        sst = "".join(f"<si><t>{t}</t></si>" for t in compartidos)
        z.writestr("xl/sharedStrings.xml", f"<sst {S}>{sst}</sst>")
    return salida.getvalue()
