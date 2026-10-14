// Sincronizar una carpeta puede tardar (lee y prepara cada documento): el avance vive fuera de los componentes, para
// verse igual en el diálogo, en el cuaderno y en la página de Fuentes, y no perderse al cambiar de página.
import { useSyncExternalStore } from 'react'
import { api, type Informe } from './api'

export interface Sincronizacion {
  paso: string
  informe?: Informe
  error?: string
}

let estado: Record<string, Sincronizacion> = {}
const oyentes = new Set<() => void>()

function publicar(id: string, s: Sincronizacion) {
  estado = { ...estado, [id]: s }
  oyentes.forEach((o) => o())
}

export function useSincronizaciones() {
  return useSyncExternalStore(
    (o) => {
      oyentes.add(o)
      return () => oyentes.delete(o)
    },
    () => estado,
  )
}

export function sincronizacionDe(id: string): Sincronizacion | undefined {
  return estado[id]
}

export function enCurso(s?: Sincronizacion) {
  return !!s && !s.informe && !s.error
}

export async function sincronizar(id: string, alTerminar: () => void) {
  if (enCurso(estado[id])) return
  publicar(id, { paso: 'Empezando' })
  try {
    const final = await api.sincronizarCarpeta(id, (e) => {
      if (e.tipo === 'paso') publicar(id, { paso: e.texto })
    })
    if (final.tipo === 'error') throw new Error(final.texto)
    if (final.tipo === 'sincronizada') publicar(id, { paso: '', informe: final.informe })
  } catch (error) {
    publicar(id, { paso: '', error: (error as Error).message })
  }
  alTerminar()
}

export function resumen(i: Informe) {
  const partes: string[] = []
  if (i.agregados) partes.push(`${i.agregados} ${i.agregados === 1 ? 'nuevo' : 'nuevos'}`)
  if (i.actualizados) partes.push(`${i.actualizados} ${i.actualizados === 1 ? 'actualizado' : 'actualizados'}`)
  if (i.quitados) partes.push(`${i.quitados} ${i.quitados === 1 ? 'quitado' : 'quitados'}`)
  if (!partes.length) partes.push('Sin cambios')
  return partes.join(', ')
}
