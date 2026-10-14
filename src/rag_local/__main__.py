"""Comando `rag`.

uv run rag indexar                    lee documentos/, genera el contexto de cada trozo y guarda el índice
uv run rag preguntar "¿...?"          responde citando las fuentes (--rapido: sin reescribir ni reordenar)
uv run rag evaluar                    corre todas las configuraciones y guarda resultados/evaluacion.*
uv run rag evaluar --solo-busqueda    solo BM25 por sección, sin Ollama
uv run rag evaluar --repuntuar        vuelve a puntuar las respuestas guardadas, sin Ollama
uv run rag evaluar --unidades         experimento: comprobar la unidad de las cifras (sin Ollama, solo una parte)
uv run rag servir                     abre la app: agrega tus documentos y pregúntales
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import ollama
from .busqueda import Busqueda, buscar
from .cache import CacheEmbeddings, CacheLLM
from .contexto import agregar_contexto
from .evaluar import cargar_preguntas, evaluar_busqueda, repuntuar
from .experimentos import Modelos, correr, experimento_unidades, informe, informe_unidades
from .indice import Indice, cargar_documentos, trocear_documentos
from .responder import responder

RAIZ = Path.cwd()


def main() -> None:
    try:
        _main()
    except ollama.SinConexion as e:
        raise SystemExit(str(e)) from None


def _main() -> None:
    ap = argparse.ArgumentParser(prog="rag", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--documentos", type=Path, default=RAIZ / "documentos")
    ap.add_argument("--indice", type=Path, default=RAIZ / ".indice")
    sub = ap.add_subparsers(dest="comando", required=True)
    i = sub.add_parser("indexar")
    i.add_argument("--sin-contexto", action="store_true", help="no generar el contexto de cada trozo (más rápido)")
    p = sub.add_parser("preguntar")
    p.add_argument("pregunta")
    p.add_argument("-k", type=int, default=4)
    p.add_argument("--rapido", action="store_true", help="sin reescribir la consulta ni reordenar con el modelo")
    p.add_argument("--sin-citas-textuales", action="store_true")
    e = sub.add_parser("evaluar")
    e.add_argument("--solo-busqueda", action="store_true")
    e.add_argument("--repuntuar", action="store_true", help="puntuar de nuevo resultados/evaluacion.json")
    e.add_argument("--salida", type=Path, default=RAIZ / "resultados")
    e.add_argument(
        "--unidades", action="store_true", help="experimento: comprobar la unidad de las cifras (docs/evaluacion.md)"
    )
    s = sub.add_parser("servir", help="abre la app: agrega tus documentos y pregúntales (necesita Ollama)")
    s.add_argument("--puerto", type=int, default=8000)
    s.add_argument("--sin-navegador", action="store_true")
    s.add_argument("--biblioteca", type=Path, default=RAIZ / "biblioteca", help="dónde guarda tus documentos")
    a = ap.parse_args()

    if a.comando == "servir":
        from .servidor import servir

        servir(Path(__file__).resolve().parents[2], a.biblioteca, a.puerto, abrir=not a.sin_navegador)
        return

    cache = a.indice / "cache-llm.jsonl"
    aux = CacheLLM(ollama.chatear_auxiliar, cache, f"aux|{ollama.MODELO_AUX}|low")
    chat = CacheLLM(ollama.chatear, cache, f"chat|{ollama.MODELO_CHAT}")
    consulta = CacheEmbeddings(ollama.embeber_consulta, a.indice / "cache-embeddings.jsonl", ollama.MODELO_EMBEDDINGS)

    if a.comando == "indexar":
        documentos = cargar_documentos(a.documentos)
        trozos = trocear_documentos(documentos)
        print(f"{len(trozos)} trozos de {len(documentos)} documentos vigentes")
        print(f"Embeddings con {ollama.MODELO_EMBEDDINGS}…")
        Indice.construir(trozos, ollama.embeber_documentos).guardar(a.indice / "base")
        if not a.sin_contexto:
            print(f"Contexto de cada trozo con {ollama.MODELO_AUX} (queda en caché para la próxima vez)…")
            con_contexto = agregar_contexto(trozos, documentos, aux)
            Indice.construir(con_contexto, ollama.embeber_documentos).guardar(a.indice / "contexto")
        print(f"Índice guardado en {a.indice}")

    elif a.comando == "preguntar":
        carpeta = a.indice / "contexto" if (a.indice / "contexto").exists() else a.indice / "base"
        indice = Indice.cargar(carpeta)
        config = Busqueda() if a.rapido else Busqueda(reescribir=True, reordenar=True)  # la v2 evaluada
        fuentes = buscar(indice, a.pregunta, a.k, consulta, config, aux)
        r = responder(a.pregunta, fuentes, chat, citas_textuales=not a.sin_citas_textuales)
        print(r.cuerpo, "\n")
        for n, frase in r.textuales:
            print(f'  [{n}] "{frase}"')
        print()
        for n, f in enumerate(fuentes, 1):
            print(f"[{n}] {f.trozo.titulo}  ({f.trozo.documento})")
        if r.problemas:
            print("\nOjo, la respuesta no pasó la validación:", "; ".join(r.problemas))

    elif a.comando == "evaluar":
        preguntas = cargar_preguntas(RAIZ / "evaluacion" / "preguntas.json")
        a.salida.mkdir(parents=True, exist_ok=True)
        if a.repuntuar:
            r = json.loads((a.salida / "evaluacion.json").read_text(encoding="utf-8"))
            repuntuar(r["respuestas"], preguntas)
            (a.salida / "evaluacion.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (a.salida / "evaluacion.md").write_text(informe(r), encoding="utf-8")
            print(informe(r))
            return
        if a.unidades:
            previa = json.loads((a.salida / "evaluacion.json").read_text(encoding="utf-8"))
            textos = {t.titulo: t.texto for t in trocear_documentos(cargar_documentos(a.documentos))}
            indice, modelos = None, None
            if (a.indice / "contexto" / "trozos.json").exists() and ollama.modelos_instalados() is not None:
                indice = Indice.cargar(a.indice / "contexto")
                juez = CacheLLM(ollama.chatear_juez, cache, f"juez|{ollama.MODELO_AUX}|medium")
                nombres = {"embeddings": ollama.MODELO_EMBEDDINGS, "respuestas": ollama.MODELO_CHAT}
                modelos = Modelos(ollama.embeber_documentos, consulta, chat, aux, nombres, juez)
            else:
                print("Sin Ollama o sin índice con contexto: solo la parte sin modelo.\n")
            r = experimento_unidades(previa, preguntas, textos, indice, modelos)
            (a.salida / "experimento-unidades.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            texto = informe_unidades(r, previa)
            (a.salida / "experimento-unidades.md").write_text(texto, encoding="utf-8")
            print(texto)
            return
        if a.solo_busqueda:
            indice = Indice.construir(trocear_documentos(cargar_documentos(a.documentos)), None)
            salida = {"busqueda": {"BM25": evaluar_busqueda(indice, preguntas, None, Busqueda("bm25"))}}
            (a.salida / "evaluacion-busqueda.json").write_text(
                json.dumps(salida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(salida, ensure_ascii=False, indent=2))
            return
        _mantener_despierto()
        registro = a.indice / "progreso.log"
        registro.parent.mkdir(parents=True, exist_ok=True)

        def avance(texto: str) -> None:
            linea = f"{time.strftime('%H:%M:%S')}  {texto}"
            print(linea, flush=True)
            with registro.open("a", encoding="utf-8") as f:
                f.write(linea + "\n")

        juez = CacheLLM(ollama.chatear_juez, cache, f"juez|{ollama.MODELO_AUX}|medium")
        modelos = Modelos(
            ollama.embeber_documentos,
            consulta,
            chat,
            aux,
            {"embeddings": ollama.MODELO_EMBEDDINGS, "respuestas": ollama.MODELO_CHAT, "auxiliar": ollama.MODELO_AUX},
            juez,
        )
        r = correr(a.documentos, preguntas, modelos, avance)
        for nombre, indice in r.pop("indices").items():
            indice.guardar(a.indice / nombre)
        r["llamadas_al_modelo"] = {"respuestas": chat.llamadas, "auxiliar": aux.llamadas, "juez": juez.llamadas}
        (a.salida / "evaluacion.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (a.salida / "evaluacion.md").write_text(informe(r), encoding="utf-8")
        avance(f"listo: {a.salida / 'evaluacion.md'}")


def _mantener_despierto() -> None:
    """En Windows, evita que el computador se suspenda mientras corre la evaluación (vuelve a lo normal al
    terminar el proceso). En otros sistemas no hace nada."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED


if __name__ == "__main__":
    main()
