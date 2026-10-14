"""La versión web (src/rag_local/navegador.py) en Python común: los pedidos en bytes pasan por el mismo Manejador,
sin hilos; el modo empieza en solo buscar y no se puede elegir Ollama. En el navegador de verdad, con Pyodide, la
prueban tests/test_app_web.py."""

import json

import pytest

from rag_local import enlaces, navegador, ollama, servidor

MD = "# Compras\n\n## Aprobaciones\n\nSobre USD 50.000 aprueba el gerente de operaciones de la faena.\n"


@pytest.fixture
def web(tmp_path, monkeypatch):
    # iniciar() cambia funciones de los módulos; se devuelven al terminar la prueba
    for modulo, nombre in ((servidor, "_en_otro_hilo"), (ollama, "modelos_instalados"), (enlaces, "traer")):
        monkeypatch.setattr(modulo, nombre, getattr(modulo, nombre))
    monkeypatch.setattr(navegador, "_app", None)
    navegador.iniciar(tmp_path / "biblioteca")
    return tmp_path


def pedir(metodo, ruta, cuerpo=None, **cabeceras):
    """(estado, cabeceras, trozos del cuerpo) de un pedido a la versión web."""
    trozos: list[bytes] = []
    datos = None
    if isinstance(cuerpo, dict):
        datos = json.dumps(cuerpo).encode()
        cabeceras.setdefault("Content-Type", "application/json")
    elif isinstance(cuerpo, bytes):
        datos = cuerpo
    navegador.atender(metodo, ruta, {k.replace("_", "-"): v for k, v in cabeceras.items()}, datos, trozos.append)
    crudo = b"".join(trozos)
    cabeza, _, cuerpo_resp = crudo.partition(b"\r\n\r\n")
    linea, *resto = cabeza.decode("latin-1").split("\r\n")
    return int(linea.split()[1]), dict(r.split(": ", 1) for r in resto), cuerpo_resp, trozos


def test_empieza_en_solo_buscar_sin_ollama(web):
    estado, _, cuerpo, _ = pedir("GET", "/api/estado")
    assert estado == 200
    datos = json.loads(cuerpo)
    assert datos["modo"] == "buscar"
    assert datos["ollama"] is False
    assert datos["listo"] is True
    estado, _, cuerpo, _ = pedir("PUT", "/api/ajustes", {"modo": "ollama"})
    assert estado == 400
    assert "instala Tesela" in json.loads(cuerpo)["error"]


def test_agregar_y_buscar_en_un_cuaderno(web):
    estado, _, cuerpo, _ = pedir("POST", "/api/cuadernos", {"nombre": "Compras"})
    assert estado == 201
    cid = json.loads(cuerpo)["cuaderno"]["id"]
    estado, cabeceras, cuerpo, trozos = pedir(
        "POST", f"/api/cuadernos/{cid}/documentos", MD.encode(), Content_Type="application/octet-stream",
        X_Nombre="compras.md",
    )  # fmt: skip
    assert estado == 200
    assert cabeceras["Content-Type"].startswith("application/x-ndjson")
    eventos = [json.loads(linea) for linea in cuerpo.decode().splitlines() if linea.strip()]
    assert eventos[-1]["tipo"] == "listo"
    assert any(e["tipo"] == "paso" for e in eventos[:-1])  # los avisos salen antes del resultado
    assert len(trozos) > 2  # y salen de a poco, no todo junto al final

    estado, _, cuerpo, _ = pedir("POST", f"/api/cuadernos/{cid}/preguntar", {"pregunta": "¿Quién aprueba?"})
    vuelta = [json.loads(linea) for linea in cuerpo.decode().splitlines() if linea.strip()][-1]
    assert vuelta["tipo"] == "vuelta"
    assert "gerente de operaciones" in json.dumps(vuelta["vuelta"]["pasajes"], ensure_ascii=False)


def test_valida_igual_que_el_servidor(web):
    # el token lo pone navegador.py: uno distinto en el pedido se ignora, igual que el Host y el Origin
    assert pedir("GET", "/api/estado", X_Mesa_Token="otro", Origin="https://otro.sitio")[0] == 200
    assert pedir("POST", "/api/cuadernos", b"{}", Content_Type="text/plain")[0] == 415
    assert pedir("GET", "/api/cuadernos/000000000000")[0] == 404
    _, _, cuerpo, _ = pedir("POST", "/api/enlaces", {"url": "https://ejemplo.cl"})
    final = [json.loads(linea) for linea in cuerpo.decode().splitlines() if linea.strip()][-1]
    assert final == {"tipo": "error", "texto": navegador.SIN_ENLACES}


def test_una_cabecera_con_salto_de_linea_no_entra(web):
    estado, _, _, _ = pedir("GET", "/api/estado", X_Otra="a\r\nX-Mesa-Token: web")
    assert estado == 200


def test_sin_iniciar_avisa(monkeypatch):
    monkeypatch.setattr(navegador, "_app", None)
    with pytest.raises(RuntimeError):
        navegador.atender("GET", "/api/estado", {}, None, lambda _: None)
