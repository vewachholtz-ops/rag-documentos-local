"""El servidor de la app, con un Ollama de mentira: cuadernos, documentos, notas, preguntas en los tres modos,
modelos y quién puede pedir."""

import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import pytest
from archivos import pdf_simple
from ollama_falso import iniciar

from rag_local import biblioteca, enlaces, estudio, ollama, servidor
from rag_local.biblioteca import Biblioteca
from rag_local.servidor import App, crear

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"
MD = b"# Compras\n\n## Aprobaciones\n\nSobre USD 50.000 aprueba el gerente de operaciones de la faena."
PREGUNTA = {"pregunta": "¿Quién aprueba sobre USD 50.000?"}
TOKEN = "token-de-prueba"


@pytest.fixture
def falso(monkeypatch):
    s, estado, url = iniciar(demora=0)
    monkeypatch.setattr(ollama, "URL", url)
    yield estado
    s.shutdown()
    s.server_close()


@pytest.fixture
def puerto(tmp_path, falso, monkeypatch):
    monkeypatch.setenv("MESA_TOKEN", TOKEN)
    s = crear(APP, App(Biblioteca(tmp_path / "biblioteca")), 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s.server_address[1]
    s.shutdown()
    s.server_close()


def pedir(puerto, metodo, ruta, cuerpo=None, tipo="application/json", **cabeceras):
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
    datos = json.dumps(cuerpo).encode() if isinstance(cuerpo, dict) else cuerpo
    base = {"Host": f"127.0.0.1:{puerto}", "X-Mesa-Token": TOKEN}
    if datos is not None:
        base |= {"Content-Type": tipo, "Content-Length": str(len(datos))}
    base |= {k.replace("_", "-"): v for k, v in cabeceras.items()}
    c.request(metodo, ruta, body=datos, headers=base)
    r = c.getresponse()
    return r.status, r.getheader("Content-Type", ""), r.read()


def json_de(puerto, metodo, ruta, cuerpo=None):
    estado, _, datos = pedir(puerto, metodo, ruta, cuerpo)
    assert estado in (200, 201), (estado, datos)
    return json.loads(datos)


def lineas(datos: bytes) -> list[dict]:
    return [json.loads(x) for x in datos.decode().splitlines() if x]


def subir(puerto, nombre="compras.md", datos=MD, cuaderno=None):
    ruta = f"/api/cuadernos/{cuaderno}/documentos" if cuaderno else "/api/documentos"
    estado, tipo, cuerpo = pedir(puerto, "POST", ruta, datos, tipo="application/octet-stream", X_Nombre=quote(nombre))
    assert estado == 200 and tipo.startswith("application/x-ndjson")
    return lineas(cuerpo)


def nuevo_cuaderno(puerto, nombre="Compras"):
    return json_de(puerto, "POST", "/api/cuadernos", {"nombre": nombre, "descripcion": "Políticas"})["cuaderno"]


def preguntar(puerto, cid, cuerpo=PREGUNTA):
    return lineas(pedir(puerto, "POST", f"/api/cuadernos/{cid}/preguntar", cuerpo)[2])


def generar(puerto, cid, tipo, instruccion=""):
    return lineas(pedir(puerto, "POST", f"/api/cuadernos/{cid}/generar", {"tipo": tipo, "instruccion": instruccion})[2])


LARGO = "# Mantención de palas\n\n" + "\n\n".join(
    f"## Paso {i}\n\nEl paso {i} de la mantención preventiva de la pala revisa el sistema número {i} con cuidado. "
    f"El supervisor registra el resultado del paso {i} en la bitácora de la faena."
    for i in range(1, 13)
)
CHICAS = estudio.Medidas(ventana=400, material=600, partes=36, corta=150)


def test_la_pagina_y_el_estado(puerto, falso):
    estado, _, cuerpo = pedir(puerto, "GET", "/")
    assert estado == 200 and b'<div id="raiz">' in cuerpo
    e = json_de(puerto, "GET", "/api/estado")
    assert e["modo"] == "ollama" and e["listo"] and e["faltan"] == [] and e["modelos"] == ["gpt-oss:20b"]
    assert e["documentos"] == 0 and e["cuadernos"] == 0 and e["busqueda_por_significado"]
    falso.modelos = {"nomic-embed-text:latest"}
    e = json_de(puerto, "GET", "/api/estado")
    assert e["faltan"] == ["gpt-oss:20b"] and not e["listo"]


def test_la_pagina_lleva_csp_y_la_api_no_se_guarda(puerto):
    cabeceras = http.client.HTTPConnection("127.0.0.1", puerto, timeout=5)
    cabeceras.request("GET", "/", headers={"Host": f"127.0.0.1:{puerto}"})
    r = cabeceras.getresponse()
    assert "script-src 'self'" in r.getheader("Content-Security-Policy") and r.getheader("Cache-Control") == "no-cache"


def test_un_cuaderno_de_punta_a_punta(puerto):
    c = nuevo_cuaderno(puerto)
    assert c["nombre"] == "Compras" and c["documentos"] == [] and c["notas"] == []
    eventos = subir(puerto, "Política de compras.md", cuaderno=c["id"])
    assert eventos[0] == {"tipo": "paso", "texto": "Leyendo"} and eventos[-1]["tipo"] == "listo"
    doc = eventos[-1]["documento"]
    assert doc["nombre"] == "Política de compras.md" and doc["por_significado"] and "sha256" not in doc
    lista = json_de(puerto, "GET", "/api/cuadernos")["cuadernos"]
    assert [(x["nombre"], x["fuentes"], x["notas"]) for x in lista] == [("Compras", 1, 0)]
    biblioteca = json_de(puerto, "GET", "/api/documentos")["documentos"]
    assert biblioteca[0]["cuadernos"] == [{"id": c["id"], "nombre": "Compras"}]

    eventos = preguntar(puerto, c["id"])
    pasos = [e["texto"] for e in eventos if e["tipo"] == "paso"]
    assert pasos[:2] == ["Reformulando la pregunta", "Buscando en tus documentos"]
    vuelta = eventos[-1]["vuelta"]
    assert eventos[-1]["tipo"] == "vuelta" and vuelta["modo"] == "ollama" and vuelta["modelo"] == "gpt-oss:20b"
    r = vuelta["respuesta"]
    assert "gerente de operaciones" in r["texto"]
    assert r["fuentes"][0]["doc_id"] == doc["id"] and r["fuentes"][0]["citada"]
    guardado = json_de(puerto, "GET", f"/api/cuadernos/{c['id']}")["cuaderno"]
    (conversacion,) = guardado["conversaciones"]
    assert conversacion["id"] == eventos[-1]["conversacion"] and conversacion["preguntas"] == 1
    assert conversacion["titulo"] == PREGUNTA["pregunta"] and "vueltas" not in conversacion

    nota = json_de(puerto, "POST", f"/api/cuadernos/{c['id']}/notas", {"titulo": "Montos", "contenido": "50.000"})
    nid = nota["nota"]["id"]
    cambiada = json_de(puerto, "PATCH", f"/api/cuadernos/{c['id']}/notas/{nid}", {"contenido": "USD 50.000"})
    assert cambiada["nota"]["contenido"] == "USD 50.000" and cambiada["nota"]["origen"] == "propia"
    assert (
        json_de(puerto, "PATCH", f"/api/cuadernos/{c['id']}", {"nombre": "Abastecimiento"})["cuaderno"]["nombre"]
        == "Abastecimiento"
    )

    assert pedir(puerto, "DELETE", f"/api/cuadernos/{c['id']}/conversaciones/{conversacion['id']}")[0] == 200
    assert pedir(puerto, "DELETE", f"/api/cuadernos/{c['id']}/notas/{nid}")[0] == 200
    sin = json_de(puerto, "DELETE", f"/api/cuadernos/{c['id']}/documentos/{doc['id']}")["cuaderno"]
    assert sin["documentos"] == [] and json_de(puerto, "GET", "/api/documentos")["documentos"]  # sigue en la biblioteca
    con = json_de(puerto, "PUT", f"/api/cuadernos/{c['id']}/documentos/{doc['id']}")["cuaderno"]
    assert [d["id"] for d in con["documentos"]] == [doc["id"]]
    assert pedir(puerto, "DELETE", f"/api/cuadernos/{c['id']}")[0] == 200
    assert pedir(puerto, "GET", f"/api/cuadernos/{c['id']}")[0] == 404


def test_ver_y_borrar_un_documento_de_la_biblioteca(puerto):
    c = nuevo_cuaderno(puerto)
    doc = subir(puerto, cuaderno=c["id"])[-1]["documento"]
    detalle = json_de(puerto, "GET", f"/api/documentos/{doc['id']}")
    assert "<h4>Aprobaciones</h4>" in detalle["html"]
    estado, tipo, original = pedir(puerto, "GET", f"/api/documentos/{doc['id']}/original")
    assert estado == 200 and original == MD and tipo.startswith("text/plain")
    assert subir(puerto, "copia.md")[-1]["documento"]["repetido"]
    assert pedir(puerto, "DELETE", f"/api/documentos/{doc['id']}")[0] == 200
    assert pedir(puerto, "GET", f"/api/documentos/{doc['id']}")[0] == 404
    assert json_de(puerto, "GET", f"/api/cuadernos/{c['id']}")["cuaderno"]["documentos"] == []


def test_las_fuentes_apagadas_no_entran_al_chat(puerto):
    c = nuevo_cuaderno(puerto)
    doc = subir(puerto, cuaderno=c["id"])[-1]["documento"]
    json_de(puerto, "PATCH", f"/api/cuadernos/{c['id']}", {"fuera": [doc["id"]]})
    assert preguntar(puerto, c["id"])[-1] == {
        "tipo": "error",
        "texto": "Agrega una fuente al cuaderno, o activa alguna, para preguntar.",
    }


def test_solo_buscar_responde_sin_modelo_de_chat(puerto, falso):
    falso.modelos = set()  # ni chat ni embeddings: Ollama abierto pero vacío
    assert json_de(puerto, "PUT", "/api/ajustes", {"modo": "buscar"})["modo"] == "buscar"
    c = nuevo_cuaderno(puerto)
    doc = subir(puerto, cuaderno=c["id"])[-1]["documento"]
    assert not doc["por_significado"]
    assert json_de(puerto, "GET", "/api/estado")["listo"]
    vuelta = preguntar(puerto, c["id"])[-1]["vuelta"]
    pasajes = vuelta["pasajes"]
    assert vuelta["modo"] == "buscar" and pasajes["busqueda"] == "por palabras"
    assert "<mark>aprueba</mark>" in pasajes["pasajes"][0]["html"] and pasajes["pasajes"][0]["doc_id"] == doc["id"]
    assert "/api/chat" not in falso.llamadas and "/api/embed" not in falso.llamadas


def test_un_documento_sin_embeddings_se_completa_al_preguntar_con_ollama(puerto, falso):
    falso.modelos = {"gpt-oss:20b"}
    c = nuevo_cuaderno(puerto)
    assert not subir(puerto, cuaderno=c["id"])[-1]["documento"]["por_significado"]
    falso.modelos = {"gpt-oss:20b", "nomic-embed-text:latest"}
    eventos = preguntar(puerto, c["id"])
    assert {"tipo": "paso", "texto": "Preparando 1 de 1 documentos para buscar por significado"} in eventos
    assert eventos[-1]["tipo"] == "vuelta"
    assert json_de(puerto, "GET", "/api/documentos")["documentos"][0]["por_significado"]


def test_api_compatible_con_openai(puerto, falso):
    url = ollama.URL + "/v1"
    ajustes = json_de(puerto, "PUT", "/api/ajustes", {"modo": "openai", "openai": {"url": url, "modelo": "m"}})
    assert ajustes["openai"] == {"url": url, "modelo": "m", "hay_clave": False, "local": True}
    c = nuevo_cuaderno(puerto)
    subir(puerto, cuaderno=c["id"])
    assert preguntar(puerto, c["id"])[-1] == {"tipo": "error", "texto": "La API rechazó la clave. Revísala en Modelos."}
    ajustes = json_de(puerto, "PUT", "/api/ajustes", {"openai": {"clave": "clave-de-prueba"}})
    assert ajustes["openai"]["hay_clave"] and "clave-de-prueba" not in json.dumps(ajustes)
    vuelta = preguntar(puerto, c["id"])[-1]["vuelta"]
    assert vuelta["modo"] == "openai" and vuelta["modelo"] == "m"
    assert "gerente de operaciones" in vuelta["respuesta"]["texto"]
    assert "/api/chat" not in falso.llamadas  # respondió la API, no Ollama
    assert pedir(puerto, "PUT", "/api/ajustes", {"openai": {"url": "file:///etc/passwd"}})[0] == 400
    assert pedir(puerto, "PUT", "/api/ajustes", {"modo": "otro"})[0] == 400


def test_un_archivo_que_no_se_puede_leer_explica_por_que(puerto):
    assert subir(puerto, "foto.png", b"x")[-1] == {
        "tipo": "error",
        "texto": biblioteca.NO_SE_PUEDE,
    }
    assert subir(puerto, "planilla.xlsx", b"x")[-1] == {
        "tipo": "error",
        "texto": "El archivo no es un Excel (.xlsx) válido.",
    }


def test_si_ollama_se_cae_a_mitad_llega_un_error(puerto, monkeypatch):
    c = nuevo_cuaderno(puerto)
    subir(puerto, cuaderno=c["id"])
    monkeypatch.setattr(ollama, "URL", "http://127.0.0.1:9")  # nadie escucha ahí
    error = {"tipo": "error", "texto": "No encuentro Ollama. Ábrelo y vuelve a intentarlo."}
    assert preguntar(puerto, c["id"])[-1] == error


def test_descargar_un_modelo_que_falta(puerto, falso):
    falso.modelos = {"nomic-embed-text:latest"}
    eventos = lineas(pedir(puerto, "POST", "/api/modelos/descargar", {"modelo": "gpt-oss:20b"})[2])
    assert [e["tipo"] for e in eventos].count("progreso") >= 4 and eventos[-1] == {"tipo": "listo"}
    assert "gpt-oss:20b" in falso.modelos
    assert pedir(puerto, "POST", "/api/modelos/descargar", {"modelo": "otro:70b"})[0] == 400


def test_la_biblioteca_de_fuente_2_queda_en_un_cuaderno(tmp_path, falso):
    biblioteca = Biblioteca(tmp_path / "b")
    biblioteca.agregar("compras.md", MD, None, None, lambda _e: None)
    app = App(biblioteca)
    (cuaderno,) = app.cuadernos.lista()
    assert cuaderno["nombre"] == "Mis documentos" and cuaderno["fuentes"] == 1
    app.cuadernos.borrar(cuaderno["id"])
    assert App(biblioteca).cuadernos.lista() == []  # no se vuelve a crear


def test_rechaza_lo_que_no_viene_de_la_app(puerto):
    c = nuevo_cuaderno(puerto)
    ruta = f"/api/cuadernos/{c['id']}/preguntar"
    # un dominio ajeno que apunta a 127.0.0.1 (DNS rebinding)
    assert pedir(puerto, "GET", "/api/documentos", Host="ataque.example:80")[0] == 403
    # otra página abierta en el navegador
    assert pedir(puerto, "POST", ruta, PREGUNTA, Origin="https://ataque.example")[0] == 403
    assert pedir(puerto, "DELETE", f"/api/cuadernos/{c['id']}", Origin="https://ataque.example")[0] == 403
    assert pedir(puerto, "PUT", "/api/ajustes", {"modo": "buscar"}, Origin="https://ataque.example")[0] == 403
    # un formulario: text/plain no necesita permiso del navegador, por eso se exige otro tipo
    assert pedir(puerto, "POST", ruta, json.dumps(PREGUNTA).encode(), tipo="text/plain")[0] == 415
    assert pedir(puerto, "POST", "/api/documentos", MD, tipo="text/plain", X_Nombre="a.md")[0] == 415
    assert pedir(puerto, "POST", ruta, {"pregunta": "x" * 50_000})[0] == 413
    assert pedir(puerto, "POST", ruta, {"pregunta": "   "})[0] == 400
    assert pedir(puerto, "GET", "/api/documentos/../../etc/passwd")[0] == 404
    assert pedir(puerto, "GET", "/api/cuadernos/..%2f..%2fajustes")[0] == 404
    assert pedir(puerto, "POST", "/api/cuadernos/0123456789ab/preguntar", PREGUNTA)[0] == 404
    assert pedir(puerto, "PATCH", "/", {"x": 1})[0] == 405
    assert pedir(puerto, "POST", ruta, PREGUNTA, Origin=f"http://localhost:{puerto}")[0] == 200


def test_la_api_pide_el_token_de_la_sesion(puerto):
    pagina = pedir(puerto, "GET", "/")[2].decode()
    assert f'<meta name="mesa-token" content="{TOKEN}">' in pagina
    assert pedir(puerto, "GET", "/api/estado", X_Mesa_Token="")[0] == 403
    assert pedir(puerto, "GET", "/api/documentos", X_Mesa_Token="otro")[0] == 403
    c = nuevo_cuaderno(puerto)
    assert pedir(puerto, "DELETE", f"/api/cuadernos/{c['id']}", X_Mesa_Token="otro")[0] == 403
    assert pedir(puerto, "POST", f"/api/cuadernos/{c['id']}/preguntar", PREGUNTA, X_Mesa_Token="")[0] == 403
    doc = subir(puerto, cuaderno=c["id"])[-1]["documento"]
    # el original se abre con un enlace en otra pestaña: no lleva token
    assert pedir(puerto, "GET", f"/api/documentos/{doc['id']}/original", X_Mesa_Token="")[0] == 200


def test_sin_token_fijo_cada_apertura_tiene_uno_distinto(tmp_path, monkeypatch):
    monkeypatch.delenv("MESA_TOKEN", raising=False)
    uno, otro = App(Biblioteca(tmp_path / "a")).token, App(Biblioteca(tmp_path / "b")).token
    assert uno != otro and len(uno) >= 40


def test_borrar_un_documento_mientras_responde(tmp_path, monkeypatch):
    s_falso, _, url = iniciar(demora=0.3)
    monkeypatch.setattr(ollama, "URL", url)
    monkeypatch.setenv("MESA_TOKEN", TOKEN)
    s = crear(APP, App(Biblioteca(tmp_path / "biblioteca")), 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    p = s.server_address[1]
    try:
        c = nuevo_cuaderno(p)
        doc = subir(p, cuaderno=c["id"])[-1]["documento"]
        resultado = {}
        hilo = threading.Thread(target=lambda: resultado.update(eventos=preguntar(p, c["id"])))
        hilo.start()
        time.sleep(0.5)  # ya está buscando o redactando
        assert pedir(p, "DELETE", f"/api/documentos/{doc['id']}")[0] == 200
        hilo.join(30)
        final = resultado["eventos"][-1]
        # termina la respuesta con lo que ya había leído; la cita apunta a un documento que ya no está
        assert final["tipo"] == "vuelta", final
        assert pedir(p, "GET", f"/api/documentos/{doc['id']}")[0] == 404
    finally:
        s.shutdown()
        s.server_close()
        s_falso.shutdown()
        s_falso.server_close()


def test_conectar_y_sincronizar_una_carpeta(puerto, tmp_path):
    carpeta = tmp_path / "Compras"
    carpeta.mkdir()
    (carpeta / "compras.md").write_bytes(MD)
    c = nuevo_cuaderno(puerto)
    assert pedir(puerto, "POST", "/api/carpetas", {"ruta": "relativa", "cuaderno": c["id"]})[0] == 400
    assert pedir(puerto, "POST", "/api/carpetas", {"ruta": str(carpeta), "cuaderno": "0123456789ab"})[0] == 404
    conectada = json_de(puerto, "POST", "/api/carpetas", {"ruta": str(carpeta), "cuaderno": c["id"]})["carpeta"]
    eventos = lineas(pedir(puerto, "POST", f"/api/carpetas/{conectada['id']}/sincronizar", {})[2])
    assert {"tipo": "paso", "texto": "Leyendo compras.md (1 de 1)"} in eventos
    final = eventos[-1]
    assert final["tipo"] == "sincronizada" and final["informe"]["agregados"] == 1
    assert [d["nombre"] for d in json_de(puerto, "GET", f"/api/cuadernos/{c['id']}")["cuaderno"]["documentos"]] == [
        "compras.md"
    ]
    (lista,) = json_de(puerto, "GET", "/api/carpetas")["carpetas"]
    assert lista["cuaderno_nombre"] == "Compras" and lista["documentos"] == 1 and lista["sincronizada"]
    assert pedir(puerto, "DELETE", f"/api/carpetas/{conectada['id']}", X_Mesa_Token="otro")[0] == 403
    assert pedir(puerto, "DELETE", f"/api/carpetas/{conectada['id']}")[0] == 200
    assert json_de(puerto, "GET", "/api/carpetas")["carpetas"] == []


def test_puerto_ocupado_da_un_mensaje_claro(tmp_path, puerto, monkeypatch):
    def no_debe_servir(*args):
        pytest.fail("Un puerto ocupado no debe iniciar un segundo servidor")

    monkeypatch.setattr(servidor.ServidorLocal, "serve_forever", no_debe_servir)
    with pytest.raises(SystemExit, match="ya está abierta"):
        servidor.servir(RAIZ, tmp_path / "b", puerto, abrir=False)


def test_varias_conversaciones_y_el_estilo_del_chat(puerto, falso):
    c = nuevo_cuaderno(puerto)
    subir(puerto, cuaderno=c["id"])
    primera = preguntar(puerto, c["id"])[-1]["conversacion"]
    seguimiento = {"pregunta": "¿Y bajo ese monto?", "conversacion": primera}
    assert preguntar(puerto, c["id"], seguimiento)[-1]["conversacion"] == primera
    otra = preguntar(puerto, c["id"], {"pregunta": "¿Quién aprueba?", "conversacion": None})[-1]["conversacion"]
    assert otra != primera
    resumen = json_de(puerto, "GET", f"/api/cuadernos/{c['id']}")["cuaderno"]["conversaciones"]
    assert [(v["id"], v["preguntas"]) for v in resumen] == [(otra, 1), (primera, 2)]
    vueltas = json_de(puerto, "GET", f"/api/cuadernos/{c['id']}/conversaciones/{primera}")["conversacion"]["vueltas"]
    assert [v["pregunta"] for v in vueltas] == [PREGUNTA["pregunta"], "¿Y bajo ese monto?"]
    ruta = f"/api/cuadernos/{c['id']}/conversaciones/{primera}"
    assert json_de(puerto, "PATCH", ruta, {"titulo": "Montos"})["conversacion"]["titulo"] == "Montos"
    assert pedir(puerto, "DELETE", ruta)[0] == 200 and pedir(puerto, "GET", ruta)[0] == 404

    falso.sistemas.clear()
    estilo = {"estilo": {"largo": "largo", "instrucciones": "Explícalo como a alguien que recién llega."}}
    assert json_de(puerto, "PATCH", f"/api/cuadernos/{c['id']}", estilo)["cuaderno"]["estilo"]["largo"] == "largo"
    preguntar(puerto, c["id"])
    respuesta = next(s for s in falso.sistemas if s.startswith("Respondes preguntas sobre los documentos"))
    assert "con detalle" in respuesta and "recién llega" in respuesta


def test_la_guia_de_una_fuente_se_escribe_por_partes_y_sugiere_preguntas(puerto, falso, monkeypatch):
    monkeypatch.setattr(estudio, "LOCAL", CHICAS)
    c = nuevo_cuaderno(puerto)
    doc = subir(puerto, "palas.md", LARGO.encode(), cuaderno=c["id"])[-1]["documento"]
    assert not doc["guia"] and not json_de(puerto, "GET", f"/api/cuadernos/{c['id']}")["cuaderno"]["sugerencias"]
    eventos = lineas(pedir(puerto, "POST", f"/api/documentos/{doc['id']}/guia", {})[2])
    pasos = [e["texto"] for e in eventos if e["tipo"] == "paso"]
    assert "Leyendo «palas.md» (parte 1 de" in pasos[0]
    assert pasos[-2:] == ["Escribiendo la guía", "Guardando la guía"]
    guia = eventos[-1]["guia"]
    assert eventos[-1]["tipo"] == "guia" and guia["resumen"] and guia["temas"] and len(guia["preguntas"]) == 3
    assert guia["modelo"] == "gpt-oss:20b" and 0 < guia["leido"] <= 1
    assert json_de(puerto, "GET", f"/api/documentos/{doc['id']}")["guia"]["resumen"] == guia["resumen"]
    cuaderno = json_de(puerto, "GET", f"/api/cuadernos/{c['id']}")["cuaderno"]
    assert cuaderno["documentos"][0]["guia"] and cuaderno["sugerencias"] == guia["preguntas"]
    # la segunda vez usa las notas de lectura guardadas: no vuelve a leer el documento
    otra_vez = lineas(pedir(puerto, "POST", f"/api/documentos/{doc['id']}/guia", {})[2])
    assert not [e for e in otra_vez if e["tipo"] == "paso" and e["texto"].startswith("Leyendo")]
    assert pedir(puerto, "POST", "/api/documentos/0123456789ab/guia", {})[0] == 404


def test_estudio_escribe_notas_con_las_fuentes_del_chat(puerto, falso, monkeypatch):
    monkeypatch.setattr(estudio, "LOCAL", CHICAS)
    c = nuevo_cuaderno(puerto)
    subir(puerto, "palas.md", LARGO.encode(), cuaderno=c["id"])
    corto = subir(puerto, cuaderno=c["id"])[-1]["documento"]
    for tipo in estudio.TIPOS:
        eventos = generar(puerto, c["id"], tipo, "Haz una lista de los plazos" if tipo == "propia" else "")
        nota = eventos[-1]["nota"]
        assert eventos[-1]["tipo"] == "nota", eventos[-1]
        assert nota["origen"] == "generada" and nota["tipo"] == tipo and nota["titulo"] and nota["html"]
        assert {f["nombre"] for f in nota["fuentes"]} == {"palas.md", "compras.md"} and nota["avisos"] == []
        assert f"Escribiendo {estudio.TIPOS[tipo].que}" in [e["texto"] for e in eventos if e["tipo"] == "paso"]
    notas = json_de(puerto, "GET", f"/api/cuadernos/{c['id']}")["cuaderno"]["notas"]
    assert len(notas) == len(estudio.TIPOS) and notas[0]["instruccion"] == "Haz una lista de los plazos"
    assert "<li>" in notas[1]["html"]  # el mapa de ideas es una lista anidada
    # solo con las fuentes que entran al chat
    json_de(puerto, "PATCH", f"/api/cuadernos/{c['id']}", {"fuera": [corto["id"]]})
    assert [f["nombre"] for f in generar(puerto, c["id"], "resumen")[-1]["nota"]["fuentes"]] == ["palas.md"]
    assert pedir(puerto, "POST", f"/api/cuadernos/{c['id']}/generar", {"tipo": "propia"})[0] == 400
    assert pedir(puerto, "POST", f"/api/cuadernos/{c['id']}/generar", {"tipo": "poema"})[0] == 400


def test_estudio_explica_lo_que_falta(puerto, falso):
    c = nuevo_cuaderno(puerto)
    assert generar(puerto, c["id"], "resumen")[-1]["texto"].startswith("Incluye al menos una fuente")
    subir(puerto, cuaderno=c["id"])
    json_de(puerto, "PUT", "/api/ajustes", {"modo": "buscar"})
    assert (
        generar(puerto, c["id"], "resumen")[-1]["texto"]
        == "Estudio la escribe un modelo: elige Ollama o una API en Modelos."
    )
    json_de(puerto, "PUT", "/api/ajustes", {"modo": "ollama"})
    falso.modelos = {"nomic-embed-text:latest"}
    assert generar(puerto, c["id"], "resumen")[-1]["texto"] == "Falta descargar gpt-oss:20b: hazlo en Modelos."


def test_cerrar_la_pagina_cancela_lo_que_se_esta_escribiendo(tmp_path, monkeypatch):
    s_falso, _, url = iniciar(demora=0.25)
    monkeypatch.setattr(ollama, "URL", url)
    monkeypatch.setattr(estudio, "LOCAL", CHICAS)
    monkeypatch.setenv("MESA_TOKEN", TOKEN)
    app = App(Biblioteca(tmp_path / "biblioteca"))
    s = crear(APP, app, 0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    p = s.server_address[1]
    try:
        c = nuevo_cuaderno(p)
        subir(p, "palas.md", LARGO.encode(), cuaderno=c["id"])
        conexion = http.client.HTTPConnection("127.0.0.1", p, timeout=10)
        cuerpo = json.dumps({"tipo": "resumen"}).encode()
        conexion.request(
            "POST",
            f"/api/cuadernos/{c['id']}/generar",
            body=cuerpo,
            headers={"Host": f"127.0.0.1:{p}", "X-Mesa-Token": TOKEN, "Content-Type": "application/json"},
        )
        respuesta = conexion.getresponse()
        assert json.loads(respuesta.readline())["tipo"] == "paso"
        respuesta.close()  # como cerrar la página o tocar «Cancelar»
        conexion.close()
        assert app._turno.acquire(timeout=10)  # el modelo quedó libre sin terminar las 12 partes
        app._turno.release()
        time.sleep(0.5)
        assert app.cuadernos.obtener(c["id"])["notas"] == []
    finally:
        s.shutdown()
        s.server_close()
        s_falso.shutdown()
        s_falso.server_close()


class _Sitio(BaseHTTPRequestHandler):
    """Un sitio web de mentira: una página, un PDF, una redirección a la red local y una página vacía."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        paginas = {
            "/politica": (
                "text/html; charset=utf-8",
                "<html><head><title>Política de compras</title></head><body><nav>Inicio · Contacto</nav>"
                "<main><h1>Política de compras</h1><p>Sobre USD 50.000 aprueba el gerente de operaciones de la "
                "faena.</p><ul><li>Bajo ese monto, el jefe de área.</li></ul></main>"
                "<script>alert(1)</script></body></html>".encode(),
            ),
            "/manual.pdf": ("application/pdf", pdf_simple(["Manual de bodega\nLa bodega abre a las 8."])),
            "/vacia": ("text/html", b"<html><body><div id='app'></div><script src='x.js'></script></body></html>"),
        }
        if self.path == "/redirige":
            self.send_response(302)
            self.send_header("Location", "http://10.0.0.1/admin")
            self.end_headers()
            return
        tipo, datos = paginas.get(self.path, ("text/plain", b""))
        self.send_response(200 if datos else 404)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)


@pytest.fixture
def sitio():
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Sitio)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()
    s.server_close()


def test_agregar_una_pagina_web_desde_su_enlace(puerto, sitio, monkeypatch):
    c = nuevo_cuaderno(puerto)

    def enlace(url):
        return lineas(pedir(puerto, "POST", "/api/enlaces", {"url": url, "cuaderno": c["id"]})[2])

    # sin permiso para la red local (como en la app de verdad), 127.0.0.1 no se puede pedir
    assert "red local" in enlace(f"{sitio}/politica")[-1]["texto"]
    monkeypatch.setattr(enlaces, "PERMITIR_LOCALES", True)
    eventos = enlace(f"{sitio}/politica")
    assert eventos[0] == {"tipo": "paso", "texto": "Descargando la página"}
    doc = eventos[-1]["documento"]
    assert doc["nombre"] == "Política de compras.md" and doc["url"] == f"{sitio}/politica"
    texto = json_de(puerto, "GET", f"/api/documentos/{doc['id']}")["html"]
    assert "gerente de operaciones" in texto and "Inicio" not in texto and "alert" not in texto
    assert [d["id"] for d in json_de(puerto, "GET", f"/api/cuadernos/{c['id']}")["cuaderno"]["documentos"]] == [
        doc["id"]
    ]
    pdf = enlace(f"{sitio}/manual.pdf")[-1]["documento"]
    assert pdf["nombre"] == "manual.pdf" and pdf["tipo"] == "pdf" and pdf["paginas"] == 1
    assert "JavaScript" in enlace(f"{sitio}/vacia")[-1]["texto"]
    assert "http://" in enlace("ftp://ejemplo.cl/archivo")[-1]["texto"]
    assert pedir(puerto, "POST", "/api/enlaces", {"url": ""})[0] == 400


def test_la_red_local_no_se_puede_pedir_ni_por_redireccion(sitio, monkeypatch):
    with pytest.raises(enlaces.ErrorEnlace, match="red local"):
        enlaces.traer(f"{sitio}/politica")
    monkeypatch.setattr(enlaces, "PERMITIR_LOCALES", True)  # llegar al sitio de prueba para comprobar la redirección
    monkeypatch.setattr(enlaces, "_ip_publica", lambda nombre: None if nombre == "127.0.0.1" else _bloquear())
    with pytest.raises(enlaces.ErrorEnlace, match="red local"):
        enlaces.traer(f"{sitio}/redirige")


def _bloquear():
    raise enlaces.ErrorEnlace("Ese enlace apunta a una dirección de la red local. Tesela solo trae páginas públicas.")


@pytest.mark.parametrize("extension", ["md", "txt", "pdf"])
def test_original_descarga_textos_y_conserva_el_visor_pdf(puerto, extension):
    datos = pdf_simple(["Texto del documento original."]) if extension == "pdf" else MD
    doc = subir(puerto, f"documento.{extension}", datos)[-1]["documento"]
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=5)
    c.request("GET", f"/api/documentos/{doc['id']}/original", headers={"Host": f"127.0.0.1:{puerto}"})
    respuesta = c.getresponse()
    disposicion = "inline" if extension == "pdf" else "attachment"
    assert respuesta.getheader("Content-Disposition").startswith(disposicion)
    assert respuesta.read() == datos
    c.close()


def test_un_html_subido_se_descarga_y_no_se_abre_en_la_app(puerto):
    html_ = b"<html><head><title>Hola</title></head><body><p>Texto de la pagina con varias palabras.</p></body></html>"
    doc = subir(puerto, "pagina.html", html_)[-1]["documento"]
    assert doc["tipo"] == "html"
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=5)
    c.request("GET", f"/api/documentos/{doc['id']}/original", headers={"Host": f"127.0.0.1:{puerto}"})
    assert c.getresponse().getheader("Content-Disposition").startswith("attachment")
