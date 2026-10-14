"""Carpetas conectadas: agregar, actualizar y podar sin borrar lo que no trajo la carpeta."""

import os
import time

import pytest
from conftest import embedder_falso

from rag_local.biblioteca import Biblioteca
from rag_local.carpetas import Carpetas, ErrorCarpeta, archivos_de, validar_ruta
from rag_local.cuadernos import Cuadernos

UNO = "# Uno\n\n## Plazo\n\nEl contrato dura 24 meses."
DOS = "# Dos\n\n## Tarifa\n\nSe paga por kilómetro."


@pytest.fixture
def mesa(tmp_path):
    datos = tmp_path / "biblioteca"
    biblioteca, cuadernos, carpetas = Biblioteca(datos), Cuadernos(datos), Carpetas(datos)
    carpeta = tmp_path / "Contratos"
    carpeta.mkdir()
    (carpeta / "uno.md").write_text(UNO, encoding="utf-8")
    (carpeta / "dos.md").write_text(DOS, encoding="utf-8")
    cuaderno = cuadernos.crear("Contratos")["id"]
    conectada = carpetas.conectar(str(carpeta), cuaderno)

    def sincronizar():
        return carpetas.sincronizar(conectada["id"], biblioteca, cuadernos, embedder_falso, "falso", lambda _e: None)

    class Tesela:
        pass

    m = Tesela()
    m.biblioteca, m.cuadernos, m.carpetas, m.carpeta, m.cuaderno, m.id, m.sincronizar = (
        biblioteca, cuadernos, carpetas, carpeta, cuaderno, conectada["id"], sincronizar,
    )  # fmt: skip
    return m


def nombres(m):
    return sorted(d["nombre"] for d in m.biblioteca.documentos())


def en_cuaderno(m):
    ids = m.cuadernos.obtener(m.cuaderno)["documentos"]
    return sorted(m.biblioteca.documento(i)["nombre"] for i in ids)


def test_agrega_actualiza_y_quita(mesa):
    informe = mesa.sincronizar()
    assert (informe["agregados"], informe["quitados"]) == (2, 0)
    assert nombres(mesa) == en_cuaderno(mesa) == ["dos.md", "uno.md"]
    assert mesa.sincronizar()["sin_cambios"] == 2  # nada cambió: no se vuelve a leer

    (mesa.carpeta / "uno.md").write_text(UNO + "\n\nSe renueva solo.", encoding="utf-8")
    os.utime(mesa.carpeta / "uno.md", (time.time() + 5, time.time() + 5))
    (mesa.carpeta / "dos.md").unlink()
    (mesa.carpeta / "tres.txt").write_text("Tercer documento de la carpeta.", encoding="utf-8")
    informe = mesa.sincronizar()
    assert (informe["agregados"], informe["actualizados"], informe["quitados"]) == (1, 1, 1)
    assert nombres(mesa) == en_cuaderno(mesa) == ["tres.txt", "uno.md"]  # la versión vieja de uno.md ya no está
    assert "Se renueva solo" in mesa.biblioteca.texto(
        next(d["id"] for d in mesa.biblioteca.documentos() if d["nombre"] == "uno.md")
    )


def test_no_borra_lo_que_la_persona_ya_tenia(mesa):
    # «dos.md» ya estaba en la biblioteca (subido a mano) antes de conectar la carpeta
    propio = mesa.biblioteca.agregar("dos.md", DOS.encode(), embedder_falso, "falso", lambda _e: None)
    mesa.sincronizar()
    (mesa.carpeta / "dos.md").unlink()
    mesa.sincronizar()
    assert mesa.biblioteca.documento(propio["id"]) is not None  # sigue en la biblioteca
    assert en_cuaderno(mesa) == ["uno.md"]  # solo salió del cuaderno de la carpeta


def test_no_borra_lo_que_se_uso_en_otro_cuaderno(mesa):
    mesa.sincronizar()
    otro = mesa.cuadernos.crear("Otro")["id"]
    uno = next(d["id"] for d in mesa.biblioteca.documentos() if d["nombre"] == "uno.md")
    mesa.cuadernos.enlazar(otro, uno)
    (mesa.carpeta / "uno.md").unlink()
    mesa.sincronizar()
    assert mesa.biblioteca.documento(uno) is not None and en_cuaderno(mesa) == ["dos.md"]


def test_un_archivo_que_no_se_puede_leer_queda_en_el_informe(mesa):
    (mesa.carpeta / "roto.docx").write_bytes(b"no es un zip")
    (mesa.carpeta / "~$uno.docx").write_bytes(b"temporal de Word")
    (mesa.carpeta / "foto.png").write_bytes(b"x")
    informe = mesa.sincronizar()
    assert informe["agregados"] == 2
    assert informe["errores"] == [{"archivo": "roto.docx", "texto": "El archivo no es un Word (.docx) válido."}]


def test_subcarpetas_y_limites(tmp_path, monkeypatch):
    from rag_local import carpetas

    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "hondo.md").write_text("# Hondo", encoding="utf-8")
    (tmp_path / ".oculta").mkdir()
    (tmp_path / ".oculta" / "x.md").write_text("# X", encoding="utf-8")
    assert [r for r, _ in archivos_de(tmp_path)[0]] == ["a/b/hondo.md"]
    monkeypatch.setattr(carpetas, "ARCHIVOS_MAXIMOS", 0)
    with pytest.raises(ErrorCarpeta, match="más de 0 documentos"):
        archivos_de(tmp_path)


def test_rutas_que_no_se_aceptan(tmp_path):
    for ruta in ("", "documentos", "\\\\servidor\\compartida", "https://ejemplo.com", str(tmp_path / "no-existe")):
        with pytest.raises(ErrorCarpeta):
            validar_ruta(ruta)
    archivo = tmp_path / "a.md"
    archivo.write_text("x", encoding="utf-8")
    with pytest.raises(ErrorCarpeta):
        validar_ruta(str(archivo))
    assert validar_ruta(f'"{tmp_path}"') == tmp_path.resolve()  # el explorador de Windows copia la ruta con comillas


def test_desconectar_deja_los_documentos(mesa):
    mesa.sincronizar()
    mesa.carpetas.desconectar(mesa.id)
    assert nombres(mesa) == ["dos.md", "uno.md"] and Carpetas(mesa.biblioteca.carpeta).lista() == []


def test_no_relee_la_biblioteca_de_mesa(tmp_path):
    datos = tmp_path / "biblioteca"
    biblioteca, cuadernos, carpetas = Biblioteca(datos), Cuadernos(datos), Carpetas(datos)
    (tmp_path / "uno.md").write_text(UNO, encoding="utf-8")
    c = carpetas.conectar(str(tmp_path), None)  # la carpeta conectada contiene la biblioteca
    for _ in range(2):
        carpetas.sincronizar(c["id"], biblioteca, cuadernos, embedder_falso, "falso", lambda _e: None)
    assert [d["nombre"] for d in biblioteca.documentos()] == ["uno.md"]
    with pytest.raises(ErrorCarpeta, match="donde Tesela guarda"):
        carpetas.conectar(str(datos / "originales"), None)
