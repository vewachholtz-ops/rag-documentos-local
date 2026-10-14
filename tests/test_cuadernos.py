"""Cuadernos y ajustes guardados en disco: sobreviven a reiniciar la app y no se rompen con datos raros."""

import json

from rag_local.cuadernos import LARGO_NOMBRE, Cuadernos
from rag_local.proveedores import Proveedores


def test_se_guardan_y_se_vuelven_a_leer(tmp_path):
    c = Cuadernos(tmp_path).crear("  Contratos  ", "Del 2026", ["a" * 12, "a" * 12, "b" * 12])
    assert c["nombre"] == "Contratos" and c["documentos"] == ["a" * 12, "b" * 12]
    Cuadernos(tmp_path).crear_nota(c["id"], "Plazo", "30 días", origen="respuesta")
    otra_vez = Cuadernos(tmp_path).obtener(c["id"])
    assert otra_vez["notas"][0]["titulo"] == "Plazo" and otra_vez["notas"][0]["origen"] == "respuesta"


def test_un_archivo_roto_no_impide_abrir_los_demas(tmp_path):
    bien = Cuadernos(tmp_path).crear("Bien")
    (tmp_path / "cuadernos" / "0123456789ab.json").write_text("{roto", encoding="utf-8")
    assert [c["nombre"] for c in Cuadernos(tmp_path).lista()] == [bien["nombre"]]


def test_limites_y_valores_por_omision(tmp_path):
    cs = Cuadernos(tmp_path)
    c = cs.crear("x" * 500)
    assert len(c["nombre"]) == LARGO_NOMBRE
    assert cs.crear("   ")["nombre"] == "Cuaderno sin nombre"
    assert cs.cambiar(c["id"], {"nombre": ""})["nombre"] == c["nombre"]  # vacío no borra el nombre
    assert cs.crear_nota(c["id"], "t", "c", origen="cualquiera")["origen"] == "propia"
    conversacion = None
    for i in range(205):
        conversacion, _ = cs.agregar_vuelta(c["id"], conversacion, {"pregunta": str(i), "modo": "buscar"})
    vueltas = cs.conversacion(c["id"], conversacion)["vueltas"]
    assert len(vueltas) == 205 and vueltas[0]["pregunta"] == "0" and vueltas[-1]["pregunta"] == "204"
    for i in range(53):
        cs.agregar_vuelta(c["id"], None, {"pregunta": f"nueva {i}", "modo": "buscar"})
    assert len(cs.conversaciones(c["id"])) == 54
    assert cs.conversaciones(c["id"])[0]["titulo"] == "nueva 52"
    assert len(Cuadernos(tmp_path).conversacion(c["id"], conversacion)["vueltas"]) == 205


def test_fuera_solo_admite_documentos_del_cuaderno(tmp_path):
    cs = Cuadernos(tmp_path)
    c = cs.crear("C", documentos=["a" * 12, "b" * 12])
    assert cs.cambiar(c["id"], {"fuera": ["b" * 12, "z" * 12]})["fuera"] == ["b" * 12]
    assert cs.para_el_chat(c["id"]) == ["a" * 12]
    cs.olvidar_documento("b" * 12)
    assert cs.obtener(c["id"])["fuera"] == [] and cs.obtener(c["id"])["documentos"] == ["a" * 12]


def test_el_historial_es_de_las_vueltas_con_ia_de_esa_conversacion(tmp_path):
    cs = Cuadernos(tmp_path)
    c = cs.crear("C")
    uno = {"pregunta": "uno", "modo": "ollama", "respuesta": {"texto": "Respuesta uno"}}
    conversacion, _ = cs.agregar_vuelta(c["id"], None, uno)
    cs.agregar_vuelta(c["id"], conversacion, {"pregunta": "dos", "modo": "buscar", "pasajes": {"pasajes": []}})
    otra, _ = cs.agregar_vuelta(c["id"], None, {"pregunta": "tres", "modo": "ollama", "respuesta": {"texto": "x"}})
    assert cs.historial(c["id"], conversacion) == [{"pregunta": "uno", "respuesta": "Respuesta uno"}]
    assert cs.historial(c["id"], otra) == [{"pregunta": "tres", "respuesta": "x"}]
    assert cs.historial(c["id"], None) == [] and cs.historial(c["id"], "0123456789ab") == []


def test_varias_conversaciones(tmp_path):
    cs = Cuadernos(tmp_path)
    c = cs.crear("C")
    pregunta = "¿Quién aprueba las compras sobre USD 50.000 en la faena y cuánto demora la aprobación en total?"
    primera, _ = cs.agregar_vuelta(c["id"], None, {"pregunta": pregunta, "modo": "buscar"})
    segunda, _ = cs.agregar_vuelta(c["id"], None, {"pregunta": "Plazos", "modo": "buscar"})
    resumen = cs.conversaciones(c["id"])
    assert [v["id"] for v in resumen] == [segunda, primera] and resumen[1]["preguntas"] == 1
    assert len(resumen[1]["titulo"]) == 80 and resumen[1]["titulo"].endswith("…")
    assert cs.renombrar_conversacion(c["id"], primera, "  Compras  ")["titulo"] == "Compras"
    assert cs.renombrar_conversacion(c["id"], primera, "")["titulo"] == "Compras"  # vacío no borra el título
    cs.borrar_conversacion(c["id"], segunda)
    assert [v["titulo"] for v in Cuadernos(tmp_path).conversaciones(c["id"])] == ["Compras"]


def test_un_cuaderno_con_una_sola_conversacion_se_pasa_al_formato_nuevo(tmp_path):
    carpeta = tmp_path / "cuadernos"
    carpeta.mkdir()
    viejo = {
        "id": "0123456789ab", "nombre": "Viejo", "descripcion": "", "creado": "2026-10-01T10:00:00",
        "actualizado": "2026-10-02T10:00:00", "documentos": [], "fuera": [], "notas": [],
        "conversacion": [{"id": "v1", "creado": "2026-10-02T09:00:00", "pregunta": "¿Hola?", "modo": "buscar"}],
    }  # fmt: skip
    (carpeta / "0123456789ab.json").write_text(json.dumps(viejo), encoding="utf-8")
    cs = Cuadernos(tmp_path)
    (resumen,) = cs.conversaciones("0123456789ab")
    assert resumen["titulo"] == "¿Hola?" and resumen["preguntas"] == 1
    assert cs.obtener("0123456789ab")["estilo"] == {"largo": "normal", "instrucciones": ""}
    guardado = json.loads((carpeta / "0123456789ab.json").read_text(encoding="utf-8"))
    assert "conversacion" not in guardado and len(guardado["conversaciones"]) == 1


def test_el_estilo_del_chat(tmp_path):
    cs = Cuadernos(tmp_path)
    c = cs.crear("C")
    assert cs.cambiar(c["id"], {"estilo": {"largo": "largo", "instrucciones": " Como profesor "}})["estilo"] == {
        "largo": "largo",
        "instrucciones": "Como profesor",
    }
    assert cs.cambiar(c["id"], {"estilo": {"largo": "enorme"}})["estilo"]["largo"] == "normal"
    assert cs.obtener(c["id"])["estilo"]["instrucciones"] == "Como profesor"  # lo que no se manda se mantiene


def test_una_nota_generada_guarda_de_donde_salio(tmp_path):
    cs = Cuadernos(tmp_path)
    c = cs.crear("C")
    extra = {"tipo": "guia", "fuentes": [{"id": "a" * 12, "nombre": "a.md"}], "modelo": "m", "otra": 1}
    nota = cs.crear_nota(c["id"], "Guía", "# x", "generada", extra)
    assert nota["origen"] == "generada" and nota["tipo"] == "guia" and nota["fuentes"][0]["nombre"] == "a.md"
    assert "otra" not in nota


def test_la_clave_de_la_api_queda_aparte_y_no_se_muestra(tmp_path):
    p = Proveedores(tmp_path)
    p.cambiar({"modo": "openai", "openai": {"url": "https://api.example.com/v1", "modelo": "m", "clave": "sk-1"}})
    publico = Proveedores(tmp_path).publico()
    assert publico["modo"] == "openai" and publico["openai"]["hay_clave"] and not publico["openai"]["local"]
    assert "sk-1" not in (tmp_path / "ajustes.json").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "ajustes-secretos.json").read_text(encoding="utf-8")) == {"clave": "sk-1"}
    p.cambiar({"openai": {"clave": ""}})
    assert not (tmp_path / "ajustes-secretos.json").exists() and not p.publico()["openai"]["hay_clave"]
