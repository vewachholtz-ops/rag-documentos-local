import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'

export const CLAVES = {
  estado: ['estado'] as const,
  ajustes: ['ajustes'] as const,
  cuadernos: ['cuadernos'] as const,
  cuaderno: (id: string) => ['cuaderno', id] as const,
  documentos: ['documentos'] as const,
  carpetas: ['carpetas'] as const,
  documento: (id: string) => ['documento', id] as const,
  conversacion: (cuaderno: string, id: string) => ['conversacion', cuaderno, id] as const,
}

export function useEstado() {
  return useQuery({
    queryKey: CLAVES.estado,
    queryFn: api.estado,
    // mientras falte algo (Ollama cerrado, un modelo), se vuelve a mirar cada pocos segundos
    refetchInterval: (q) => (q.state.data && q.state.data.listo ? 30_000 : 4_000),
  })
}

export const useAjustes = () => useQuery({ queryKey: CLAVES.ajustes, queryFn: api.ajustes })
export const useCuadernos = () => useQuery({ queryKey: CLAVES.cuadernos, queryFn: api.cuadernos })
export const useCuaderno = (id: string) => useQuery({ queryKey: CLAVES.cuaderno(id), queryFn: () => api.cuaderno(id) })
export const useDocumentos = () => useQuery({ queryKey: CLAVES.documentos, queryFn: api.documentos })
export const useCarpetas = () => useQuery({ queryKey: CLAVES.carpetas, queryFn: api.carpetas })
export const useConversacion = (cuaderno: string, id: string | null) =>
  useQuery({
    queryKey: CLAVES.conversacion(cuaderno, id ?? ''),
    queryFn: () => api.conversacion(cuaderno, id!),
    enabled: !!id,
    retry: false,
  })

/** Después de cambiar algo, lo que hay que volver a pedir. */
export function useRefrescar() {
  const cliente = useQueryClient()
  return (...claves: (readonly unknown[])[]) =>
    Promise.all(claves.map((queryKey) => cliente.invalidateQueries({ queryKey })))
}
