// El Web Worker de la versión web: carga Pyodide, el motor de Tesela (src/rag_local, empaquetado en py/) y la
// biblioteca guardada en el navegador, y atiende uno a uno los pedidos a /api que le pasa puente.ts. La respuesta
// vuelve en trozos de bytes a medida que Python la escribe.
/// <reference lib="webworker" />

type Pyodide = {
  loadPackage: (nombres: string | string[]) => Promise<unknown>
  unpackArchive: (datos: ArrayBuffer, formato: string, opciones?: { extractDir?: string }) => void
  runPython: (codigo: string) => unknown
  pyimport: (nombre: string) => unknown
  toPy: (valor: unknown) => unknown
  FS: {
    mkdirTree: (ruta: string) => void
    mount: (fs: unknown, opciones: object, ruta: string) => void
    syncfs: (cargar: boolean, listo: (error: unknown) => void) => void
    filesystems: { IDBFS: unknown }
  }
}

type Inicio = { tipo: 'iniciar'; base: string; pyodide: string }
type Pedido = { tipo: 'pedido'; id: number; metodo: string; ruta: string; cabeceras: Record<string, string>; cuerpo: Uint8Array | null }

type Navegador = { iniciar: (carpeta: string) => void; atender: (...args: unknown[]) => void }

const avisar = (mensaje: object) => (self as unknown as Worker).postMessage(mensaje)
let navegador: Navegador | null = null
let pyodide: Pyodide | null = null
let cola: Promise<void> = Promise.resolve()

function sincronizar(cargar: boolean) {
  return new Promise<void>((resolver, rechazar) => pyodide!.FS.syncfs(cargar, (error) => (error ? rechazar(error) : resolver())))
}

async function iniciar({ base, pyodide: urlPyodide }: Inicio) {
  avisar({ tipo: 'arranque', texto: 'Bajando Python para el navegador (unos 15 MB, solo la primera vez)' })
  const { loadPyodide } = await import(/* @vite-ignore */ `${urlPyodide}pyodide.mjs`)
  pyodide = (await loadPyodide({ indexURL: urlPyodide })) as Pyodide
  const manifiesto = await (await fetch(new URL('py/manifiesto.json', base))).json()
  await pyodide.loadPackage(['numpy', 'pyodide-http', ...manifiesto.ruedas.map((r: string) => new URL(`py/${r}`, base).href)])

  avisar({ tipo: 'arranque', texto: 'Preparando el motor de búsqueda' })
  const motor = await (await fetch(new URL(`py/${manifiesto.motor}`, base))).arrayBuffer()
  pyodide.unpackArchive(motor, 'zip', { extractDir: '/tesela' })
  pyodide.runPython("import sys; sys.path.insert(0, '/tesela')\nimport pyodide_http; pyodide_http.patch_all()")

  avisar({ tipo: 'arranque', texto: 'Abriendo tu biblioteca' })
  pyodide.FS.mkdirTree('/datos')
  pyodide.FS.mount(pyodide.FS.filesystems.IDBFS, {}, '/datos')
  await sincronizar(true)
  navegador = pyodide.pyimport('rag_local.navegador') as Navegador
  navegador.iniciar('/datos/biblioteca')
  await sincronizar(false)
  avisar({ tipo: 'listo' })
}

async function atender({ id, metodo, ruta, cabeceras, cuerpo }: Pedido) {
  try {
    const py = pyodide!
    const cabecerasPy = py.toPy(cabeceras)
    const cuerpoPy = cuerpo ? py.toPy(cuerpo) : null
    try {
      navegador!.atender(metodo, ruta, cabecerasPy, cuerpoPy, (trozo: Uint8Array) => {
        const copia = trozo.slice()
        avisar({ tipo: 'datos', id, bytes: copia })
      })
    } finally {
      ;(cabecerasPy as { destroy?: () => void }).destroy?.()
      ;(cuerpoPy as { destroy?: () => void } | null)?.destroy?.()
    }
    // lo que cambió queda guardado en el navegador antes de dar el pedido por terminado
    if (metodo !== 'GET') await sincronizar(false)
    avisar({ tipo: 'fin', id })
  } catch (error) {
    avisar({ tipo: 'error', id, texto: error instanceof Error ? error.message : String(error) })
  }
}

self.onmessage = (e: MessageEvent<Inicio | Pedido>) => {
  const m = e.data
  if (m.tipo === 'iniciar') {
    cola = iniciar(m).catch((error) => {
      avisar({ tipo: 'fallo', texto: error instanceof Error ? error.message : String(error) })
      throw error
    })
    return
  }
  // de a uno: Python atiende un pedido a la vez
  cola = cola.then(() => atender(m))
}
