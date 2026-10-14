// Las notas de Estudio llegan en Markdown con un formato pedido (ver src/rag_local/estudio.py). Aquí se leen para
// mostrarlas como mapa, tarjetas o cuestionario. Si el modelo no siguió el formato, se muestran como texto.

const VINETA = /^(\s*)(?:[-*+•]|\d{1,3}[.)])\s+(.*)$/

function limpio(texto: string) {
  return texto
    .replace(/\*\*|__|`/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\s*[*_]+|[*_]+\s*$/g, '')
    .trim()
}

// ---- mapa de ideas ----
export interface Nodo {
  id: string
  texto: string
  hijos: Nodo[]
}

/** El título es el centro; las viñetas, sus ramas según la sangría. Los subtítulos «##» también cuentan como ramas. */
export function leerMapa(titulo: string, contenido: string): Nodo | null {
  const raiz: Nodo = { id: '0', texto: titulo, hijos: [] }
  const pila: { nivel: number; nodo: Nodo }[] = [{ nivel: -1, nodo: raiz }]
  let n = 0
  let base = 0 // sangría extra bajo un subtítulo
  for (const linea of contenido.split('\n')) {
    const subtitulo = /^\s{0,3}#{1,6}\s+(.+)$/.exec(linea)
    const m = VINETA.exec(linea)
    let nivel: number
    let texto: string
    if (subtitulo) {
      nivel = 0
      texto = subtitulo[1]
      base = 2
    } else if (m) {
      nivel = m[1].replace(/\t/g, '  ').length + base
      texto = m[2]
    } else continue
    texto = limpio(texto)
    if (!texto) continue
    while (pila.length > 1 && pila[pila.length - 1].nivel >= nivel) pila.pop()
    const nodo: Nodo = { id: String(++n), texto, hijos: [] }
    pila[pila.length - 1].nodo.hijos.push(nodo)
    pila.push({ nivel, nodo })
  }
  return raiz.hijos.length ? raiz : null
}

export function contarNodos(n: Nodo): number {
  return 1 + n.hijos.reduce((s, h) => s + contarNodos(h), 0)
}

// ---- tarjetas ----
export interface Tarjeta {
  pregunta: string
  respuesta: string
}

const LADO = /^\s*(?:[-*]\s*)?(?:\*\*)?\s*(P|R|Pregunta|Respuesta|Frente|Reverso)\s*(?:\*\*)?\s*[:.]\s*(?:\*\*)?\s*(.*)$/i

export function leerTarjetas(contenido: string): Tarjeta[] | null {
  const tarjetas: Tarjeta[] = []
  let pregunta: string | null = null
  for (const linea of contenido.split('\n')) {
    const m = LADO.exec(linea)
    if (!m) {
      // una respuesta puede seguir en la línea de abajo
      const ultima = tarjetas[tarjetas.length - 1]
      const otra = /^\s*(?:#|\*\*|tarjeta\b|\d+[.)]?\s*$)/i.test(linea)
      if (linea.trim() && pregunta === null && ultima && !otra) ultima.respuesta += ` ${limpio(linea)}`
      continue
    }
    const lado = m[1].toLowerCase()
    const texto = limpio(m[2])
    if (lado === 'p' || lado === 'pregunta' || lado === 'frente') pregunta = texto
    else if (pregunta !== null) {
      tarjetas.push({ pregunta, respuesta: texto })
      pregunta = null
    }
  }
  return tarjetas.length >= 2 ? tarjetas : null
}

// ---- cuestionario ----
export interface Pregunta {
  n: number
  texto: string
  opciones: { letra: string; texto: string }[]
  correcta: string
  porque: string
}

const PREGUNTA = /^\s*(?:#{1,6}\s*)?(?:\*\*)?(?:Pregunta\s+)?(\d{1,2})[.):]\s*(?:\*\*)?\s*(.+?)\s*$/i
const OPCION = /^\s*(?:[-*]\s*)?(?:\*\*)?\(?([a-dA-D])[).]\s*(?:\*\*)?\s*(.+?)\s*$/
const RESPUESTA = /^\s*(?:[-*]\s*)?(?:\*\*)?(\d{1,2})[.):]?\s*(?:\*\*)?\s*(?:[-–—:]\s*)?(?:\*\*)?\(?([a-dA-D])\)?(?![a-zA-ZáéíóúñÁÉÍÓÚÑ])[).:]?\s*(?:\*\*)?\s*(?:[-–—:,]\s*)?(.*)$/

export function leerCuestionario(contenido: string): Pregunta[] | null {
  const [parte, ...resto] = contenido.split(/^\s*#{1,6}\s*Respuestas\b.*$/im)
  if (!resto.length) return null
  const preguntas: Pregunta[] = []
  for (const linea of parte.split('\n')) {
    const opcion = OPCION.exec(linea)
    const actual = preguntas[preguntas.length - 1]
    if (opcion && actual) actual.opciones.push({ letra: opcion[1].toLowerCase(), texto: limpio(opcion[2]) })
    else {
      const p = PREGUNTA.exec(linea)
      if (p) preguntas.push({ n: Number(p[1]), texto: limpio(p[2]), opciones: [], correcta: '', porque: '' })
    }
  }
  for (const linea of resto.join('\n').split('\n')) {
    const r = RESPUESTA.exec(linea)
    const p = r && preguntas.find((x) => x.n === Number(r[1]))
    if (p && r) {
      p.correcta = r[2].toLowerCase()
      p.porque = limpio(r[3].replace(/^porque\s+/i, 'Porque '))
    }
  }
  const buenas = preguntas.filter((p) => p.opciones.length >= 2 && p.opciones.some((o) => o.letra === p.correcta))
  return buenas.length >= 2 ? buenas : null
}
