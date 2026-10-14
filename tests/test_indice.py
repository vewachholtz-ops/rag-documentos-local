import numpy as np
import pytest
from conftest import RAIZ, embedder_falso

from rag_local.busqueda import Busqueda, buscar, fusionar, reescribir, reordenar
from rag_local.cache import CacheEmbeddings, CacheLLM
from rag_local.contexto import agregar_contexto
from rag_local.indice import BM25, Indice, cargar_documentos, es_obsoleto, tokens, trocear_markdown


# ---------------- carga, vigencia y troceo ----------------
def test_carga_sin_readme_ni_obsoletos(trozos):
    docs = {t.documento for t in trozos}
    assert len(docs) == 23 and "README.md" not in docs
    assert "PR-COM-01-v4-solicitud-de-compra.md" not in docs  # versión obsoleta, reemplazada por la 5
    todos = cargar_documentos(RAIZ / "documentos", incluir_obsoletos=True)
    assert "PR-COM-01-v4-solicitud-de-compra.md" in todos and len(todos) == 24


@pytest.mark.parametrize(
    ("linea", "esperado"),
    [
        ("Estado: obsoleto.", True),
        ("**Estado:** Obsoleta", True),
        ("estado:obsoleto", True),
        ("Estado: vigente", False),
    ],
)
def test_es_obsoleto(linea, esperado):
    assert es_obsoleto(f"# Doc\n\nVersión 1.\n\n{linea}\n\n## Alcance\n\nTexto.") is esperado


def test_troceo_por_secciones(tabla_compras):
    assert "USD 250.000" in tabla_compras.texto and "Gerente general" in tabla_compras.texto  # la tabla queda junta
    assert tabla_compras.titulo == "PR-COM-01 Solicitud de compra y aprobaciones > Niveles de aprobación"
    assert tabla_compras.seccion == "Niveles de aprobación"


def test_seccion_larga_se_parte_sin_perder_texto():
    md = "# Doc\n\n## Larga\n\n" + "\n\n".join(f"Párrafo {i} " + "palabra " * 60 for i in range(5))
    partes = trocear_markdown("doc.md", md, max_palabras=150)
    assert len(partes) == 3 and all(p.seccion == "Larga" for p in partes)
    assert sum(t.texto.count("Párrafo") for t in partes) == 5
    assert all(len(t.texto.split()) <= 150 for t in partes)


# ---------------- BM25, vectores y fusión ----------------
def test_tokens_normalizan_tildes_y_miles():
    assert tokens("Aprobación de USD 5.000 en Bodega") == ["aprobacion", "usd", "5000", "bodega"]


def test_bm25_prefiere_el_documento_con_mas_coincidencias_raras():
    b = BM25(["el camion de extraccion", "el chancador primario", "camion camion aceite"])
    s = b.puntajes("aceite del camion")
    assert s.argmax() == 2 and s[1] == 0


@pytest.mark.parametrize("modo", ["bm25", "vector", "hibrido"])
def test_busqueda_encuentra_la_seccion(indice, modo):
    r = indice.buscar("¿Cuántas cotizaciones necesito para comprar algo de USD 12.000?", 3, embedder_falso, modo)
    assert ("PR-COM-01-solicitud-de-compra.md", "Cotizaciones") in [(x.trozo.documento, x.trozo.seccion) for x in r]


def test_vectores_rescatan_sinonimos_que_bm25_no_ve(indice):
    assert indice.bm25.puntajes("lubricante").max() == 0  # ningún documento usa esa palabra
    r = indice.buscar("lubricante", k=1, embedder=embedder_falso, modo="vector")
    assert "aceite" in r[0].trozo.texto.lower()  # el embedder simulado la acerca a "aceite"


def test_fusion_por_rango_reciproco(indice):
    r = indice.buscar("candado rojo", k=4, embedder=embedder_falso, modo="hibrido")
    for x in r:
        assert x.puntaje == pytest.approx(1 / (60 + x.rango_bm25) + 1 / (60 + x.rango_vector))
    assert [x.puntaje for x in r] == sorted((x.puntaje for x in r), reverse=True)


def test_sin_embeddings_el_modo_vector_avisa(trozos):
    with pytest.raises(ValueError):
        Indice.construir(trozos, None).buscar("x", modo="vector")


def test_guardar_y_cargar_con_contexto(trozos, tmp_path):
    con = agregar_contexto(trozos[:3], cargar_documentos(RAIZ / "documentos"), lambda s, u: "  Un\ncontexto.  ")
    indice = Indice.construir(con, embedder_falso)
    indice.guardar(tmp_path)
    otro = Indice.cargar(tmp_path)
    assert otro.trozos == indice.trozos and otro.trozos[0].contexto == "Un contexto."
    assert np.allclose(otro.vectores, indice.vectores)


# ---------------- Contextual Retrieval ----------------
def test_contexto_se_indexa_y_cambia_la_busqueda(trozos):
    documentos = cargar_documentos(RAIZ / "documentos")
    palas = [t for t in trozos if t.documento.startswith("PR-MAN-0")]
    recibidos = []

    def chat(sistema, usuario):
        recibidos.append(usuario)
        return "Pauta de las palas eléctricas." if "palas" in usuario.split("<trozo>")[0] else "Camiones de extracción."

    con = agregar_contexto(palas, documentos, chat)
    assert "<documento>" in recibidos[0] and palas[0].texto in recibidos[0]  # recibe el documento completo
    tol = next(t for t in con if t.documento.startswith("PR-MAN-03") and t.seccion == "Tolerancia")
    assert tol.contexto == "Pauta de las palas eléctricas." and tol.texto_indice.count("\n") >= 2
    r = Indice.construir(con, None).buscar("tolerancia palas eléctricas", k=1, modo="bm25")
    assert r[0].trozo == tol


def test_cache_llm_no_repite_llamadas(tmp_path):
    llamadas = []

    def chat(sistema, usuario):
        llamadas.append(usuario)
        return f"respuesta a {usuario}"

    c = CacheLLM(chat, tmp_path / "c.jsonl", "modelo-x")
    assert c("s", "hola") == c("s", "hola") == "respuesta a hola"
    assert len(llamadas) == 1 and c.llamadas == 1
    otra = CacheLLM(chat, tmp_path / "c.jsonl", "modelo-x")  # retoma desde el archivo
    assert otra("s", "hola") == "respuesta a hola" and len(llamadas) == 1
    assert CacheLLM(chat, tmp_path / "c.jsonl", "modelo-y")("s", "hola") and len(llamadas) == 2  # otro modelo


# ---------------- reescritura y reordenamiento ----------------
def test_reescribir_limpia_las_lineas():
    salida = "1. repuesto sin movimiento\n- inventario obsoleto 24 meses\n\n¿Qué pasa con la pieza?\n"
    salida += "• repuesto sin movimiento"
    assert reescribir("¿Qué pasa con la pieza?", lambda s, u: salida) == [
        "repuesto sin movimiento",
        "inventario obsoleto 24 meses",
    ]


def test_reescribir_rescata_la_pregunta_coloquial(indice):
    pregunta = "Tengo una pieza que lleva dos años sin moverse en el almacén, ¿qué pasa con ella?"
    config = Busqueda("bm25", reescribir=True)
    consultas = "repuesto sin movimiento\ninventario obsoleto\nrepuesto obsoleto 24 meses"
    sin = buscar(indice, pregunta, 3, None, Busqueda("bm25"))
    con = buscar(indice, pregunta, 3, None, config, lambda s, u: consultas)
    correcta = ("PR-INV-01-politica-de-inventario.md", "Inventario obsoleto")
    assert correcta not in [(r.trozo.documento, r.trozo.seccion) for r in sin]  # BM25 solo no la encuentra
    assert correcta == (con[0].trozo.documento, con[0].trozo.seccion)


def test_fusion_de_varias_consultas(indice):
    a = indice.buscar("candado rojo", k=3, modo="bm25")
    b = indice.buscar("curso de bloqueo", k=3, modo="bm25")
    f = fusionar([a, b])
    assert len({x.trozo.id for x in f}) == len(f)
    comunes = {x.trozo.id for x in a} & {x.trozo.id for x in b}
    if comunes:  # un trozo que aparece en las dos listas sube
        assert f[0].trozo.id in comunes


def test_reordenar_sigue_el_orden_del_modelo(indice):
    c = indice.buscar("candado", k=4, modo="bm25")
    assert reordenar("x", c, lambda s, u: "3, 1") == [c[2], c[0], c[1], c[3]]
    assert reordenar("x", c, lambda s, u: "no sé") == c  # si no entrega números, queda igual
    assert reordenar("x", c, lambda s, u: "9, 2, 2") == [c[1], c[0], c[2], c[3]]  # ignora los que no existen


def test_buscar_reordena_entre_mas_candidatos(indice):
    vistos = []

    def chat(sistema, usuario):
        vistos.append(usuario)
        return "20"

    r = buscar(indice, "candado", 2, None, Busqueda("bm25", reordenar=True, candidatos=20), chat)
    assert "[20] " in vistos[0] and "[21] " not in vistos[0]  # el modelo ve 20 candidatos
    assert len(r) == 2 and r[0] == indice.buscar("candado", 20, modo="bm25")[19]


def test_reescribir_sin_modelo_avisa(indice):
    with pytest.raises(ValueError):
        buscar(indice, "x", 3, None, Busqueda("bm25", reescribir=True))


def test_cache_llm_suma_lo_ahorrado(tmp_path):
    c = CacheLLM(lambda s, u: "r", tmp_path / "c.jsonl", "m")
    c("s", "u")
    otra = CacheLLM(lambda s, u: "r", tmp_path / "c.jsonl", "m")
    otra("s", "u")
    assert otra.llamadas == 0 and otra.ahorrados == c.duracion[next(iter(c.duracion))]


def test_una_reescritura_sola_no_le_gana_a_la_pregunta(indice):
    pregunta = "¿De qué color son los candados personales?"
    original = buscar(indice, pregunta, 1, None, Busqueda("bm25"))[0]
    r = buscar(indice, pregunta, 1, None, Busqueda("bm25", reescribir=True), lambda s, u: "residuos peligrosos")
    assert r[0] == original


def test_cache_de_embeddings(tmp_path):
    llamadas = []

    def embedder(textos):
        llamadas.append(list(textos))
        return embedder_falso(textos)

    c = CacheEmbeddings(embedder, tmp_path / "e.jsonl", "m")
    a = c(["hola", "chao"])
    b = CacheEmbeddings(embedder, tmp_path / "e.jsonl", "m")(["chao", "nuevo"])
    assert llamadas == [["hola", "chao"], ["nuevo"]]
    assert np.allclose(a[1], b[0], atol=1e-6) and a.shape == (2, 4096)
