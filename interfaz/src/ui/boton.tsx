import { type ButtonHTMLAttributes, forwardRef } from 'react'
import { cn } from '../lib/utiles'

const VARIANTES = {
  principal: 'bg-primario text-sobre-primario hover:bg-primario-hondo border border-transparent',
  contorno: 'bg-superficie text-tinta border border-linea hover:bg-hundida',
  fantasma: 'bg-transparent text-tinta-suave hover:bg-hundida hover:text-tinta border border-transparent',
  peligro: 'bg-peligro text-white hover:opacity-90 border border-transparent',
  'contorno-peligro': 'bg-superficie text-peligro border border-linea hover:bg-peligro-tinte',
}
const TAMANOS = {
  sm: 'h-8 px-3 text-[13px] gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
  icono: 'h-8 w-8 p-0 justify-center',
  'icono-sm': 'h-7 w-7 p-0 justify-center',
}

export interface PropsBoton extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: keyof typeof VARIANTES
  tamano?: keyof typeof TAMANOS
}

export const Boton = forwardRef<HTMLButtonElement, PropsBoton>(function Boton(
  { variante = 'contorno', tamano = 'md', className, type = 'button', ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        'inline-flex shrink-0 items-center rounded-md font-medium whitespace-nowrap transition-colors',
        'disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0',
        VARIANTES[variante],
        TAMANOS[tamano],
        className,
      )}
      {...props}
    />
  )
})
