// Panel de trabajo de Tesela: título, acciones y contenido con desplazamiento independiente.
import { ChevronLeft } from 'lucide-react'
import type { ElementType, ReactNode } from 'react'
import { cn } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Ayuda } from '../ui/piezas'

export function Columna({
  titulo,
  etiqueta = titulo,
  color,
  icono: Icono,
  acciones,
  plegada,
  alPlegar,
  children,
  pie,
  sinRelleno,
}: {
  titulo: string
  /** El nombre de la región para lectores de pantalla, si el título visible es más largo. */
  etiqueta?: string
  color: string
  icono: ElementType
  acciones?: ReactNode
  plegada?: boolean
  alPlegar?: (plegada: boolean) => void
  children: ReactNode
  pie?: ReactNode
  /** El contenido maneja su propio relleno y desplazamiento (el chat). */
  sinRelleno?: boolean
}) {
  if (plegada && alPlegar) {
    return (
      <Ayuda texto={`Mostrar ${etiqueta.toLowerCase()}`} lado="right">
        <button
          onClick={() => alPlegar(false)}
          className="group flex h-full min-h-0 w-12 flex-col items-center justify-center gap-3 rounded-lg border bg-superficie py-6 transition-all hover:bg-hundida/50"
          aria-label={`Mostrar ${etiqueta.toLowerCase()}`}
        >
          <Icono className="size-5 shrink-0 text-tinta-suave transition-colors group-hover:text-tinta" aria-hidden />
          <span className="rotate-180 text-xs font-medium whitespace-nowrap text-tinta-suave [writing-mode:vertical-rl] group-hover:text-tinta">
            {etiqueta}
          </span>
        </button>
      </Ayuda>
    )
  }
  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border bg-superficie" aria-label={etiqueta}>
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-linea-suave px-4 py-3">
        <h2 className="flex min-w-0 items-center gap-2 text-sm font-semibold text-tinta">
          <span aria-hidden className={cn('flex size-6 shrink-0 items-center justify-center rounded-md', color)}><Icono className="size-3.5 text-superficie" /></span>
          <span className="truncate">{titulo}</span>
        </h2>
        <div className="flex items-center gap-2">
          {acciones}
          {alPlegar && (
            <Ayuda texto={`Plegar ${etiqueta.toLowerCase()}`}>
              <Boton
                variante="fantasma"
                tamano="icono-sm"
                className="hidden lg:inline-flex"
                onClick={() => alPlegar(true)}
                aria-label={`Plegar ${etiqueta.toLowerCase()}`}
              >
                <ChevronLeft />
              </Boton>
            </Ayuda>
          )}
        </div>
      </header>
      <div className={cn('min-h-0 flex-1', sinRelleno ? 'flex flex-col' : 'overflow-y-auto p-3')}>{children}</div>
      {pie}
    </section>
  )
}
