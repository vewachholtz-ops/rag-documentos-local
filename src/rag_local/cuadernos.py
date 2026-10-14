"""Cuadernos: un tema con sus documentos, sus notas y sus conversaciones (como los cuadernos de NotebookLM y
de Open Notebook).

Los documentos viven en la Biblioteca y un cuaderno solo los enlaza por id: el mismo documento puede estar en
varios cuadernos, y sacarlo de uno no lo borra. Cada cuaderno es un JSON en biblioteca/cuadernos/, escrito de
forma atómica (archivo temporal y reemplazo) para que un corte a mitad no lo deje roto.

Un cuaderno guarda también cómo responder en su chat (`estilo`: largo de las respuestas e indicaciones propias).
Los de Fuente 3, con una sola conversación, se pasan solos al formato de varias conversaciones al abrirlos.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

LARGO_NOMBRE = 120
LARGO_DESCRIPCION = 1_000
LARGO_TITULO_NOTA = 200
LARGO_NOTA = 50_000
LARGO_TITULO_CONVERSACION = 80
LARGO_INSTRUCCIONES = 600
LARGOS = ("corto", "normal", "largo")
ORIGENES = ("propia", "respuesta", "generada")
EXTRAS_NOTA = ("tipo", "fuentes", "modelo", "leido", "avisos", "instruccion")


class NoExiste(Exception):
    pass


def _ahora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _texto(valor, maximo: int) -> str:
    return str(valor or "").strip()[:maximo]


def _titulo(pregunta: str) -> str:
    texto = " ".join(str(pregunta).split())
    return texto if len(texto) <= LARGO_TITULO_CONVERSACION else texto[: LARGO_TITULO_CONVERSACION - 1] + "…"


def _migrar(c: dict) -> bool:
    """Lleva un cuaderno guardado por una versión anterior al formato de hoy. Devuelve si cambió algo."""
    cambio = False
    if "conversaciones" not in c:
        vueltas = c.pop("conversacion", None) or []
        c["conversaciones"] = []
        if vueltas:
            c["conversaciones"].append(
                {
                    "id": _id(),
                    "titulo": _titulo(vueltas[0].get("pregunta", "Conversación")),
                    "creado": vueltas[0].get("creado", c.get("creado", _ahora())),
                    "actualizado": vueltas[-1].get("creado", c.get("actualizado", _ahora())),
                    "vueltas": vueltas,
                }
            )
        cambio = True
    if not isinstance(c.get("estilo"), dict):
        c["estilo"] = {"largo": "normal", "instrucciones": ""}
        cambio = True
    return cambio


class Cuadernos:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta) / "cuadernos"
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._cerrojo = threading.RLock()
        self._todos: dict[str, dict] = {}
        for ruta in sorted(self.carpeta.glob("*.json")):
            try:
                c = json.loads(ruta.read_text(encoding="utf-8"))
            except ValueError:
                continue  # uno roto no impide abrir los demás
            if isinstance(c, dict) and c.get("id") == ruta.stem:
                self._todos[c["id"]] = c
                if _migrar(c):
                    self._guardar(c)

    # ---- consulta ----
    def lista(self) -> list[dict]:
        """Resumen de cada cuaderno, el que se tocó último primero."""
        with self._cerrojo:
            resumen = [
                {
                    **{k: c[k] for k in ("id", "nombre", "descripcion", "creado", "actualizado")},
                    "fuentes": len(c["documentos"]),
                    "notas": len(c["notas"]),
                }
                for c in self._todos.values()
            ]
        return sorted(resumen, key=lambda c: c["actualizado"], reverse=True)

    def obtener(self, cid: str) -> dict:
        with self._cerrojo:
            if cid not in self._todos:
                raise NoExiste(cid)
            return json.loads(json.dumps(self._todos[cid]))  # copia profunda: quien lo recibe no lo altera

    def historial(self, cid: str, conversacion: str | None, vueltas: int = 2) -> list[dict]:
        """Las últimas vueltas de la conversación respondidas con IA, como las pide asistente.condensar."""
        if not conversacion:
            return []
        try:
            todas = self.conversacion(cid, conversacion)["vueltas"]
        except NoExiste:
            return []
        con_ia = [v for v in todas if v.get("respuesta")]
        return [{"pregunta": v["pregunta"], "respuesta": v["respuesta"].get("texto", "")} for v in con_ia[-vueltas:]]

    # ---- cuadernos ----
    def crear(self, nombre: str, descripcion: str = "", documentos: list[str] | None = None) -> dict:
        ahora = _ahora()
        c = {
            "id": _id(),
            "nombre": _texto(nombre, LARGO_NOMBRE) or "Cuaderno sin nombre",
            "descripcion": _texto(descripcion, LARGO_DESCRIPCION),
            "creado": ahora,
            "actualizado": ahora,
            "documentos": list(dict.fromkeys(documentos or [])),
            "fuera": [],  # documentos del cuaderno que no entran al chat
            "notas": [],
            "conversaciones": [],
            "estilo": {"largo": "normal", "instrucciones": ""},
        }
        with self._cerrojo:
            self._todos[c["id"]] = c
            self._guardar(c)
        return self.obtener(c["id"])

    def cambiar(self, cid: str, cambios: dict) -> dict:
        with self._cerrojo:
            c = self._de(cid)
            if "nombre" in cambios:
                c["nombre"] = _texto(cambios["nombre"], LARGO_NOMBRE) or c["nombre"]
            if "descripcion" in cambios:
                c["descripcion"] = _texto(cambios["descripcion"], LARGO_DESCRIPCION)
            if isinstance(cambios.get("fuera"), list):
                c["fuera"] = [d for d in c["documentos"] if d in {str(x) for x in cambios["fuera"]}]
            if isinstance(cambios.get("estilo"), dict):
                nuevo = cambios["estilo"]
                largo = nuevo.get("largo", c["estilo"]["largo"])
                c["estilo"] = {
                    "largo": largo if largo in LARGOS else "normal",
                    "instrucciones": _texto(
                        nuevo.get("instrucciones", c["estilo"]["instrucciones"]), LARGO_INSTRUCCIONES
                    ),
                }
            self._tocar(c)
            return self.obtener(cid)

    def borrar(self, cid: str) -> None:
        with self._cerrojo:
            self._de(cid)
            del self._todos[cid]
            (self.carpeta / f"{cid}.json").unlink(missing_ok=True)

    # ---- documentos ----
    def enlazar(self, cid: str, doc_id: str) -> dict:
        with self._cerrojo:
            c = self._de(cid)
            if doc_id not in c["documentos"]:
                c["documentos"].append(doc_id)
            self._tocar(c)
            return self.obtener(cid)

    def desenlazar(self, cid: str, doc_id: str) -> dict:
        with self._cerrojo:
            c = self._de(cid)
            if doc_id not in c["documentos"]:
                raise NoExiste(doc_id)
            c["documentos"].remove(doc_id)
            c["fuera"] = [d for d in c["fuera"] if d != doc_id]
            self._tocar(c)
            return self.obtener(cid)

    def olvidar_documento(self, doc_id: str) -> None:
        """Al borrar un documento de la biblioteca, sale de todos los cuadernos."""
        with self._cerrojo:
            for c in self._todos.values():
                if doc_id in c["documentos"]:
                    c["documentos"].remove(doc_id)
                    c["fuera"] = [d for d in c["fuera"] if d != doc_id]
                    self._guardar(c)

    def cuadernos_de(self) -> dict[str, list[dict]]:
        """Para cada documento, en qué cuadernos está (id y nombre)."""
        with self._cerrojo:
            salida: dict[str, list[dict]] = {}
            for c in self._todos.values():
                for d in c["documentos"]:
                    salida.setdefault(d, []).append({"id": c["id"], "nombre": c["nombre"]})
            return salida

    def para_el_chat(self, cid: str) -> list[str]:
        c = self.obtener(cid)
        return [d for d in c["documentos"] if d not in c["fuera"]]

    # ---- notas ----
    def crear_nota(
        self, cid: str, titulo: str, contenido: str, origen: str = "propia", extra: dict | None = None
    ) -> dict:
        """Una nota propia, una respuesta guardada o una nota generada en Estudio (con `extra`: el tipo, las
        fuentes, el modelo, cuánto se leyó y las cifras que no se encontraron en las fuentes)."""
        ahora = _ahora()
        nota = {
            "id": _id(),
            "titulo": _texto(titulo, LARGO_TITULO_NOTA),
            "contenido": str(contenido or "")[:LARGO_NOTA],
            "origen": origen if origen in ORIGENES else "propia",
            "creado": ahora,
            "actualizado": ahora,
        }
        if extra:
            nota |= {k: extra[k] for k in EXTRAS_NOTA if k in extra}
        with self._cerrojo:
            c = self._de(cid)
            c["notas"].insert(0, nota)
            self._tocar(c)
        return dict(nota)

    def cambiar_nota(self, cid: str, nid: str, cambios: dict) -> dict:
        with self._cerrojo:
            c = self._de(cid)
            nota = next((n for n in c["notas"] if n["id"] == nid), None)
            if nota is None:
                raise NoExiste(nid)
            if "titulo" in cambios:
                nota["titulo"] = _texto(cambios["titulo"], LARGO_TITULO_NOTA)
            if "contenido" in cambios:
                nota["contenido"] = str(cambios["contenido"] or "")[:LARGO_NOTA]
            nota["actualizado"] = _ahora()
            self._tocar(c)
            return dict(nota)

    def borrar_nota(self, cid: str, nid: str) -> None:
        with self._cerrojo:
            c = self._de(cid)
            antes = len(c["notas"])
            c["notas"] = [n for n in c["notas"] if n["id"] != nid]
            if len(c["notas"]) == antes:
                raise NoExiste(nid)
            self._tocar(c)

    # ---- conversaciones ----
    def conversaciones(self, cid: str) -> list[dict]:
        """Resumen de cada conversación, la usada último primero."""
        with self._cerrojo:
            todas = [
                {**{k: v[k] for k in ("id", "titulo", "creado", "actualizado")}, "preguntas": len(v["vueltas"])}
                for v in self._de(cid)["conversaciones"]
            ]
        return todas[::-1]  # la lista se guarda de la menos a la más usada

    def conversacion(self, cid: str, conversacion: str) -> dict:
        with self._cerrojo:
            return json.loads(json.dumps(self._conversacion(self._de(cid), conversacion)))

    def agregar_vuelta(self, cid: str, conversacion: str | None, vuelta: dict) -> tuple[str, dict]:
        """Agrega la vuelta a la conversación; si no se dice cuál (o ya no existe), empieza una nueva con la
        pregunta como título. Devuelve el id de la conversación y la vuelta."""
        vuelta = {"id": _id(), "creado": _ahora(), **vuelta}
        with self._cerrojo:
            c = self._de(cid)
            actual = next((v for v in c["conversaciones"] if v["id"] == conversacion), None)
            if actual is None:
                actual = {
                    "id": _id(),
                    "titulo": _titulo(vuelta.get("pregunta", "")) or "Conversación",
                    "creado": vuelta["creado"],
                    "actualizado": vuelta["creado"],
                    "vueltas": [],
                }
            else:
                c["conversaciones"].remove(actual)
            c["conversaciones"].append(actual)  # la más usada queda al final
            actual["vueltas"].append(vuelta)
            actual["actualizado"] = vuelta["creado"]
            self._tocar(c)
            return actual["id"], vuelta

    def renombrar_conversacion(self, cid: str, conversacion: str, titulo: str) -> dict:
        with self._cerrojo:
            c = self._de(cid)
            v = self._conversacion(c, conversacion)
            v["titulo"] = _texto(titulo, LARGO_TITULO_CONVERSACION) or v["titulo"]
            self._tocar(c)
            return {k: v[k] for k in ("id", "titulo", "creado", "actualizado")} | {"preguntas": len(v["vueltas"])}

    def borrar_conversacion(self, cid: str, conversacion: str) -> None:
        with self._cerrojo:
            c = self._de(cid)
            c["conversaciones"].remove(self._conversacion(c, conversacion))
            self._tocar(c)

    # ---- interno ----
    def _de(self, cid: str) -> dict:
        if cid not in self._todos:
            raise NoExiste(cid)
        return self._todos[cid]

    @staticmethod
    def _conversacion(c: dict, conversacion: str) -> dict:
        for v in c["conversaciones"]:
            if v["id"] == conversacion:
                return v
        raise NoExiste(conversacion)

    def _tocar(self, c: dict) -> None:
        c["actualizado"] = _ahora()
        self._guardar(c)

    def _guardar(self, c: dict) -> None:
        ruta = self.carpeta / f"{c['id']}.json"
        temporal = ruta.with_suffix(".json.tmp")
        temporal.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
        temporal.replace(ruta)
