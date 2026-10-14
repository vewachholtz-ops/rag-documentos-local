"""Responder en la app: la conversación, la búsqueda sobre la biblioteca y lo que llega a la página."""

from conftest import embedder_falso

from rag_local.asistente import SISTEMA_CONDENSAR, condensar, responder_en_biblioteca
from rag_local.biblioteca import Biblioteca
from rag_local.busqueda import SISTEMA_REESCRIBIR_GENERAL, SISTEMA_REORDENAR_GENERAL
from rag_local.responder import SISTEMA_GENERAL

MD = (
    "# Compras\n\n## Aprobaciones\n\nSobre USD 50.000 aprueba el gerente de operaciones.\n\n"
    "## Viajes\n\nEl viático diario es de CLP 40.000."
)


def test_condensar_solo_si_hay_conversacion():
    llamadas = []

    def chat(sistema, usuario):
        llamadas.append((sistema, usuario))
        return '"¿Quién aprueba una compra de USD 300.000?"'

    assert condensar("¿Quién aprueba?", [], chat) == "¿Quién aprueba?" and not llamadas
    historial = [{"pregunta": "¿Quién aprueba una compra de USD 150.000?", "respuesta": "El gerente [1]."}]
    assert condensar("¿y si es de USD 300.000?", historial, chat) == "¿Quién aprueba una compra de USD 300.000?"
    assert llamadas[0][0] == SISTEMA_CONDENSAR and "El gerente ." in llamadas[0][1]  # sin las citas
    assert condensar("¿y?", historial, lambda s, u: "x" * 500) == "¿y?"  # una reescritura rara no se usa


def test_responde_con_la_biblioteca_y_dice_de_donde_viene(tmp_path):
    b = Biblioteca(tmp_path)
    doc = b.agregar("compras.md", MD.encode(), embedder_falso, "falso", lambda _e: None)
    sistemas, pasos = [], []

    def chat(sistema, usuario):
        sistemas.append(sistema)
        if sistema == SISTEMA_REESCRIBIR_GENERAL:
            return "aprobación de compras\ngerente de operaciones"
        if sistema == SISTEMA_REORDENAR_GENERAL:
            return "1, 2"
        if sistema == SISTEMA_CONDENSAR:
            return "¿Quién aprueba una compra de USD 60.000?"
        return 'Aprueba el gerente de operaciones [1].\n\n[1] "Sobre USD 50.000 aprueba el gerente de operaciones"'

    historial = [{"pregunta": "¿Cómo se compra?", "respuesta": "Con una solicitud."}]
    r = responder_en_biblioteca(
        b, "¿y si es de USD 60.000?", None, historial, chat, chat, embedder_falso, avisar=pasos.append
    )
    assert pasos[0] == "Leyendo la conversación" and "Buscando en tus documentos" in pasos
    assert pasos[-1].startswith("Leyendo") and "redactando" in pasos[-1]
    assert SISTEMA_GENERAL in sistemas and r["consulta"] == "¿Quién aprueba una compra de USD 60.000?"
    citada = r["fuentes"][0]
    assert citada["citada"] and citada["doc_id"] == doc["id"] and citada["seccion"] == "Aprobaciones"
    assert citada["documento"] == "compras.md" and citada["pagina"] is None and "<mark>" in citada["html"]
    assert r["texto"].startswith("Aprueba el gerente") and "<button" in r["html"]


def test_sin_busqueda_a_fondo_no_reescribe_ni_reordena(tmp_path):
    b = Biblioteca(tmp_path)
    b.agregar("compras.md", MD.encode(), embedder_falso, "falso", lambda _e: None)
    sistemas = []

    def chat(sistema, usuario):
        sistemas.append(sistema)
        return "No está en los documentos."

    r = responder_en_biblioteca(b, "¿Qué color?", None, [], chat, chat, embedder_falso, a_fondo=False)
    assert sistemas == [SISTEMA_GENERAL] and r["abstencion"] and r["consulta"] is None
