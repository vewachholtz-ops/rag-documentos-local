from rag_local.resaltar import marcar, ubicar, ubicar_todas

TABLA = "| Monto | Quién aprueba |\n|---|---|\n| Más de USD 50.000 y hasta USD 250.000 | Gerente de operaciones |"


def test_ubicar_ignora_tildes_mayusculas_y_miles():
    texto = "El material dañado se deja en la zona de cuarentena (zona Q)."
    a, b = ubicar(texto, "material DANADO se deja")
    assert texto[a:b] == "material dañado se deja"
    a, b = ubicar("Hasta USD 30.000 por teléfono.", "hasta usd 30\u202f000")
    assert "30.000" in "Hasta USD 30.000 por teléfono."[a:b]
    assert ubicar("Texto cualquiera.", "otra frase") is None and ubicar("x", "  ") is None


def test_marcar_respeta_las_celdas_de_la_tabla():
    m = marcar(TABLA, ["Más de USD 50.000 y hasta USD 250.000 | Gerente de operaciones"])
    assert "| <mark>Más de USD 50.000 y hasta USD 250.000</mark> | <mark>Gerente de operaciones</mark> |" in m
    assert m.count("|") == TABLA.count("|")  # la tabla sigue entera


def test_marcar_escapa_html_y_une_tramos():
    m = marcar("a < b y c > d, luego e", ["b y c", "c > d"])
    assert m == "a &lt; <mark>b y c &gt; d</mark>, luego e"
    assert ubicar_todas("uno dos tres cuatro", ["dos … cuatro"]) == [(4, 7), (13, 19)]
