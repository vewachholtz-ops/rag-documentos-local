"""Un Ollama de mentira para probar la app sin modelos: responde /api/tags, /api/embed, /api/chat y /api/pull,
y también /v1/chat/completions como una API compatible con OpenAI (con la clave "clave-de-prueba").

Los embeddings son una bolsa de palabras con hash; el "modelo" responde con la primera oración del pasaje que
más palabras comparte con la pregunta, citándola, o dice que no está. Alcanza para recorrer la app de punta a
punta (agregar, preguntar, citar, descargar un modelo) en las pruebas y en las capturas.

Uso suelto: python tests/ollama_falso.py 11999 [--sin-chat]
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_local.indice import tokens
from rag_local.responder import NO_ESTA

DIMENSIONES = 512


def vector(texto: str) -> list[float]:
    v = [0.0] * DIMENSIONES
    for w in tokens(texto):
        v[zlib.crc32(w[:6].encode()) % DIMENSIONES] += 1.0
    return v


def _oraciones(texto: str) -> list[str]:
    """Las oraciones de un material, sin títulos, viñetas ni tablas."""
    limpio = []
    for linea in texto.splitlines():
        linea = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", linea).strip()
        if linea and not linea.startswith(("#", "|", "Página web:")):
            limpio.append(linea)
    return [o.strip() for o in re.split(r"(?<=[.!?])\s+", " ".join(limpio)) if len(o.split()) >= 3]


def _temas(texto: str) -> list[str]:
    """Los subtítulos del material (sin «Fuente:» ni «Página N»), o las palabras más largas."""
    temas = [
        m.strip()
        for m in re.findall(r"^#{2,3} (.+)$", texto, flags=re.M)
        if not m.startswith(("Fuente:", "Página")) and len(m) < 60
    ]
    if len(temas) < 3:
        temas += sorted({w.capitalize() for w in tokens(texto) if len(w) > 7})[:4]
    return list(dict.fromkeys(temas))[:5]


def _ramas(texto: str) -> list[tuple[str, list[str]]]:
    """(subtítulo, sus oraciones) de cada sección del material; si casi no hay subtítulos, temas sueltos."""
    ramas = []
    for bloque in re.split(r"^(?=#{2,3} )", texto, flags=re.M):
        titulo = re.match(r"#{2,3} (.+)", bloque)
        if titulo and not titulo.group(1).startswith(("Fuente:", "Página")) and (o := _oraciones(bloque)):
            ramas.append((titulo.group(1).strip(), o))
    if len(ramas) < 3:
        oraciones = _oraciones(texto) or ["Las fuentes casi no tienen texto."]
        ramas = [(t, [o]) for t, o in zip(_temas(texto), oraciones * 3, strict=False)]
    return ramas[:5]


def escribir_estudio(usuario: str) -> str:
    material = usuario.split("Fuentes:\n\n", 1)[1].split("\n\nTarea:", 1)[0]
    tarea = usuario.split("Tarea: ", 1)[1].split("\n\nReglas:", 1)[0]
    fuente = re.search(r"^## Fuente: (.+)$", material, flags=re.M)
    nombre = fuente.group(1).rsplit(".", 1)[0] if fuente else "las fuentes"
    oraciones = _oraciones(material) or ["Las fuentes casi no tienen texto."]
    ramas = _ramas(material)
    if "mapa de ideas" in tarea:
        return f"# {nombre}\n\n" + "\n".join(
            f"- {t}\n" + "\n".join(f"  - {o.rstrip('.')[:70]}" for o in os[:2]) for t, os in ramas
        )
    if "tarjetas" in tarea:
        pares = [f"P: ¿Qué dicen las fuentes sobre {t.lower()}?\nR: {os[0]}" for t, os in ramas]
        return f"# Tarjetas de {nombre}\n\n" + "\n\n".join(pares)
    if "cuestionario" in tarea:
        preguntas, respuestas = [], []
        for i, (t, os) in enumerate(ramas, 1):
            otras = [o[0] for x, o in ramas if x != t][:3] + ["No lo dicen las fuentes."] * 3
            alternativas = "\n".join(f"{letra}) {o}" for letra, o in zip("abcd", [os[0], *otras[:3]], strict=False))
            preguntas.append(f"{i}. ¿Qué dicen las fuentes sobre {t.lower()}?\n{alternativas}")
            respuestas.append(f"{i}. a) porque la fuente dice: {os[0]}")
        return (
            f"# Cuestionario de {nombre}\n\n" + "\n\n".join(preguntas) + "\n\n## Respuestas\n\n" + "\n".join(respuestas)
        )
    if tarea and not tarea.startswith(("Escribe un resumen", "Escribe una guía", "Escribe de 8", "Escribe una cron")):
        return f"# Lo que pediste\n\n{tarea}\n\n" + "\n".join(f"- {o}" for o in oraciones[:4])
    secciones = "\n\n".join(f"## {t}\n\n" + "\n".join(f"- {o}" for o in os[:2]) for t, os in ramas)
    titulos = {
        "Escribe una guía": "Guía de estudio",
        "Escribe de 8": "Preguntas frecuentes",
        "Escribe una cron": "Cronología",
    }
    titulo = next((v for k, v in titulos.items() if tarea.startswith(k)), "Resumen")
    return f"# {titulo}: {nombre}\n\n{oraciones[0]}\n\n{secciones}"


def responder_chat(sistema: str, usuario: str) -> str:
    if sistema.startswith("Tomas notas de lectura"):
        texto = usuario.split("\n\n", 1)[1].rsplit("\n\nToma notas", 1)[0]
        return "\n".join(f"- {o}" for o in _oraciones(texto)[:4])
    if sistema.startswith("Condensas notas"):
        lineas = usuario.rsplit("\n\nJunta estas notas", 1)[0].splitlines()
        return "\n".join(x for i, x in enumerate(lineas) if x.startswith("## ") or i % 3 == 0)
    if sistema.startswith("Preparas guías"):
        material = usuario.split("\n\n", 1)[1].rsplit("\n\nEscribe la guía", 1)[0]
        oraciones, temas = _oraciones(material), _temas(material)
        preguntas = "\n".join(f"- ¿Qué dice sobre {t.lower()}?" for t in temas[:3])
        return (
            f"**Resumen:** {' '.join(oraciones[:3])}\n\n**Temas:**\n"
            + "\n".join(f"- {t}" for t in temas)
            + (f"\n\n**Preguntas:**\n{preguntas}")
        )
    if sistema.startswith("Escribes material de estudio"):
        return escribir_estudio(usuario)
    if sistema.startswith("Reformulas preguntas"):
        pregunta = usuario.split("Pregunta:", 1)[1].split("\n", 1)[0].strip()
        return "\n".join([pregunta.rstrip("?¿"), " ".join(tokens(pregunta)), pregunta.lower()])
    if sistema.startswith("Ordenas pasajes"):
        return ", ".join(str(i) for i in range(1, 21))
    if sistema.startswith("Reescribes preguntas"):
        ultima = usuario.split("Última pregunta:", 1)[1].split("\n", 1)[0].strip()
        anteriores = re.findall(r"^Pregunta: (.+)$", usuario, flags=re.M)
        seguimiento = re.match(r"¿?\s*y\b", ultima, flags=re.I)  # "¿y si es de USD 300.000?"
        return f"{ultima} ({anteriores[-1]})" if anteriores and seguimiento else ultima
    # una respuesta con citas: la primera oración del pasaje más parecido a la pregunta
    pregunta = usuario.rsplit("Pregunta:", 1)[1].split("\n\nTu respuesta anterior", 1)[0]
    buscadas = set(tokens(pregunta))
    bloques = re.split(r"\n\n(?=\[\d+\] )", usuario.split("Fuentes:\n\n", 1)[1].rsplit("\n\nPregunta:", 1)[0])
    mejor, puntaje = None, 0
    for bloque in bloques:
        n = int(re.match(r"\[(\d+)\]", bloque).group(1))
        texto = bloque.split("\n", 1)[1] if "\n" in bloque else ""
        comunes = len(buscadas & set(tokens(texto)))
        if comunes > puntaje:
            mejor, puntaje = (n, texto), comunes
    if mejor is None or puntaje < 2:
        return NO_ESTA
    n, texto = mejor
    oracion = re.split(r"(?<=[.!?])\s+", " ".join(texto.split()))[0]
    oracion = " ".join(oracion.split()[:30]).rstrip(".")
    return f'{oracion} [{n}].\n\n[{n}] "{oracion}"'


class Estado:
    def __init__(self, modelos: set[str], demora: float):
        self.modelos = set(modelos)
        self.demora = demora
        self.llamadas: list[str] = []
        self.sistemas: list[str] = []  # las instrucciones de sistema de cada chat, para revisar qué se pidió


def manejador(estado: Estado):
    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, datos: dict) -> None:
            cuerpo = json.dumps(datos).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            if self.path == "/api/tags":
                self._json({"models": [{"name": m} for m in sorted(estado.modelos)]})
            else:
                self.send_error(404)

        def do_POST(self):
            pedido = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            estado.llamadas.append(self.path)
            if self.path == "/api/embed":
                time.sleep(estado.demora / 2)
                self._json({"embeddings": [vector(t) for t in pedido["input"]]})
            elif self.path == "/v1/chat/completions":  # una API compatible con OpenAI
                if self.headers.get("Authorization") != "Bearer clave-de-prueba":
                    self.send_error(401)
                    return
                mensajes = pedido["messages"]
                contenido = responder_chat(mensajes[0]["content"], mensajes[-1]["content"])
                self._json({"choices": [{"message": {"role": "assistant", "content": contenido}}]})
            elif self.path == "/api/chat":
                time.sleep(estado.demora)
                mensajes = pedido["messages"]
                estado.sistemas.append(mensajes[0]["content"])
                contenido = responder_chat(mensajes[0]["content"], mensajes[-1]["content"])
                self._json({"message": {"role": "assistant", "content": contenido}})
            elif self.path == "/api/pull":
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                total = 1_000_000
                for hecho in (0, 250_000, 600_000, total):
                    linea = {"status": "pulling", "total": total, "completed": hecho}
                    self.wfile.write((json.dumps(linea) + "\n").encode())
                    self.wfile.flush()
                    time.sleep(estado.demora)
                estado.modelos.add(pedido["model"])
                self.wfile.write(b'{"status": "success"}\n')
            else:
                self.send_error(404)

    return Manejador


def iniciar(puerto: int = 0, modelos=("gpt-oss:20b", "nomic-embed-text:latest"), demora: float = 0.05):
    """Arranca el Ollama de mentira en otro hilo. Devuelve (servidor, estado, url)."""
    estado = Estado(set(modelos), demora)
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), manejador(estado))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, estado, f"http://127.0.0.1:{servidor.server_address[1]}"


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 11999
    modelos = ["nomic-embed-text:latest"] if "--sin-chat" in sys.argv else ["gpt-oss:20b", "nomic-embed-text:latest"]
    servidor, _, url = iniciar(puerto, modelos, demora=0.6)
    print(f"Ollama de mentira en {url}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        servidor.shutdown()
