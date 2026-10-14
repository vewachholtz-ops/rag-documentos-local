// La pantalla de la versión web mientras el motor parte: la primera vez baja Python para el navegador, así que
// se dice qué está pasando y por qué tarda. Si no puede partir, lo explica y ofrece instalar la app.
import type { ReactNode } from 'react'
import { Logo } from '../componentes/Marco'
import { Boton } from '../ui/boton'
import { Girando } from '../ui/piezas'
import { URL_INSTALAR } from './config'
import { useArranque } from './puente'

export function Arranque({ children }: { children: ReactNode }) {
  const a = useArranque()
  if (a.fase === 'listo') return children
  return (
    <main className="flex min-h-dvh items-center justify-center bg-fondo p-6">
      <div className="w-full max-w-md rounded-xl border bg-superficie p-7 shadow-capa">
        <div className="flex items-center gap-2.5">
          <Logo className="size-8" />
          <span className="font-display text-2xl font-semibold tracking-tight">Tesela</span>
        </div>
        {a.fase === 'cargando' ? (
          <>
            <p className="mt-6 flex items-center gap-2.5 text-[15px] font-medium" role="status">
              <Girando className="size-5 text-acento" />
              {a.texto}…
            </p>
            <p className="mt-4 text-[13.5px] leading-relaxed text-tinta-suave">
              Esta es la versión web: el motor corre aquí, en tu navegador, y tus documentos quedan guardados en él. No
              se suben a ningún servidor.
            </p>
          </>
        ) : (
          <>
            <p className="mt-6 text-[15px] font-medium text-peligro" role="alert">
              No pude abrir el motor en este navegador.
            </p>
            <p className="mt-2 text-[13.5px] leading-relaxed text-tinta-suave">
              {a.texto}. Revisa tu conexión (la primera vez baja Python) y reintenta, o instala Tesela en tu computador.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Boton variante="principal" onClick={() => location.reload()}>
                Reintentar
              </Boton>
              <a
                href={URL_INSTALAR}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-9 items-center rounded-md border border-linea bg-superficie px-3.5 text-sm font-medium hover:bg-hundida"
              >
                Instalar Tesela
              </a>
            </div>
          </>
        )}
      </div>
    </main>
  )
}
