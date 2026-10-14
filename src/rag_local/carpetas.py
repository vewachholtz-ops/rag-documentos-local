"""Carpetas conectadas: Tesela lee los documentos de una carpeta del computador y los mantiene al día.

Idea de Mesa documental (el conector de carpetas de Codex). Sincronizar agrega los archivos nuevos, vuelve a leer
los que cambiaron (tamaño o fecha) y saca los que ya no están. La poda es cuidadosa: un documento solo se borra de la
biblioteca si lo trajo esta carpeta y ningún otro archivo conectado lo usa; si ya estaba en la biblioteca antes (la
persona lo había subido a mano), solo se saca del cuaderno de la carpeta. Los archivos de la carpeta nunca se tocan:
Tesela guarda su propia copia.

La lista vive en biblioteca/carpetas.json, escrita de forma atómica.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from .biblioteca import TAMANO_MAXIMO, TIPOS, Biblioteca, ErrorDocumento
from .cuadernos import Cuadernos, NoExiste
from .indice import Embedder

ARCHIVOS_MAXIMOS = 300
PROFUNDIDAD = 3  # subcarpetas que se recorren, contando desde la conectada
Avisar = Callable[[dict], None]


class ErrorCarpeta(ErrorDocumento):
    """La carpeta no se puede conectar o sincronizar; el mensaje es para mostrarlo tal cual."""


def validar_ruta(ruta: str) -> Path:
    """Una carpeta local que existe. Nada de direcciones de red ni de rutas relativas o enlaces."""
    ruta = str(ruta or "").strip().strip('"')
    if not ruta or "://" in ruta or ruta.startswith(("\\\\", "//")):
        raise ErrorCarpeta("Escribe la ruta de una carpeta de este computador, por ejemplo C:\\Users\\tu\\Documentos.")
    carpeta = Path(ruta).expanduser()
    if not carpeta.is_absolute():
        raise ErrorCarpeta("Escribe la ruta completa de la carpeta, desde la unidad (por ejemplo C:\\...).")
    if carpeta.is_symlink() or not carpeta.is_dir():
        raise ErrorCarpeta("Esa carpeta no existe o no es una carpeta.")
    return carpeta.resolve()


def archivos_de(carpeta: Path, excluir: Path | None = None) -> tuple[list[tuple[str, Path]], list[dict]]:
    """Los documentos que se pueden leer (ruta relativa, ruta) y los que se omiten, con el motivo. `excluir` es la
    carpeta de la biblioteca de Tesela: sus copias no se vuelven a leer si la carpeta conectada la contiene."""
    encontrados: list[tuple[str, Path]] = []
    omitidos: list[dict] = []
    excluir = excluir.resolve() if excluir else None
    for raiz, subcarpetas, archivos in os.walk(carpeta):  # no sigue enlaces simbólicos
        nivel = len(Path(raiz).relative_to(carpeta).parts)
        subcarpetas[:] = sorted(
            d
            for d in subcarpetas
            if not d.startswith(".") and nivel < PROFUNDIDAD and (Path(raiz) / d).resolve() != excluir
        )
        for nombre in sorted(archivos, key=str.lower):
            ruta = Path(raiz) / nombre
            relativa = ruta.relative_to(carpeta).as_posix()
            # los ocultos y los temporales de Word (~$archivo.docx) no son documentos
            if nombre.startswith((".", "~$")) or ruta.suffix.lower() not in TIPOS or ruta.is_symlink():
                continue
            try:
                tamano = ruta.stat().st_size
            except OSError:  # abierto por otro programa o sin permiso
                omitidos.append({"archivo": relativa, "texto": "no se pudo abrir"})
                continue
            if tamano > TAMANO_MAXIMO:
                omitidos.append({"archivo": relativa, "texto": "pesa más de 30 MB"})
                continue
            encontrados.append((relativa, ruta))
            if len(encontrados) > ARCHIVOS_MAXIMOS:
                raise ErrorCarpeta(
                    f"La carpeta tiene más de {ARCHIVOS_MAXIMOS} documentos. Conecta una más chica o una subcarpeta."
                )
    return encontrados, omitidos


class Carpetas:
    def __init__(self, carpeta: Path):
        self._biblioteca = Path(carpeta).resolve()
        self._ruta = Path(carpeta) / "carpetas.json"
        self._cerrojo = threading.RLock()
        self._sincronizando = threading.Lock()
        try:
            datos = json.loads(self._ruta.read_text(encoding="utf-8"))
            self._todas: list[dict] = datos if isinstance(datos, list) else []
        except (OSError, ValueError):
            self._todas = []

    # ---- consulta ----
    def lista(self) -> list[dict]:
        with self._cerrojo:
            return [self._publica(c) for c in self._todas]

    def obtener(self, cid: str) -> dict:
        with self._cerrojo:
            return self._publica(self._de(cid))

    # ---- cambios ----
    def conectar(self, ruta: str, cuaderno: str | None) -> dict:
        carpeta = validar_ruta(ruta)
        if carpeta == self._biblioteca or self._biblioteca in carpeta.parents:
            raise ErrorCarpeta("Esa es la carpeta donde Tesela guarda sus copias: conecta otra.")
        with self._cerrojo:
            if any(Path(c["ruta"]) == carpeta and c["cuaderno"] == cuaderno for c in self._todas):
                raise ErrorCarpeta("Esa carpeta ya está conectada a este cuaderno.")
            nueva = {
                "id": uuid.uuid4().hex[:12],
                "ruta": str(carpeta),
                "cuaderno": cuaderno or None,
                "conectada": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "sincronizada": None,
                "archivos": {},  # ruta relativa → {doc_id, tamano, modificado, propio}
            }
            self._todas.append(nueva)
            self._guardar()
            return self._publica(nueva)

    def desconectar(self, cid: str) -> None:
        """Deja de seguir la carpeta. Los documentos que ya trajo quedan en la biblioteca y en el cuaderno."""
        with self._cerrojo:
            self._todas.remove(self._de(cid))
            self._guardar()

    def olvidar_cuaderno(self, cuaderno: str) -> None:
        with self._cerrojo:
            for c in self._todas:
                if c["cuaderno"] == cuaderno:
                    c["cuaderno"] = None
            self._guardar()

    def sincronizar(
        self,
        cid: str,
        biblioteca: Biblioteca,
        cuadernos: Cuadernos,
        embedder: Embedder | None,
        modelo: str | None,
        avisar: Avisar,
    ) -> dict:
        """Agrega, actualiza y quita según lo que hay hoy en la carpeta. Devuelve el informe."""
        if not self._sincronizando.acquire(blocking=False):
            raise ErrorCarpeta("Ya se está sincronizando una carpeta. Espera a que termine.")
        try:
            with self._cerrojo:
                c = self._de(cid)
                entradas: dict[str, dict] = dict(c["archivos"])
                cuaderno = c["cuaderno"]
            carpeta = validar_ruta(c["ruta"])
            avisar({"tipo": "paso", "texto": "Revisando la carpeta"})
            archivos, omitidos = archivos_de(carpeta, self._biblioteca)
            informe = {"agregados": 0, "actualizados": 0, "quitados": 0, "sin_cambios": 0, "omitidos": omitidos}
            errores: list[dict] = []
            vistos: set[str] = set()
            for n, (relativa, ruta) in enumerate(archivos, 1):
                vistos.add(relativa)
                try:
                    estado = ruta.stat()
                except OSError as error:
                    errores.append({"archivo": relativa, "texto": f"no se pudo abrir ({error.strerror})"})
                    continue
                firma = {"tamano": estado.st_size, "modificado": int(estado.st_mtime)}
                previa = entradas.get(relativa)
                if previa and all(previa[k] == v for k, v in firma.items()) and biblioteca.documento(previa["doc_id"]):
                    informe["sin_cambios"] += 1
                    cuaderno = self._enlazar(cuadernos, cuaderno, previa["doc_id"])
                    continue
                avisar({"tipo": "paso", "texto": f"Leyendo {relativa} ({n} de {len(archivos)})"})
                try:
                    doc = biblioteca.agregar(ruta.name, ruta.read_bytes(), embedder, modelo, lambda _e: None)
                except (ErrorDocumento, OSError) as error:
                    errores.append({"archivo": relativa, "texto": str(error)})
                    continue  # si cambió y ahora no se puede leer, se queda la versión anterior
                mismo = previa is not None and previa["doc_id"] == doc["id"]  # cambió la fecha, no el contenido
                propio = previa["propio"] if mismo else not doc.get("repetido")
                entradas[relativa] = {**firma, "doc_id": doc["id"], "propio": propio}
                if previa and not mismo:
                    self._soltar(previa, entradas, cid, biblioteca, cuadernos, cuaderno)
                informe["sin_cambios" if mismo else "actualizados" if previa else "agregados"] += 1
                cuaderno = self._enlazar(cuadernos, cuaderno, doc["id"])
            for relativa in [r for r in entradas if r not in vistos]:
                self._soltar(entradas.pop(relativa), entradas, cid, biblioteca, cuadernos, cuaderno)
                informe["quitados"] += 1
            with self._cerrojo:
                c = self._de(cid)
                c["archivos"] = entradas
                c["cuaderno"] = cuaderno
                c["sincronizada"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._guardar()
            return informe | {"errores": errores}
        finally:
            self._sincronizando.release()

    # ---- interno ----
    def _enlazar(self, cuadernos: Cuadernos, cuaderno: str | None, doc_id: str) -> str | None:
        """Enlaza el documento al cuaderno de la carpeta; si el cuaderno ya no existe, la carpeta queda sin él."""
        if not cuaderno:
            return None
        try:
            cuadernos.enlazar(cuaderno, doc_id)
            return cuaderno
        except NoExiste:
            return None

    def _soltar(
        self,
        entrada: dict,
        restantes: dict[str, dict],
        cid: str,
        biblioteca: Biblioteca,
        cuadernos: Cuadernos,
        cuaderno: str | None,
    ) -> None:
        """Un archivo que ya no está (o que cambió): su documento se borra solo si lo trajo esta carpeta y nadie más
        lo usa; si no, a lo más sale del cuaderno de la carpeta."""
        doc_id = entrada["doc_id"]
        if any(e["doc_id"] == doc_id for e in restantes.values()):
            return  # otro archivo de la misma carpeta tiene el mismo contenido
        with self._cerrojo:
            en_otras = any(e["doc_id"] == doc_id for c in self._todas if c["id"] != cid for e in c["archivos"].values())
        # si la persona lo agregó también a otro cuaderno, lo sigue usando: solo sale del de la carpeta
        en_otros_cuadernos = any(x["id"] != cuaderno for x in cuadernos.cuadernos_de().get(doc_id, []))
        if entrada.get("propio") and not en_otras and not en_otros_cuadernos:
            if biblioteca.quitar(doc_id):
                cuadernos.olvidar_documento(doc_id)
        elif cuaderno and not en_otras:
            try:
                cuadernos.desenlazar(cuaderno, doc_id)
            except NoExiste:
                pass

    def _de(self, cid: str) -> dict:
        for c in self._todas:
            if c["id"] == cid:
                return c
        raise NoExiste(cid)

    @staticmethod
    def _publica(c: dict) -> dict:
        return {k: c[k] for k in ("id", "ruta", "cuaderno", "conectada", "sincronizada")} | {
            "documentos": len(c["archivos"])
        }

    def _guardar(self) -> None:
        temporal = self._ruta.with_suffix(".json.tmp")
        temporal.write_text(json.dumps(self._todas, ensure_ascii=False, indent=1), encoding="utf-8")
        temporal.replace(self._ruta)
