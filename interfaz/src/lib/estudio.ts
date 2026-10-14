// Lo que escribe el modelo (las notas de Estudio y la guía de cada fuente) puede tardar minutos con un modelo local:
// el avance vive fuera de los componentes, para seguir viéndose al cambiar de página, y se puede cancelar.
import { useSyncExternalStore } from 'react'
import { toast } from 'sonner'
import { api, type Evento, type Nota, type TipoEstudio } from './api'

export const TIPOS_ESTUDIO: Record<TipoEstudio, { nombre: string; que: string; descripcion: string }> = {
  resumen: { nombre: 'Resumen', que: 'el resumen', descripcion: 'Lo esencial y los datos clave, por tema' },
  guia: { nombre: 'Guía de estudio', que: 'la guía de estudio', descripcion: 'Conceptos, preguntas de repaso con respuestas y glosario' },
  faq: { nombre: 'Preguntas frecuentes', que: 'las preguntas frecuentes', descripcion: 'Lo que alguien preguntaría, con su respuesta' },
  cronologia: { nombre: 'Cronología', que: 'la cronología', descripcion: 'Fechas y hechos en orden, y quién es quién' },
  cuestionario: { nombre: 'Cuestionario', que: 'el cuestionario', descripcion: '10 preguntas de alternativas para ponerte a prueba' },
  tarjetas: { nombre: 'Tarjetas', que: 'las tarjetas', descripcion: 'Pregunta por un lado, respuesta por el otro' },
  mapa: { nombre: 'Mapa de ideas', que: 'el mapa de ideas', descripcion: 'Los temas y cómo se relacionan' },
  propia: { nombre: 'Personalizado', que: 'lo que pediste', descripcion: 'Escribe tú qué quieres que haga' },
}

export interface Trabajo {
  titulo: string
  paso: string
  error?: string
  controlador: AbortController
}

let trabajos: Record<string, Trabajo> = {}
const oyentes = new Set<() => void>()

function publicar(clave: string, t: Trabajo | null) {
  const copia = { ...trabajos }
  if (t) copia[clave] = t
  else delete copia[clave]
  trabajos = copia
  oyentes.forEach((o) => o())
}

export function useTrabajos() {
  return useSyncExternalStore(
    (o) => {
      oyentes.add(o)
      return () => oyentes.delete(o)
    },
    () => trabajos,
  )
}

export const claveNota = (cuaderno: string) => `nota:${cuaderno}`
export const claveGuia = (documento: string) => `guia:${documento}`

export function cancelar(clave: string) {
  trabajos[clave]?.controlador.abort()
}

export function descartar(clave: string) {
  publicar(clave, null)
}

async function correr(clave: string, titulo: string, enviar: (alEvento: (e: Evento) => void, senal: AbortSignal) => Promise<Evento>) {
  if (trabajos[clave] && !trabajos[clave].error) return null
  const controlador = new AbortController()
  publicar(clave, { titulo, paso: 'Empezando', controlador })
  try {
    const final = await enviar((e) => {
      if (e.tipo === 'paso') publicar(clave, { titulo, paso: e.texto, controlador })
    }, controlador.signal)
    if (final.tipo === 'error') throw new Error(final.texto)
    publicar(clave, null)
    return final
  } catch (error) {
    if (controlador.signal.aborted) {
      publicar(clave, null)
      toast('Cancelado', { description: `Ya no se escribe ${titulo}.` })
    } else publicar(clave, { titulo, paso: '', error: (error as Error).message, controlador })
    return null
  }
}

/** Escribe una nota de Estudio con las fuentes que entran al chat. Devuelve la nota, o null si falló o se canceló. */
export async function generarNota(cuaderno: string, tipo: TipoEstudio, instruccion = ''): Promise<Nota | null> {
  const final = await correr(claveNota(cuaderno), TIPOS_ESTUDIO[tipo].que, (alEvento, senal) =>
    api.generar(cuaderno, tipo, instruccion, alEvento, senal),
  )
  return final?.tipo === 'nota' ? final.nota : null
}

export async function escribirGuia(documento: string): Promise<boolean> {
  const final = await correr(claveGuia(documento), 'la guía', (alEvento, senal) => api.escribirGuia(documento, alEvento, senal))
  return final?.tipo === 'guia'
}
