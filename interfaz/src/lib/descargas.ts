// Descargas de modelos de Ollama: pueden durar muchos minutos, así que el avance vive fuera de los componentes
// y se sigue viendo aunque se cambie de página.
import { useSyncExternalStore } from 'react'
import { api } from './api'

export interface Descarga {
  modelo: string
  hecho: number
  total: number
  estado: string
  error?: string
}

let descargas: Record<string, Descarga> = {}
const oyentes = new Set<() => void>()

function publicar(modelo: string, d: Descarga | null) {
  const copia = { ...descargas }
  if (d) copia[modelo] = d
  else delete copia[modelo]
  descargas = copia
  oyentes.forEach((o) => o())
}

export function useDescargas() {
  return useSyncExternalStore(
    (o) => {
      oyentes.add(o)
      return () => oyentes.delete(o)
    },
    () => descargas,
  )
}

export async function descargar(modelo: string, alTerminar: () => void) {
  if (descargas[modelo] && !descargas[modelo].error) return
  publicar(modelo, { modelo, hecho: 0, total: 0, estado: 'Empezando' })
  try {
    const final = await api.descargarModelo(modelo, (e) => {
      if (e.tipo === 'progreso') publicar(modelo, { modelo, hecho: e.hecho, total: e.total, estado: e.estado ?? '' })
    })
    if (final.tipo === 'error') throw new Error(final.texto)
    publicar(modelo, null)
  } catch (error) {
    publicar(modelo, { modelo, hecho: 0, total: 0, estado: '', error: (error as Error).message })
  }
  alTerminar()
}
