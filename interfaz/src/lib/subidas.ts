import { useCallback, useRef, useState } from 'react'
import { toast } from 'sonner'
import { api, type Evento, NO_SE_PUEDE, TAMANO_MAXIMO } from './api'
import { CLAVES, useRefrescar } from './consultas'
import { dominio } from './utiles'

export interface Subida {
  clave: string
  nombre: string
  paso: string
  avance: number // 0 a 1
  error?: string
}

interface Trabajo {
  clave: string
  nombre: string
  enviar: (alEvento: (e: Evento) => void) => Promise<Evento>
}

const ACEPTADOS = /\.(pdf|docx|pptx|xlsx|csv|html?|md|markdown|txt)$/i

/** Agrega archivos y enlaces de a uno (el modelo de embeddings atiende uno a la vez) y muestra el avance de cada uno. */
export function useSubidas(cuaderno: string | null, avisarListo = false) {
  const [subidas, setSubidas] = useState<Subida[]>([])
  const cola = useRef<Trabajo[]>([])
  const trabajando = useRef(false)
  const refrescar = useRefrescar()

  const cambiar = (clave: string, cambios: Partial<Subida>) =>
    setSubidas((s) => s.map((x) => (x.clave === clave ? { ...x, ...cambios } : x)))

  const procesar = useCallback(async () => {
    if (trabajando.current) return
    trabajando.current = true
    while (cola.current.length) {
      const { clave, nombre, enviar } = cola.current.shift()!
      cambiar(clave, { paso: 'Leyendo', avance: 0.05 })
      try {
        const final = await enviar((e) => {
          if (e.tipo === 'paso') cambiar(clave, { paso: e.texto })
          if (e.tipo === 'progreso' && e.total)
            cambiar(clave, { paso: 'Preparando la búsqueda', avance: 0.1 + 0.9 * (e.hecho / e.total) })
        })
        if (final.tipo === 'error') throw new Error(final.texto)
        const agregado = final.tipo === 'listo' && final.documento ? final.documento.nombre : nombre
        if (final.tipo === 'listo' && final.documento?.repetido)
          toast(`«${agregado}» ya estaba en la biblioteca`, {
            description: cuaderno ? 'Quedó enlazado a este cuaderno.' : undefined,
          })
        else if (avisarListo) toast.success(`Agregaste «${agregado}»`)
        setSubidas((s) => s.filter((x) => x.clave !== clave))
      } catch (error) {
        cambiar(clave, { error: (error as Error).message, avance: 1 })
      }
      await refrescar(CLAVES.documentos, CLAVES.estado, CLAVES.cuadernos, ...(cuaderno ? [CLAVES.cuaderno(cuaderno)] : []))
    }
    trabajando.current = false
  }, [cuaderno, refrescar, avisarListo])

  const encolar = useCallback(
    (nuevas: Subida[], trabajos: Trabajo[]) => {
      cola.current.push(...trabajos)
      setSubidas((s) => [...s, ...nuevas])
      void procesar()
    },
    [procesar],
  )

  const agregar = useCallback(
    (archivos: FileList | File[]) => {
      const nuevas: Subida[] = []
      const trabajos: Trabajo[] = []
      for (const archivo of Array.from(archivos)) {
        const clave = `${archivo.name}-${archivo.size}-${Math.random().toString(36).slice(2)}`
        if (!ACEPTADOS.test(archivo.name)) {
          nuevas.push({ clave, nombre: archivo.name, paso: '', avance: 1, error: NO_SE_PUEDE })
          continue
        }
        if (archivo.size > TAMANO_MAXIMO) {
          nuevas.push({ clave, nombre: archivo.name, paso: '', avance: 1, error: 'El archivo pesa más de 30 MB.' })
          continue
        }
        nuevas.push({ clave, nombre: archivo.name, paso: 'En espera', avance: 0 })
        trabajos.push({ clave, nombre: archivo.name, enviar: (alEvento) => api.subir(archivo, cuaderno, alEvento) })
      }
      encolar(nuevas, trabajos)
    },
    [cuaderno, encolar],
  )

  const agregarEnlace = useCallback(
    (url: string) => {
      const clave = `enlace-${Math.random().toString(36).slice(2)}`
      const nombre = dominio(/^https?:\/\//i.test(url) ? url : `https://${url}`)
      encolar(
        [{ clave, nombre, paso: 'En espera', avance: 0 }],
        [{ clave, nombre, enviar: (alEvento) => api.agregarEnlace(url, cuaderno, alEvento) }],
      )
    },
    [cuaderno, encolar],
  )

  const descartar = (clave: string) => setSubidas((s) => s.filter((x) => x.clave !== clave))
  return { subidas, agregar, agregarEnlace, descartar }
}
