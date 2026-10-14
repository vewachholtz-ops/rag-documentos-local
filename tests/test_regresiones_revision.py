"""Casos encontrados al revisar Tesela: sin internet ni modelos reales."""

import io
import socket
import ssl
import threading
from unittest.mock import Mock

import pytest

from rag_local import enlaces, estudio
from rag_local.biblioteca import Biblioteca
from rag_local.servidor import App


def test_un_cambio_dns_no_permite_conectar_a_la_red_local(monkeypatch):
    ips = iter(["93.184.216.34", "127.0.0.1"])
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(ips), port or 80))],
    )
    conexion = Mock()
    conexion.makefile.return_value = io.BytesIO(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 6\r\n\r\nlocal!"
    )
    monkeypatch.setattr(socket, "socket", Mock(return_value=conexion))
    monkeypatch.setattr(enlaces.urllib.request, "getproxies", lambda: {})
    with pytest.raises(enlaces.ErrorEnlace, match="red local"):
        enlaces.traer("http://ejemplo.test/texto")
    conexion.connect.assert_not_called()


@pytest.mark.parametrize("esquema", ["http", "https"])
def test_conexion_fija_la_ip_y_conserva_host_y_tls(monkeypatch, esquema):
    direcciones = Mock(
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443 if esquema == "https" else 80))]
    )
    monkeypatch.setattr(socket, "getaddrinfo", direcciones)
    conexion = Mock()
    conexion.makefile.return_value = io.BytesIO(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 6\r\n\r\ntexto!"
    )
    monkeypatch.setattr(socket, "socket", Mock(return_value=conexion))
    tls = []

    def envolver(contexto, sock, *, server_hostname):
        tls.append(server_hostname)
        assert contexto.check_hostname and contexto.verify_mode == ssl.CERT_REQUIRED
        return sock

    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", envolver)
    _, datos, _ = enlaces.traer(f"{esquema}://ejemplo.test/texto")
    assert datos == b"texto!" and direcciones.call_count == 2
    conexion.connect.assert_called_once_with(("93.184.216.34", 443 if esquema == "https" else 80))
    assert b"Host: ejemplo.test" in conexion.sendall.call_args_list[0].args[0]
    assert tls == (["ejemplo.test"] if esquema == "https" else [])


@pytest.mark.parametrize("es_guia", [False, True])
def test_cancelar_durante_la_ultima_llamada_no_guarda_el_resultado(tmp_path, monkeypatch, es_guia):
    app = App(Biblioteca(tmp_path))
    doc = app.biblioteca.agregar("fuente.md", b"# Fuente\n\nUna fuente para consultar.", None, "", lambda _: None)
    cid = app.cuadernos.crear("Prueba", documentos=[doc["id"]])["id"]
    entro = threading.Event()
    liberar = threading.Event()
    termino = threading.Event()
    monkeypatch.setattr(app, "_modelo_para", lambda _: (None, None, "modelo de prueba"))

    def escribir(*args):
        entro.set()
        assert liberar.wait(3)
        return {"resumen": "Prueba", "temas": [], "preguntas": []} if es_guia else ("Resumen", "Contenido")

    monkeypatch.setattr(estudio, "escribir_guia" if es_guia else "escribir", escribir)
    guardar = Mock()
    monkeypatch.setattr(
        app.biblioteca if es_guia else app.cuadernos, "guardar_guia" if es_guia else "crear_nota", guardar
    )
    eventos = app.guia(doc["id"]) if es_guia else app.generar(cid, "resumen")
    anteriores = set(threading.enumerate())
    assert next(eventos)["tipo"] == "paso"
    trabajadores = set(threading.enumerate()) - anteriores

    def esperar_latido():
        try:
            assert next(eventos)["tipo"] == "latido"
        finally:
            termino.set()

    lector = threading.Thread(target=esperar_latido)
    lector.start()
    try:
        assert entro.wait(1)
        assert termino.wait(1)
        eventos.close()
    finally:
        liberar.set()
        lector.join(timeout=3)
    for trabajador in trabajadores:
        trabajador.join(timeout=3)
        assert not trabajador.is_alive()
    guardar.assert_not_called()


def test_estudio_respeta_el_limite_sin_omitir_fuentes_en_silencio():
    cupos = estudio._repartir({str(i): 20 + i for i in range(13)}, 36)
    assert sum(cupos.values()) == 36 and min(cupos.values()) >= 1
    with pytest.raises(estudio.SinMaterial, match="como máximo 36"):
        estudio._repartir({str(i): 2 for i in range(50)}, 36)
