// Navegación de Tesela: la barra lateral con sus páginas, el modelo en uso y el tema.
import { Book, Bot, ChevronLeft, FileText, Menu, Monitor, Moon, Plus, Sun } from 'lucide-react'
import { type ElementType, type ReactNode, useEffect, useState } from 'react'
import { useEstado } from '../lib/consultas'
import { aplicarTema, cn, enlace, type Ruta, type Tema, temaGuardado } from '../lib/utiles'
import { DialogoNuevoCuaderno } from '../paginas/Cuadernos'
import { Boton } from '../ui/boton'
import { Ayuda, MenuContenido, MenuDisparador, MenuItem, MenuRaiz } from '../ui/piezas'
import { DialogoAgregarFuente } from './AgregarFuente'

/** La marca de Tesela: un mosaico de fuentes; la pieza sin relleno es la que se está citando. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect x="3" y="3" width="15" height="11" rx="3" className="fill-primario" />
      <rect x="21" y="3" width="8" height="11" rx="3" className="fill-primario" />
      <rect x="3" y="17" width="8" height="12" rx="3" className="fill-primario" />
      <rect x="15" y="18" width="13" height="10" rx="2.5" fill="none" className="stroke-primario" strokeWidth="2" />
    </svg>
  )
}

type Item = { nombre: string; ruta: Ruta; icono: ElementType; color?: string }
const ITEMS: Item[] = [
  { nombre: 'Cuadernos', ruta: { pagina: 'cuadernos' }, icono: Book },
  { nombre: 'Fuentes', ruta: { pagina: 'biblioteca' }, icono: FileText },
  { nombre: 'Modelos', ruta: { pagina: 'ajustes' }, icono: Bot },
]

const CLAVE_LATERAL = 'fuente.lateral-cerrada'

export function Marco({ ruta, children }: { ruta: Ruta; children: ReactNode }) {
  const [cerrada, setCerrada] = useState(() => {
    try {
      return localStorage.getItem(CLAVE_LATERAL) === '1'
    } catch {
      return false
    }
  })
  const [nuevoCuaderno, setNuevoCuaderno] = useState(false)
  const [nuevaFuente, setNuevaFuente] = useState(false)
  useEffect(() => {
    try {
      localStorage.setItem(CLAVE_LATERAL, cerrada ? '1' : '0')
    } catch {
      /* no importa */
    }
  }, [cerrada])
  const activa = ruta.pagina === 'cuaderno' ? 'cuadernos' : ruta.pagina

  return (
    <div className="flex h-full min-h-0">
      <aside
        className={cn(
          'mesa-sidebar hidden shrink-0 flex-col bg-fondo-hondo transition-[width] duration-300 md:flex',
          cerrada ? 'w-16' : 'w-52',
        )}
        aria-label="Navegación"
      >
        <div className={cn('group flex h-20 items-center', cerrada ? 'justify-center px-2' : 'justify-between px-5')}>
          {cerrada ? (
            <div className="relative flex w-full items-center justify-center">
              <Logo className="size-6 transition-opacity group-hover:opacity-0" />
              <Boton
                variante="fantasma"
                tamano="icono"
                onClick={() => setCerrada(false)}
                className="absolute opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                aria-label="Abrir la barra lateral"
              >
                <Menu />
              </Boton>
            </div>
          ) : (
            <>
              <a href={enlace({ pagina: 'cuadernos' })} className="flex items-center gap-2.5 rounded-md">
                <Logo className="size-8" />
                <span className="font-display text-2xl font-semibold tracking-tight">Tesela</span>
              </a>
              <Boton variante="fantasma" tamano="sm" onClick={() => setCerrada(true)} aria-label="Cerrar la barra lateral">
                <ChevronLeft />
              </Boton>
            </>
          )}
        </div>

        <nav className={cn('flex-1 space-y-1 py-3', cerrada ? 'px-2' : 'px-3')}>
          <div className="mb-7">
            <MenuRaiz>
              <MenuDisparador asChild>
                <Boton
                  variante="principal"
                  tamano="sm"
                  className={cn('w-full font-display font-bold', cerrada ? 'justify-center px-2' : 'justify-start')}
                  aria-label={cerrada ? 'Nuevo' : undefined}
                >
                  <Plus />
                  {!cerrada && 'Nuevo'}
                </Boton>
              </MenuDisparador>
              <MenuContenido align={cerrada ? 'end' : 'start'} side={cerrada ? 'right' : 'bottom'} className="w-48 min-w-0">
                <MenuItem icono={FileText} onSelect={() => setNuevaFuente(true)}>
                  Fuente
                </MenuItem>
                <MenuItem icono={Book} onSelect={() => setNuevoCuaderno(true)}>
                  Cuaderno
                </MenuItem>
              </MenuContenido>
            </MenuRaiz>
          </div>

          {!cerrada && <p className="mb-3 px-3 text-xs text-tinta-tenue">Tu espacio de trabajo</p>}
          {ITEMS.map((item) => (
            <ItemNavegacion key={item.nombre} item={item} actual={item.ruta.pagina === activa} cerrada={cerrada} />
          ))}
        </nav>

        <div className={cn('space-y-2 border-t p-3', cerrada && 'flex flex-col items-center px-2')}>
          <EstadoModelo compacto={cerrada} />
          <SelectorTema compacto={cerrada} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <BarraMovil activa={activa} />
        <main className="flex min-h-0 flex-1 flex-col">{children}</main>
      </div>
      <DialogoNuevoCuaderno abierto={nuevoCuaderno} alCambiar={setNuevoCuaderno} />
      <DialogoAgregarFuente abierto={nuevaFuente} alCambiar={setNuevaFuente} />
    </div>
  )
}

function ItemNavegacion({ item, actual, cerrada }: { item: Item; actual: boolean; cerrada: boolean }) {
  const enlaceItem = (
    <a
      href={enlace(item.ruta)}
      aria-current={actual ? 'page' : undefined}
      className={cn(
        'relative flex h-10 w-full items-center gap-2.5 rounded-md px-3 text-[13px] font-medium text-tinta-suave transition-colors hover:bg-superficie',
        actual &&
          'bg-elevada font-semibold text-tinta',
        cerrada ? 'justify-center px-2' : 'justify-start',
      )}
    >
      <item.icono className={cn('size-4 shrink-0 opacity-85', item.color)} aria-hidden />
      {cerrada ? <span className="sr-only">{item.nombre}</span> : item.nombre}
    </a>
  )
  return cerrada ? (
    <Ayuda texto={item.nombre} lado="right">
      {enlaceItem}
    </Ayuda>
  ) : (
    enlaceItem
  )
}

/** En pantallas chicas, la navegación va arriba. */
function BarraMovil({ activa }: { activa: string }) {
  return (
    <header className="flex h-12 items-center gap-1 border-b bg-fondo-hondo px-3 md:hidden">
      <a href={enlace({ pagina: 'cuadernos' })} className="mr-auto flex items-center gap-2">
        <Logo className="size-6" />
        <span className="font-display text-lg font-semibold tracking-tight">Tesela</span>
      </a>
      {ITEMS.map((item) => (
        <a
          key={item.nombre}
          href={enlace(item.ruta)}
          aria-current={item.ruta.pagina === activa ? 'page' : undefined}
          className={cn(
            'flex h-8 items-center gap-1.5 rounded-md px-2 text-[13px]',
            item.ruta.pagina === activa ? 'bg-elevada font-medium ring-1 ring-linea ring-inset' : 'text-tinta-suave',
          )}
        >
          <item.icono className={cn('size-4', item.color)} aria-hidden />
          <span className="sr-only sm:not-sr-only">{item.nombre}</span>
        </a>
      ))}
    </header>
  )
}

const NOMBRE_MODO = { buscar: 'Solo buscar', ollama: 'Ollama', openai: 'API' } as const

function EstadoModelo({ compacto }: { compacto: boolean }) {
  const { data: e } = useEstado()
  if (!e) return null
  const detalle =
    e.modo === 'buscar'
      ? 'Sin IA, solo pasajes'
      : e.modo === 'ollama'
        ? !e.ollama
          ? 'Ollama está cerrado'
          : e.faltan.length
            ? `Falta descargar ${e.faltan.join(' y ')}`
            : `${e.modelo}, local`
        : e.listo
          ? `${e.modelo}, por internet`
          : 'Falta completar la API'
  const punto = <span className={cn('size-2 shrink-0 rounded-full', e.listo ? 'bg-acento' : 'bg-aviso')} aria-hidden />
  const contenido = (
    <a
      href={enlace({ pagina: 'ajustes' })}
      className={cn('flex items-center gap-2.5 rounded-md px-3 py-1.5 text-left hover:bg-superficie', compacto && 'justify-center px-0 py-2.5')}
    >
      {punto}
      {compacto ? (
        <span className="sr-only">
          {NOMBRE_MODO[e.modo]}: {detalle}
        </span>
      ) : (
        <span className="min-w-0 leading-tight">
          <span className="block text-xs font-medium">{NOMBRE_MODO[e.modo]}</span>
          <span className="block truncate text-[11px] text-tinta-suave">{detalle}</span>
        </span>
      )}
    </a>
  )
  return compacto ? (
    <Ayuda texto={`${NOMBRE_MODO[e.modo]}: ${detalle}`} lado="right">
      {contenido}
    </Ayuda>
  ) : (
    contenido
  )
}

const TEMAS: { tema: Tema; nombre: string; icono: ElementType }[] = [
  { tema: 'claro', nombre: 'Claro', icono: Sun },
  { tema: 'oscuro', nombre: 'Oscuro', icono: Moon },
  { tema: 'sistema', nombre: 'Como el sistema', icono: Monitor },
]

function SelectorTema({ compacto }: { compacto: boolean }) {
  const [tema, setTema] = useState<Tema>(temaGuardado)
  useEffect(() => {
    aplicarTema(tema)
    if (tema !== 'sistema') return
    const m = matchMedia('(prefers-color-scheme: dark)')
    const cambiar = () => aplicarTema('sistema')
    m.addEventListener('change', cambiar)
    return () => m.removeEventListener('change', cambiar)
  }, [tema])
  const actual = TEMAS.find((t) => t.tema === tema) ?? TEMAS[2]
  const siguiente = TEMAS[(TEMAS.indexOf(actual) + 1) % TEMAS.length]
  return (
    <Ayuda texto={`Tema: ${actual.nombre.toLowerCase()}. Cambiar a ${siguiente.nombre.toLowerCase()}`} lado="right">
      <Boton
        variante="contorno"
        onClick={() => setTema(siguiente.tema)}
        className={cn('w-full justify-start bg-transparent', compacto && 'w-9 justify-center px-0')}
        aria-label={`Tema: ${actual.nombre}. Cambiar a ${siguiente.nombre}`}
      >
        <actual.icono aria-hidden />
        {!compacto && <span>Tema</span>}
      </Boton>
    </Ayuda>
  )
}
