"""Con qué responde Tesela: solo buscar (sin IA), Ollama en el computador o una API compatible con OpenAI.

La búsqueda es siempre local. Los embeddings, si Ollama está abierto y tiene el modelo, también: en el modo API
lo único que sale del computador son la pregunta y los pasajes elegidos, para que el modelo redacte la respuesta.

Los ajustes quedan en biblioteca/ajustes.json; la clave de la API en biblioteca/ajustes-secretos.json, que la
API local nunca devuelve.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from . import ollama
from .indice import Embedder

Chat = Callable[[str, str], str]
MODOS = ("buscar", "ollama", "openai")
LOCALES = {"localhost", "127.0.0.1", "::1"}


class ErrorProveedor(Exception):
    """Un problema con el modelo elegido, explicado para mostrarlo tal cual en la app."""


def _ruta_atomica(ruta: Path, datos: dict) -> None:
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    temporal.replace(ruta)


def es_local(url: str) -> bool:
    return (urllib.parse.urlsplit(url).hostname or "") in LOCALES


def url_valida(url: str) -> bool:
    partes = urllib.parse.urlsplit(url)
    return partes.scheme in ("http", "https") and bool(partes.hostname) and not partes.username


def chatear_openai(url: str, clave: str, modelo: str, sistema: str, usuario: str, timeout: float = 300) -> str:
    """Una respuesta de /chat/completions (OpenAI, Groq, OpenRouter, LM Studio, vLLM y similares)."""
    cuerpo = {
        "model": modelo,
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        "temperature": 0,
    }
    cabeceras = {"Content-Type": "application/json"} | ({"Authorization": f"Bearer {clave}"} if clave else {})
    pedido = urllib.request.Request(
        f"{url.rstrip('/')}/chat/completions", data=json.dumps(cuerpo).encode(), headers=cabeceras
    )
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as r:
            datos = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")[:200]
        if e.code in (401, 403):
            raise ErrorProveedor("La API rechazó la clave. Revísala en Modelos.") from e
        raise ErrorProveedor(f"La API respondió {e.code}: {detalle}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise ErrorProveedor(f"No pude conectar con {url}. Revisa la dirección en Modelos.") from e
    except ValueError as e:
        raise ErrorProveedor("La API respondió algo que no es JSON.") from e
    try:
        return str(datos["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as e:
        raise ErrorProveedor("La respuesta de la API no trae el texto donde se espera.") from e


class Proveedores:
    def __init__(self, carpeta: Path):
        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        self._ruta = carpeta / "ajustes.json"
        self._ruta_secreta = carpeta / "ajustes-secretos.json"
        self._cerrojo = threading.Lock()
        self._ajustes = {
            "modo": "ollama",
            "modelo": ollama.MODELO_CHAT,
            "a_fondo": True,
            "openai": {"url": "", "modelo": ""},
        }
        self._clave = ""
        try:
            guardado = json.loads(self._ruta.read_text(encoding="utf-8"))
            if isinstance(guardado, dict):
                self._ajustes |= {k: v for k, v in guardado.items() if k in self._ajustes}
        except (OSError, ValueError):
            pass
        try:
            self._clave = str(json.loads(self._ruta_secreta.read_text(encoding="utf-8")).get("clave", ""))
        except (OSError, ValueError, AttributeError):
            pass
        if self._ajustes["modo"] not in MODOS:
            self._ajustes["modo"] = "ollama"

    # ---- ajustes ----
    @property
    def modo(self) -> str:
        return self._ajustes["modo"]

    @property
    def a_fondo(self) -> bool:
        return bool(self._ajustes["a_fondo"])

    def publico(self) -> dict:
        """Los ajustes para la interfaz, sin la clave."""
        with self._cerrojo:
            api = self._ajustes["openai"]
            return {
                "modo": self._ajustes["modo"],
                "modelo": self._ajustes["modelo"],
                "a_fondo": self._ajustes["a_fondo"],
                "openai": {
                    "url": api["url"],
                    "modelo": api["modelo"],
                    "hay_clave": bool(self._clave),
                    "local": bool(api["url"]) and es_local(api["url"]),
                },
            }

    def cambiar(self, cambios: dict) -> dict:
        with self._cerrojo:
            nuevo = json.loads(json.dumps(self._ajustes))
            if "modo" in cambios:
                if cambios["modo"] not in MODOS:
                    raise ErrorProveedor("Ese modo no existe.")
                nuevo["modo"] = cambios["modo"]
            if "modelo" in cambios:
                nuevo["modelo"] = str(cambios["modelo"]).strip()[:200] or ollama.MODELO_CHAT
            if "a_fondo" in cambios:
                nuevo["a_fondo"] = cambios["a_fondo"] is not False
            api = cambios.get("openai")
            if isinstance(api, dict):
                if "url" in api:
                    url = str(api["url"]).strip()[:500]
                    if url and not url_valida(url):
                        raise ErrorProveedor("La dirección debe empezar con http:// o https://.")
                    nuevo["openai"]["url"] = url
                if "modelo" in api:
                    nuevo["openai"]["modelo"] = str(api["modelo"]).strip()[:200]
                if "clave" in api:
                    self._clave = str(api["clave"]).strip()[:500]
                    if self._clave:
                        _ruta_atomica(self._ruta_secreta, {"clave": self._clave})
                    else:
                        self._ruta_secreta.unlink(missing_ok=True)
            self._ajustes = nuevo
            _ruta_atomica(self._ruta, self._ajustes)
        return self.publico()

    # ---- estado ----
    def estado(self) -> dict:
        """Si se puede preguntar con el modo elegido y, si no, qué falta."""
        instalados = ollama.modelos_instalados()
        modo = self.modo
        salida = {
            "modo": modo,
            "ollama": instalados is not None,
            "modelo": self._ajustes["modelo"],
            "embeddings": ollama.MODELO_EMBEDDINGS,
            "modelos": sorted(m for m in (instalados or set()) if "embed" not in m),
            "faltan": [],
            "busqueda_por_significado": self._hay_embeddings(instalados),
        }
        if modo == "ollama":
            necesarios = (self._ajustes["modelo"], ollama.MODELO_EMBEDDINGS)
            salida["faltan"] = [] if instalados is None else ollama.faltan(instalados, necesarios)
            salida["listo"] = instalados is not None and not salida["faltan"]
        elif modo == "openai":
            api = self._ajustes["openai"]
            salida["listo"] = bool(api["url"] and api["modelo"])
            salida["modelo"] = api["modelo"]
        else:
            salida["listo"] = True
        return salida

    # ---- funciones para buscar y responder ----
    def _hay_embeddings(self, instalados: set[str] | None) -> bool:
        return instalados is not None and not ollama.faltan(instalados, [ollama.MODELO_EMBEDDINGS])

    def embedder_documentos(self) -> tuple[Embedder | None, str | None]:
        """Embeddings locales si Ollama está abierto y tiene el modelo; si no, (None, None): solo palabras."""
        if self._hay_embeddings(ollama.modelos_instalados()):
            return ollama.embeber_documentos, ollama.MODELO_EMBEDDINGS
        return None, None

    def embedder_consulta(self) -> Embedder | None:
        return ollama.embeber_consulta if self._hay_embeddings(ollama.modelos_instalados()) else None

    def chats(self) -> tuple[Chat, Chat, str]:
        """(chat, auxiliar, nombre del modelo) del modo elegido. En el modo solo buscar no hay."""
        modo = self.modo
        if modo == "ollama":
            modelo = self._ajustes["modelo"]

            def chat(sistema: str, usuario: str) -> str:
                return ollama.chatear(sistema, usuario, modelo)

            def aux(sistema: str, usuario: str) -> str:
                return ollama.chatear(sistema, usuario, modelo, razonamiento="low")

            return chat, aux, modelo
        if modo == "openai":
            api = dict(self._ajustes["openai"])
            clave = self._clave
            if not (api["url"] and api["modelo"]):
                raise ErrorProveedor("Falta la dirección o el modelo de la API. Complétalos en Modelos.")

            def chat_api(sistema: str, usuario: str) -> str:
                return chatear_openai(api["url"], clave, api["modelo"], sistema, usuario)

            return chat_api, chat_api, api["modelo"]
        raise ErrorProveedor("En el modo solo buscar no hay modelo que responda.")
