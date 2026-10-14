from rag_local import ollama


def test_prefijos_de_nomic_para_documentos_y_consultas(monkeypatch):
    recibidos = []
    monkeypatch.setattr(ollama, "embeber", lambda textos, modelo: recibidos.append((list(textos), modelo)))
    monkeypatch.setattr(ollama, "MODELO_EMBEDDINGS", "nomic-embed-text:latest")
    ollama.embeber_documentos(["texto"])
    ollama.embeber_consulta(["pregunta"])
    assert recibidos == [
        (["search_document: texto"], "nomic-embed-text:latest"),
        (["search_query: pregunta"], "nomic-embed-text:latest"),
    ]
    monkeypatch.setattr(ollama, "MODELO_EMBEDDINGS", "otro-modelo")
    ollama.embeber_consulta(["pregunta"])
    assert recibidos[-1] == (["pregunta"], "otro-modelo")


def test_nivel_de_razonamiento_solo_para_gpt_oss():
    assert ollama.cuerpo_chat("s", "u", "gpt-oss:20b", "low")["think"] == "low"
    assert "think" not in ollama.cuerpo_chat("s", "u", "gemma4:12b", "low")
    assert "think" not in ollama.cuerpo_chat("s", "u", "gpt-oss:20b")
    assert ollama.cuerpo_chat("s", "u", "m")["options"]["temperature"] == 0


def test_sin_soporte_de_razonamiento_reintenta_sin_el(monkeypatch):
    cuerpos = []

    def post(ruta, cuerpo, timeout=900):
        cuerpos.append(cuerpo)
        if "think" in cuerpo:
            raise ollama.ErrorOllama(400, "think no soportado")
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(ollama, "_post", post)
    assert ollama.chatear("s", "u", "gpt-oss:20b", "low") == "ok"
    assert len(cuerpos) == 2 and "think" not in cuerpos[1]
