// Piezas de interfaz sobre Radix (accesibles por teclado y lector de pantalla), con el estilo de Tesela.
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import * as Dialog from '@radix-ui/react-dialog'
import * as Menu from '@radix-ui/react-dropdown-menu'
import * as Tooltip from '@radix-ui/react-tooltip'
import { LoaderCircle, X } from 'lucide-react'
import {
  type ComponentProps,
  type ElementType,
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from 'react'
import { cn } from '../lib/utiles'
import { Boton } from './boton'

// ---- diálogo ----
export function Dialogo({
  abierto,
  alCambiar,
  titulo,
  descripcion,
  children,
  ancho = 'max-w-lg',
  className,
}: {
  abierto: boolean
  alCambiar: (abierto: boolean) => void
  titulo: ReactNode
  descripcion?: ReactNode
  children: ReactNode
  ancho?: string
  className?: string
}) {
  return (
    <Dialog.Root open={abierto} onOpenChange={alCambiar}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/35 data-[state=open]:animate-[aparecer_120ms_ease-out]" />
        <Dialog.Content
          className={cn(
            'fixed top-1/2 left-1/2 z-50 flex max-h-[min(88vh,900px)] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col',
            'rounded-lg border bg-elevada shadow-capa',
            ancho,
            className,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b py-4 pr-14 pl-5">
            <div className="min-w-0">
              <Dialog.Title className="font-display text-lg leading-tight font-semibold">{titulo}</Dialog.Title>
              {descripcion ? (
                <Dialog.Description className="mt-1 text-[13px] text-tinta-suave">{descripcion}</Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">{typeof titulo === 'string' ? titulo : ''}</Dialog.Description>
              )}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
          {/* al final del orden de tabulación: al abrir, el foco va a lo primero del contenido, no a «Cerrar» */}
          <Dialog.Close asChild>
            <Boton variante="fantasma" tamano="icono" aria-label="Cerrar" className="absolute top-3.5 right-3.5">
              <X />
            </Boton>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

// ---- confirmar algo que no se deshace ----
export function Confirmar({
  abierto,
  alCambiar,
  titulo,
  descripcion,
  accion,
  alConfirmar,
  ocupado,
}: {
  abierto: boolean
  alCambiar: (abierto: boolean) => void
  titulo: string
  descripcion: ReactNode
  accion: string
  alConfirmar: () => void
  ocupado?: boolean
}) {
  return (
    <AlertDialog.Root open={abierto} onOpenChange={alCambiar}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-black/35" />
        <AlertDialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-elevada p-5 shadow-capa">
          <AlertDialog.Title className="font-display text-lg font-semibold">{titulo}</AlertDialog.Title>
          <AlertDialog.Description className="mt-2 text-sm text-tinta-suave">{descripcion}</AlertDialog.Description>
          <div className="mt-5 flex justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <Boton variante="contorno">Cancelar</Boton>
            </AlertDialog.Cancel>
            <Boton
              variante="peligro"
              disabled={ocupado}
              onClick={(e) => {
                e.preventDefault()
                alConfirmar()
              }}
            >
              {ocupado && <LoaderCircle className="animate-spin" />}
              {accion}
            </Boton>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}

// ---- menú ----
export const MenuRaiz = Menu.Root
export const MenuDisparador = Menu.Trigger

export function MenuContenido({ className, ...props }: ComponentProps<typeof Menu.Content>) {
  return (
    <Menu.Portal>
      <Menu.Content
        sideOffset={4}
        align="end"
        className={cn('z-50 min-w-48 rounded-md border bg-elevada p-1 shadow-flota', className)}
        {...props}
      />
    </Menu.Portal>
  )
}

export function MenuItem({
  className,
  icono: Icono,
  peligro,
  children,
  ...props
}: ComponentProps<typeof Menu.Item> & { icono?: ElementType; peligro?: boolean }) {
  return (
    <Menu.Item
      className={cn(
        'flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-[13px] outline-none select-none',
        'data-[disabled]:opacity-50 data-[highlighted]:bg-hundida [&_svg]:size-4',
        peligro ? 'text-peligro' : 'text-tinta',
        className,
      )}
      {...props}
    >
      {Icono && <Icono />}
      {children}
    </Menu.Item>
  )
}

export function MenuSeparador() {
  return <Menu.Separator className="my-1 h-px bg-linea" />
}

// ---- ayuda al pasar el mouse ----
export function Ayuda({ texto, children, lado = 'top' }: { texto: ReactNode; children: ReactNode; lado?: 'top' | 'right' | 'bottom' | 'left' }) {
  return (
    <Tooltip.Root delayDuration={300}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side={lado}
          sideOffset={6}
          className="z-50 max-w-64 rounded-md bg-tinta px-2.5 py-1.5 text-xs text-fondo shadow-flota"
        >
          {texto}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}
export const ProveedorAyuda = Tooltip.Provider

// ---- campos ----
export const Campo = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Campo(
  { className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        'h-9 w-full rounded-md border bg-superficie px-3 text-sm placeholder:text-tinta-tenue',
        'focus-visible:border-cita focus-visible:outline-none',
        className,
      )}
      {...props}
    />
  )
})

export const Texto = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Texto(
  { className, ...props },
  ref,
) {
  return (
    <textarea
      ref={ref}
      className={cn(
        'w-full rounded-md border bg-superficie px-3 py-2 text-sm placeholder:text-tinta-tenue',
        'focus-visible:border-cita focus-visible:outline-none',
        className,
      )}
      {...props}
    />
  )
})

export function Etiqueta({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[13px] font-medium">
      {children}
    </label>
  )
}

// ---- otros ----
export function Girando({ className }: { className?: string }) {
  return <LoaderCircle className={cn('size-4 animate-spin text-tinta-tenue', className)} aria-hidden />
}

export function Vacio({
  icono: Icono,
  titulo,
  children,
  accion,
}: {
  icono: ElementType
  titulo: string
  children?: ReactNode
  accion?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center px-4 py-10 text-center">
      <Icono className="mb-3 size-9 text-tinta-tenue opacity-70" aria-hidden />
      <p className="font-medium">{titulo}</p>
      {children && <p className="mt-1 max-w-72 text-[13px] text-tinta-suave">{children}</p>}
      {accion && <div className="mt-4">{accion}</div>}
    </div>
  )
}

export function Insignia({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-sm bg-hundida px-1.5 py-0.5 text-[11px] font-medium text-tinta-suave',
        className,
      )}
    >
      {children}
    </span>
  )
}

export function Barra({ valor }: { valor: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-hundida" role="progressbar" aria-valuenow={Math.round(valor * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full bg-cita transition-[width] duration-300" style={{ width: `${Math.max(2, valor * 100)}%` }} />
    </div>
  )
}
