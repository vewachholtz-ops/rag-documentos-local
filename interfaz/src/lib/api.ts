// Cliente de la API local (src/rag_local/servidor.py). El contrato está en PLAN.md.

export type Modo = 'buscar' | 'ollama' | 'openai'

export interface Estado {
  modo: Modo
  listo: boolean
  ollama: boolean
  modelo: string
  embeddings: string
  modelos: string[]
  faltan: string[]
  busqueda_por_significado: boolean
  documentos: number
  cuadernos: number
}

export interface Ajustes {
  modo: Modo
  modelo: string
  a_fondo: boolean
  openai: { url: string; modelo: string; hay_clave: boolean; local: boolean }
}

export type TipoDocumento = 'pdf' | 'docx' | 'pptx' | 'xlsx' | 'csv' | 'html' | 'md' | 'txt'

export interface Documento {
  id: string
  nombre: string
  tipo: TipoDocumento
  paginas?: number | null
  trozos: number
  bytes: number
  agregado: string
  por_significado: boolean
  /** Si ya tiene guía (resumen, temas y preguntas). */
  guia: boolean
  /** El enlace de donde vino, si se agregó desde una página web. */
  url?: string
  repetido?: boolean
  cuadernos?: { id: string; nombre: string }[]
}

export interface Guia {
  resumen: string
  temas: string[]
  preguntas: string[]
  modelo: string
  leido: number
  creada: string
}

export type TipoEstudio = 'resumen' | 'guia' | 'faq' | 'cronologia' | 'cuestionario' | 'tarjetas' | 'mapa' | 'propia'

export interface Nota {
  id: string
  titulo: string
  contenido: string
  /** El contenido como HTML seguro (lo arma el servidor). */
  html: string
  origen: 'propia' | 'respuesta' | 'generada'
  creado: string
  actualizado: string
  // las generadas en Estudio
  tipo?: TipoEstudio
  fuentes?: { id: string; nombre: string }[]
  modelo?: string
  leido?: number
  avisos?: string[]
  instruccion?: string
}

export interface FuenteRespuesta {
  n: number
  documento: string
  seccion: string
  citada: boolean
  html: string
  doc_id: string
  pagina?: number | null
  tipo?: Documento['tipo'] | null
}

export interface Respuesta {
  html: string
  texto: string
  frases: { n: number; texto: string }[]
  fuentes: FuenteRespuesta[]
  estado: { tipo: 'alerta' | 'neutro' | 'literal'; texto: string; detalle: string }
  abstencion: boolean
  consulta: string | null
  segundos: number
}

export interface Pasaje {
  n: number
  documento: string
  seccion: string
  doc_id: string
  pagina?: number | null
  tipo?: Documento['tipo'] | null
  html: string
}

export interface Vuelta {
  id: string
  creado: string
  pregunta: string
  modo: Modo
  modelo?: string
  respuesta?: Respuesta
  pasajes?: { pasajes: Pasaje[]; busqueda: string; segundos: number }
}

export interface ResumenCuaderno {
  id: string
  nombre: string
  descripcion: string
  creado: string
  actualizado: string
  fuentes: number
  notas: number
}

export interface ResumenConversacion {
  id: string
  titulo: string
  creado: string
  actualizado: string
  preguntas: number
}

export interface Conversacion extends Omit<ResumenConversacion, 'preguntas'> {
  vueltas: Vuelta[]
}

export type Largo = 'corto' | 'normal' | 'largo'

export interface Cuaderno {
  id: string
  nombre: string
  descripcion: string
  creado: string
  actualizado: string
  documentos: Documento[]
  fuera: string[]
  notas: Nota[]
  /** La usada último primero; las vueltas se piden aparte. */
  conversaciones: ResumenConversacion[]
  estilo: { largo: Largo; instrucciones: string }
  /** Preguntas para empezar, de las guías de las fuentes que entran al chat. */
  sugerencias: string[]
}

export interface Carpeta {
  id: string
  ruta: string
  cuaderno: string | null
  cuaderno_nombre?: string | null
  conectada: string
  sincronizada: string | null
  documentos: number
}

export interface Informe {
  agregados: number
  actualizados: number
  quitados: number
  sin_cambios: number
  omitidos: { archivo: string; texto: string }[]
  errores: { archivo: string; texto: string }[]
}

export type Evento =
  | { tipo: 'paso'; texto: string }
  | { tipo: 'progreso'; hecho: number; total: number; estado?: string }
  | { tipo: 'listo'; documento?: Documento }
  | { tipo: 'vuelta'; vuelta: Vuelta; conversacion: string }
  | { tipo: 'guia'; guia: Guia }
  | { tipo: 'nota'; nota: Nota }
  | { tipo: 'sincronizada'; informe: Informe; carpeta: Carpeta }
  | { tipo: 'error'; texto: string }

export class ErrorApi extends Error {}

// El servidor pone un token nuevo en la página cada vez que se abre la app; sin él no atiende la API. Así ninguna
// otra página ni programa del computador puede usarla aunque adivine el puerto.
const TOKEN = document.querySelector('meta[name="mesa-token"]')?.getAttribute('content') ?? ''

export function llamar(ruta: string, opciones: RequestInit = {}) {
  return fetch(ruta, { ...opciones, headers: { ...(opciones.headers as Record<string, string>), 'X-Mesa-Token': TOKEN } })
}

async function pedir<T>(ruta: string, metodo = 'GET', cuerpo?: unknown): Promise<T> {
  const r = await llamar(`api/${ruta}`, {
    method: metodo,
    cache: 'no-store',
    headers: cuerpo === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  })
  const datos = await r.json().catch(() => ({}))
  if (!r.ok) throw new ErrorApi(datos.error || `El servidor respondió ${r.status}`)
  return datos as T
}

/** Lee una respuesta en líneas JSON y entrega cada evento; devuelve el último. */
async function flujo(respuesta: Promise<Response>, alEvento: (e: Evento) => void): Promise<Evento> {
  let r: Response
  try {
    r = await respuesta
  } catch {
    throw new ErrorApi('No hay conexión con Tesela. Vuelve a abrir la aplicación y reintenta.')
  }
  if (!r.ok || !r.body) {
    const datos = await r.json().catch(() => ({}))
    throw new ErrorApi(datos.error || `El servidor respondió ${r.status}`)
  }
  const lector = r.body.getReader()
  const decodificador = new TextDecoder()
  let resto = ''
  let ultimo: Evento | null = null
  for (;;) {
    const { done, value } = await lector.read()
    resto += decodificador.decode(value, { stream: !done })
    const lineas = resto.split('\n')
    resto = done ? '' : (lineas.pop() ?? '')
    for (const linea of lineas) {
      if (!linea.trim()) continue
      ultimo = JSON.parse(linea) as Evento
      alEvento(ultimo)
    }
    if (done) break
  }
  if (!ultimo) throw new ErrorApi('La respuesta llegó vacía.')
  return ultimo
}

export const api = {
  estado: () => pedir<Estado>('estado'),
  ajustes: () => pedir<Ajustes>('ajustes'),
  cambiarAjustes: (cambios: Partial<Omit<Ajustes, 'openai'>> & { openai?: Record<string, string> }) =>
    pedir<Ajustes>('ajustes', 'PUT', cambios),

  documentos: () => pedir<{ documentos: Documento[] }>('documentos').then((d) => d.documentos),
  documento: (id: string) => pedir<{ documento: Documento; html: string; guia: Guia | null }>(`documentos/${id}`),
  borrarDocumento: (id: string) => pedir(`documentos/${id}`, 'DELETE'),
  original: (id: string, pagina?: number | null) =>
    `api/documentos/${id}/original${pagina ? `#page=${pagina}` : ''}`,

  cuadernos: () => pedir<{ cuadernos: ResumenCuaderno[] }>('cuadernos').then((d) => d.cuadernos),
  cuaderno: (id: string) => pedir<{ cuaderno: Cuaderno }>(`cuadernos/${id}`).then((d) => d.cuaderno),
  crearCuaderno: (nombre: string, descripcion = '') =>
    pedir<{ cuaderno: Cuaderno }>('cuadernos', 'POST', { nombre, descripcion }).then((d) => d.cuaderno),
  cambiarCuaderno: (
    id: string,
    cambios: { nombre?: string; descripcion?: string; fuera?: string[]; estilo?: Partial<Cuaderno['estilo']> },
  ) =>
    pedir<{ cuaderno: Cuaderno }>(`cuadernos/${id}`, 'PATCH', cambios).then((d) => d.cuaderno),
  borrarCuaderno: (id: string) => pedir(`cuadernos/${id}`, 'DELETE'),
  enlazar: (id: string, doc: string) => pedir(`cuadernos/${id}/documentos/${doc}`, 'PUT'),
  desenlazar: (id: string, doc: string) => pedir(`cuadernos/${id}/documentos/${doc}`, 'DELETE'),

  crearNota: (id: string, nota: { titulo: string; contenido: string; origen?: Nota['origen'] }) =>
    pedir<{ nota: Nota }>(`cuadernos/${id}/notas`, 'POST', nota).then((d) => d.nota),
  cambiarNota: (id: string, nid: string, cambios: { titulo?: string; contenido?: string }) =>
    pedir<{ nota: Nota }>(`cuadernos/${id}/notas/${nid}`, 'PATCH', cambios).then((d) => d.nota),
  borrarNota: (id: string, nid: string) => pedir(`cuadernos/${id}/notas/${nid}`, 'DELETE'),
  conversacion: (id: string, conversacion: string) =>
    pedir<{ conversacion: Conversacion }>(`cuadernos/${id}/conversaciones/${conversacion}`).then((d) => d.conversacion),
  renombrarConversacion: (id: string, conversacion: string, titulo: string) =>
    pedir(`cuadernos/${id}/conversaciones/${conversacion}`, 'PATCH', { titulo }),
  borrarConversacion: (id: string, conversacion: string) => pedir(`cuadernos/${id}/conversaciones/${conversacion}`, 'DELETE'),

  /** Sube un archivo (a la biblioteca o a un cuaderno) y entrega el avance. */
  subir: (archivo: File, cuaderno: string | null, alEvento: (e: Evento) => void) =>
    flujo(
      llamar(cuaderno ? `api/cuadernos/${cuaderno}/documentos` : 'api/documentos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream', 'X-Nombre': encodeURIComponent(archivo.name) },
        body: archivo,
      }),
      alEvento,
    ),

  preguntar: (cuaderno: string, pregunta: string, conversacion: string | null, alEvento: (e: Evento) => void) =>
    flujo(
      llamar(`api/cuadernos/${cuaderno}/preguntar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pregunta, conversacion }),
      }),
      alEvento,
    ),

  /** Una nota de Estudio con las fuentes del chat. Cortar `senal` la cancela también en el servidor. */
  generar: (cuaderno: string, tipo: TipoEstudio, instruccion: string, alEvento: (e: Evento) => void, senal?: AbortSignal) =>
    flujo(
      llamar(`api/cuadernos/${cuaderno}/generar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo, instruccion }),
        signal: senal,
      }),
      alEvento,
    ),

  escribirGuia: (documento: string, alEvento: (e: Evento) => void, senal?: AbortSignal) =>
    flujo(
      llamar(`api/documentos/${documento}/guia`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
        signal: senal,
      }),
      alEvento,
    ),

  agregarEnlace: (url: string, cuaderno: string | null, alEvento: (e: Evento) => void) =>
    flujo(
      llamar('api/enlaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, cuaderno }),
      }),
      alEvento,
    ),

  carpetas: () => pedir<{ carpetas: Carpeta[] }>('carpetas').then((d) => d.carpetas),
  conectarCarpeta: (ruta: string, cuaderno: string | null) =>
    pedir<{ carpeta: Carpeta }>('carpetas', 'POST', { ruta, cuaderno }).then((d) => d.carpeta),
  desconectarCarpeta: (id: string) => pedir(`carpetas/${id}`, 'DELETE'),
  sincronizarCarpeta: (id: string, alEvento: (e: Evento) => void) =>
    flujo(
      llamar(`api/carpetas/${id}/sincronizar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      }),
      alEvento,
    ),

  descargarModelo: (modelo: string, alEvento: (e: Evento) => void) =>
    flujo(
      llamar('api/modelos/descargar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modelo }),
      }),
      alEvento,
    ),
}

export const TIPOS_ACEPTADOS = '.pdf,.docx,.pptx,.xlsx,.csv,.html,.htm,.md,.markdown,.txt'
export const NO_SE_PUEDE = 'Ese tipo de archivo no se puede agregar: usa PDF, Word, PowerPoint, Excel, CSV, HTML, Markdown o texto.'
export const TAMANO_MAXIMO = 30 * 1024 * 1024
