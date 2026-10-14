import { type ClassValue, clsx } from 'clsx'
import { useEffect, useState } from 'react'
import { twMerge } from 'tailwind-merge'

export function cn(...clases: ClassValue[]) {
  return twMerge(clsx(clases))
}

export function plural(n: number, uno: string, varios: string) {
  return `${n.toLocaleString('es-CL')} ${n === 1 ? uno : varios}`
}

const relativo = new Intl.RelativeTimeFormat('es', { numeric: 'auto' })
const PASOS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
]

/** "hace 3 minutos", "ayer". Las fechas del servidor vienen en hora local, sin zona. */
export function haceCuanto(fecha: string) {
  const segundos = (new Date(fecha).getTime() - Date.now()) / 1000
  if (Number.isNaN(segundos)) return ''
  for (const [unidad, tamano] of PASOS) {
    if (Math.abs(segundos) >= tamano) return relativo.format(Math.round(segundos / tamano), unidad)
  }
  return 'recién'
}

export function tamanoArchivo(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toLocaleString('es-CL', { maximumFractionDigits: 1 })} MB`
}

export const NOMBRE_TIPO = {
  pdf: 'PDF',
  docx: 'Word',
  pptx: 'PowerPoint',
  xlsx: 'Excel',
  csv: 'CSV',
  html: 'HTML',
  md: 'Markdown',
  txt: 'Texto',
} as const

/** «www.ejemplo.cl/ruta» → «ejemplo.cl». */
export function dominio(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/** Un texto en Markdown sin sus marcas, para la vista previa de una nota. */
export function sinMarcas(texto: string) {
  return texto
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*(?:[-*+]|\d+[.)])\s+/gm, '')
    .replace(/\*\*|__|`/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\|?[-:| ]+\|?$/gm, '')
    .replace(/\|/g, ' ')
    .replace(/\n{2,}/g, '\n')
    .trim()
}

// ---- tema: claro, oscuro o el del sistema ----
export type Tema = 'claro' | 'oscuro' | 'sistema'
const CLAVE_TEMA = 'fuente.tema'

export function temaGuardado(): Tema {
  try {
    const t = localStorage.getItem(CLAVE_TEMA)
    if (t === 'claro' || t === 'oscuro' || t === 'sistema') return t
  } catch {
    /* sin almacenamiento: el del sistema */
  }
  return 'sistema'
}

export function aplicarTema(tema: Tema) {
  const oscuro = tema === 'oscuro' || (tema === 'sistema' && matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', oscuro)
  try {
    localStorage.setItem(CLAVE_TEMA, tema)
  } catch {
    /* no importa */
  }
}

// ---- rutas con # (la app es una sola página servida por Python) ----
export type Ruta =
  | { pagina: 'cuadernos' }
  | { pagina: 'cuaderno'; id: string }
  | { pagina: 'biblioteca' }
  | { pagina: 'ajustes' }

export function leerRuta(hash = location.hash): Ruta {
  const partes = hash.replace(/^#\/?/, '').split('/')
  if (partes[0] === 'cuadernos' && /^[0-9a-f]{12}$/.test(partes[1] ?? '')) return { pagina: 'cuaderno', id: partes[1] }
  if (partes[0] === 'biblioteca') return { pagina: 'biblioteca' }
  if (partes[0] === 'ajustes') return { pagina: 'ajustes' }
  return { pagina: 'cuadernos' }
}

export function enlace(ruta: Ruta) {
  return ruta.pagina === 'cuaderno' ? `#/cuadernos/${ruta.id}` : `#/${ruta.pagina}`
}

export function useRuta() {
  const [ruta, setRuta] = useState(leerRuta)
  useEffect(() => {
    const cambiar = () => setRuta(leerRuta())
    addEventListener('hashchange', cambiar)
    return () => removeEventListener('hashchange', cambiar)
  }, [])
  return ruta
}

export function ir(ruta: Ruta) {
  location.hash = enlace(ruta)
}

export function useEsEscritorio() {
  const [es, setEs] = useState(() => matchMedia('(min-width: 1024px)').matches)
  useEffect(() => {
    const m = matchMedia('(min-width: 1024px)')
    const cambiar = () => setEs(m.matches)
    m.addEventListener('change', cambiar)
    return () => m.removeEventListener('change', cambiar)
  }, [])
  return es
}
