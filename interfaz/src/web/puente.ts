// El puente de la versión web: los pedidos que la interfaz hace a api/… no salen a la red; van al Web Worker donde
// corre el motor en Python (trabajador.ts), y su respuesta HTTP vuelve como una Response normal, en trozos, para
// que los avisos de los trabajos largos se vean a medida que llegan. El resto de la interfaz no se entera.
import { useSyncExternalStore } from 'react'
import { URL_PYODIDE } from './config'

export type Arranque = { fase: 'cargando'; texto: string } | { fase: 'listo' } | { fase: 'error'; texto: string }

let arranque: Arranque = { fase: 'cargando', texto: 'Abriendo Tesela' }
const oyentes = new Set<() => void>()
function cambiarArranque(a: Arranque) {
  arranque = a
  oyentes.forEach((o) => o())
}

export function useArranque() {
  return useSyncExternalStore(
    (o) => {
      oyentes.add(o)
      return () => oyentes.delete(o)
    },
    () => arranque,
  )
}

type Pendiente = {
  resolver: (r: Response) => void
  rechazar: (e: unknown) => void
  cabeza: Uint8Array
  flujo: ReadableStreamDefaultController<Uint8Array> | null
}

const pendientes = new Map<number, Pendiente>()
let siguiente = 1
let trabajador: Worker
let listo: Promise<void>

const FIN_CABEZA = [13, 10, 13, 10] // \r\n\r\n

function unir(a: Uint8Array, b: Uint8Array) {
  const c = new Uint8Array(a.length + b.length)
  c.set(a)
  c.set(b, a.length)
  return c
}

function finDeCabeza(datos: Uint8Array) {
  for (let i = 0; i + 3 < datos.length; i++) if (FIN_CABEZA.every((b, k) => datos[i + k] === b)) return i
  return -1
}

function respuestaDeError(texto: string, estado = 500) {
  return new Response(JSON.stringify({ error: texto }), { status: estado, headers: { 'Content-Type': 'application/json' } })
}

/** Llegó un trozo de la respuesta: primero se juntan las cabeceras; con ellas, la Response sigue como flujo. */
function recibir(p: Pendiente, bytes: Uint8Array) {
  if (p.flujo) {
    p.flujo.enqueue(bytes)
    return
  }
  p.cabeza = unir(p.cabeza, bytes)
  const fin = finDeCabeza(p.cabeza)
  if (fin < 0) return
  const [primera, ...lineas] = new TextDecoder('latin1').decode(p.cabeza.subarray(0, fin)).split('\r\n')
  const estado = Number(primera.split(' ')[1]) || 500
  const cabeceras = new Headers()
  for (const linea of lineas) {
    const i = linea.indexOf(':')
    if (i > 0) cabeceras.append(linea.slice(0, i).trim(), linea.slice(i + 1).trim())
  }
  const resto = p.cabeza.subarray(fin + 4)
  const flujo = new ReadableStream<Uint8Array>({
    start(controlador) {
      p.flujo = controlador
      if (resto.length) controlador.enqueue(resto.slice())
    },
  })
  p.resolver(new Response(estado === 204 ? null : flujo, { status: estado, headers: cabeceras }))
}

function alMensaje(e: MessageEvent) {
  const m = e.data
  if (m.tipo === 'arranque') return cambiarArranque({ fase: 'cargando', texto: m.texto })
  if (m.tipo === 'listo') return cambiarArranque({ fase: 'listo' })
  if (m.tipo === 'fallo') return cambiarArranque({ fase: 'error', texto: m.texto })
  const p = pendientes.get(m.id)
  if (!p) return // lo cancelaron: el trabajo siguió, pero ya nadie espera su respuesta
  if (m.tipo === 'datos') return recibir(p, m.bytes)
  pendientes.delete(m.id)
  if (m.tipo === 'fin') {
    if (p.flujo) p.flujo.close()
    else p.resolver(respuestaDeError('La respuesta llegó incompleta.'))
  } else if (m.tipo === 'error') {
    if (p.flujo) p.flujo.error(new Error(m.texto))
    else p.resolver(respuestaDeError(`No pude terminar: ${m.texto}`))
  }
}

async function alTrabajador(pedido: Request, raiz: string): Promise<Response> {
  await listo
  const ruta = '/' + pedido.url.slice(raiz.length)
  const cuerpo = pedido.method === 'GET' || pedido.method === 'HEAD' ? null : new Uint8Array(await pedido.arrayBuffer())
  const cabeceras: Record<string, string> = {}
  pedido.headers.forEach((valor, nombre) => (cabeceras[nombre] = valor))
  const id = siguiente++
  return new Promise<Response>((resolver, rechazar) => {
    const p: Pendiente = { resolver, rechazar, cabeza: new Uint8Array(0), flujo: null }
    pendientes.set(id, p)
    pedido.signal?.addEventListener('abort', () => {
      pendientes.delete(id)
      const error = new DOMException('Se canceló el pedido.', 'AbortError')
      if (p.flujo) p.flujo.error(error)
      else rechazar(error)
    })
    trabajador.postMessage({ tipo: 'pedido', id, metodo: pedido.method, ruta, cabeceras, cuerpo }, cuerpo ? [cuerpo.buffer] : [])
  })
}

/** Arranca el Worker y desvía a él los pedidos a api/. Se llama una vez, antes de dibujar la interfaz. */
export function iniciarWeb() {
  trabajador = new Worker(new URL('./trabajador.ts', import.meta.url), { type: 'module' })
  trabajador.onmessage = alMensaje
  trabajador.onerror = (e) => cambiarArranque({ fase: 'error', texto: e.message || 'El motor no pudo partir.' })
  listo = new Promise((resolver, rechazar) => {
    oyentes.add(() => {
      if (arranque.fase === 'listo') resolver()
      if (arranque.fase === 'error') rechazar(new Error(arranque.texto))
    })
  })
  listo.catch(() => {})
  const raiz = new URL('./', document.baseURI).href
  const api = new URL('api/', document.baseURI).href
  trabajador.postMessage({ tipo: 'iniciar', base: raiz, pyodide: new URL(URL_PYODIDE, document.baseURI).href })
  const original = window.fetch.bind(window)
  window.fetch = (entrada: RequestInfo | URL, opciones?: RequestInit) => {
    const pedido = new Request(entrada, opciones)
    return pedido.url.startsWith(api) ? alTrabajador(pedido, raiz) : original(entrada, opciones)
  }
}
