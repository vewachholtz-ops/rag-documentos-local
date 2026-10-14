// Avisos entre partes del cuaderno que no están una dentro de la otra: un tema del mapa de ideas o una pregunta de
// la guía que se manda al chat, o una nota recién escrita que se abre.
import { useEffect, useRef } from 'react'

const PREGUNTAR = 'mesa:preguntar'
const ABRIR_NOTA = 'mesa:abrir-nota'

export function pedirAlChat(texto: string) {
  dispatchEvent(new CustomEvent<string>(PREGUNTAR, { detail: texto }))
}

export function abrirNota(id: string) {
  dispatchEvent(new CustomEvent<string>(ABRIR_NOTA, { detail: id }))
}

function useEvento(nombre: string, alRecibir: (valor: string) => void) {
  const ultimo = useRef(alRecibir)
  ultimo.current = alRecibir
  useEffect(() => {
    const oyente = (e: Event) => ultimo.current((e as CustomEvent<string>).detail)
    addEventListener(nombre, oyente)
    return () => removeEventListener(nombre, oyente)
  }, [nombre])
}

export const usePedidosAlChat = (alPedir: (texto: string) => void) => useEvento(PREGUNTAR, alPedir)
export const useAbrirNota = (alAbrir: (id: string) => void) => useEvento(ABRIR_NOTA, alAbrir)
