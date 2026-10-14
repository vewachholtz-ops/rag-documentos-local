// Tesela: documentos a la izquierda, consulta central y Estudio (lo que se escribe con las fuentes y las notas) a la
// derecha.
import * as Tabs from '@radix-ui/react-tabs'
import { useMutation } from '@tanstack/react-query'
import { ArrowLeft, FileText, GraduationCap, MessageSquare, Trash2, Upload } from 'lucide-react'
import { type DragEvent, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { ColumnaChat } from '../componentes/Chat'
import { ColumnaEstudio } from '../componentes/Estudio'
import { ColumnaFuentes } from '../componentes/Fuentes'
import { Visor, type Vista } from '../componentes/Visor'
import { api, type Cuaderno } from '../lib/api'
import { CLAVES, useCuaderno, useRefrescar } from '../lib/consultas'
import { pedirAlChat, usePedidosAlChat } from '../lib/eventos'
import { useSubidas } from '../lib/subidas'
import { cn, enlace, haceCuanto, ir, plural, useEsEscritorio } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Confirmar, Girando } from '../ui/piezas'

const CLAVE_COLUMNAS = 'fuente.columnas-plegadas'

function usePlegadas() {
  const [plegadas, setPlegadas] = useState<{ fuentes: boolean; notas: boolean }>(() => {
    try {
      const guardadas = localStorage.getItem(CLAVE_COLUMNAS)
      // sin preferencia guardada, en pantallas medianas las notas parten plegadas para que el chat respire
      if (!guardadas) return { fuentes: false, notas: innerWidth < 1280 }
      return { fuentes: false, notas: false, ...JSON.parse(guardadas) }
    } catch {
      return { fuentes: false, notas: false }
    }
  })
  const cambiar = (cambio: (p: { fuentes: boolean; notas: boolean }) => { fuentes: boolean; notas: boolean }) =>
    setPlegadas((p) => {
      const nuevas = cambio(p)
      try {
        localStorage.setItem(CLAVE_COLUMNAS, JSON.stringify(nuevas))
      } catch {
        /* no importa */
      }
      return nuevas
    })
  return [plegadas, cambiar] as const
}

export function PaginaCuaderno({ id }: { id: string }) {
  const { data: cuaderno, isLoading, isError } = useCuaderno(id)
  const { subidas, agregar, descartar } = useSubidas(id)
  const [vista, setVista] = useState<Vista | null>(null)
  const [plegadas, setPlegadas] = usePlegadas()
  const [pestana, setPestana] = useState('chat')
  const [arrastrando, setArrastrando] = useState(false)
  const profundidad = useRef(0)
  const escritorio = useEsEscritorio()
  usePedidosAlChat(() => setPestana('chat'))

  if (isLoading)
    return (
      <div className="flex flex-1 items-center justify-center">
        <Girando className="size-6" />
      </div>
    )
  if (isError || !cuaderno)
    return (
      <div className="p-6">
        <h1 className="font-display text-2xl font-bold">No encontré ese cuaderno</h1>
        <p className="mt-2 text-tinta-suave">Puede que se haya borrado.</p>
        <a href={enlace({ pagina: 'cuadernos' })} className="mt-4 inline-flex items-center gap-1.5 text-cita hover:underline">
          <ArrowLeft className="size-4" />
          Volver a los cuadernos
        </a>
      </div>
    )

  // arrastrar archivos a cualquier parte del cuaderno los agrega
  const tieneArchivos = (e: DragEvent) => Array.from(e.dataTransfer.types).includes('Files')
  const alEntrar = (e: DragEvent) => {
    if (!tieneArchivos(e)) return
    e.preventDefault()
    profundidad.current += 1
    setArrastrando(true)
  }
  const alSalir = () => {
    profundidad.current = Math.max(0, profundidad.current - 1)
    if (profundidad.current === 0) setArrastrando(false)
  }
  const alSoltar = (e: DragEvent) => {
    if (!tieneArchivos(e)) return
    e.preventDefault()
    profundidad.current = 0
    setArrastrando(false)
    agregar(e.dataTransfer.files)
    setPestana('fuentes')
  }

  const fuentes = (
    <ColumnaFuentes
      cuaderno={cuaderno}
      subidas={subidas}
      alSubir={agregar}
      alDescartar={descartar}
      abrir={setVista}
      plegada={escritorio && plegadas.fuentes}
      alPlegar={escritorio ? (p) => setPlegadas((x) => ({ ...x, fuentes: p })) : undefined}
    />
  )
  const notas = (
    <ColumnaEstudio
      cuaderno={cuaderno}
      plegada={escritorio && plegadas.notas}
      alPlegar={escritorio ? (p) => setPlegadas((x) => ({ ...x, notas: p })) : undefined}
    />
  )
  const chat = <ColumnaChat cuaderno={cuaderno} abrir={setVista} />

  return (
    <div
      className="relative flex min-h-0 flex-1 flex-col"
      onDragEnter={alEntrar}
      onDragOver={(e) => tieneArchivos(e) && e.preventDefault()}
      onDragLeave={alSalir}
      onDrop={alSoltar}
    >
      <Encabezado cuaderno={cuaderno} />

      {escritorio ? (
        <div className="flex min-h-0 flex-1 gap-3 px-4 pb-4">
          <div className={cn('min-h-0 min-w-0 transition-all duration-150', plegadas.fuentes ? 'w-12 shrink-0' : 'w-[248px] shrink-0 xl:w-[264px] 2xl:w-[280px]')}>{fuentes}</div>
          <div className="min-h-0 min-w-0 flex-1 transition-all duration-150">{chat}</div>
          <div className={cn('mesa-notas min-h-0 min-w-0 transition-all duration-150', plegadas.notas ? 'w-12 shrink-0' : 'w-[280px] shrink-0 xl:w-[296px] 2xl:w-[320px]')}>{notas}</div>
        </div>
      ) : (
        <Tabs.Root value={pestana} onValueChange={setPestana} className="flex min-h-0 flex-1 flex-col px-3 pb-3">
          <Tabs.List className="mb-3 grid grid-cols-3 rounded-md bg-hundida p-1" aria-label="Columnas del cuaderno">
            {[
              { valor: 'fuentes', nombre: 'Fuentes', icono: FileText },
              { valor: 'chat', nombre: 'Chat', icono: MessageSquare },
              { valor: 'notas', nombre: 'Estudio', icono: GraduationCap },
            ].map((p) => (
              <Tabs.Trigger
                key={p.valor}
                value={p.valor}
                className="flex h-8 items-center justify-center gap-1.5 rounded-sm text-[13px] text-tinta-suave data-[state=active]:bg-superficie data-[state=active]:font-medium data-[state=active]:text-tinta data-[state=active]:shadow-[0_0_0_1px_var(--linea)]"
              >
                <p.icono className="size-4" aria-hidden />
                {p.nombre}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
          {/* montadas siempre: cambiar de pestaña no corta una pregunta ni una subida en curso */}
          <Tabs.Content forceMount value="fuentes" className="min-h-0 flex-1 data-[state=inactive]:hidden">
            {fuentes}
          </Tabs.Content>
          <Tabs.Content forceMount value="notas" className="min-h-0 flex-1 data-[state=inactive]:hidden">
            {notas}
          </Tabs.Content>
          <Tabs.Content forceMount value="chat" className="min-h-0 flex-1 data-[state=inactive]:hidden">
            {chat}
          </Tabs.Content>
        </Tabs.Root>
      )}

      {arrastrando && (
        <div className="pointer-events-none absolute inset-3 z-30 flex items-center justify-center rounded-lg border-2 border-dashed border-cita bg-cita-tinte/85">
          <p className="flex items-center gap-2 font-display text-lg font-semibold text-cita-hondo">
            <Upload className="size-5" aria-hidden />
            Suelta para agregar a «{cuaderno.nombre}»
          </p>
        </div>
      )}
      <Visor
        vista={vista}
        alCerrar={() => setVista(null)}
        alPreguntar={(texto) => {
          setVista(null)
          pedirAlChat(texto)
        }}
      />
    </div>
  )
}

function Encabezado({ cuaderno: c }: { cuaderno: Cuaderno }) {
  const [borrando, setBorrando] = useState(false)
  const refrescar = useRefrescar()
  const cambiar = useMutation({
    mutationFn: (cambios: { nombre?: string; descripcion?: string }) => api.cambiarCuaderno(c.id, cambios),
    onSuccess: () => refrescar(CLAVES.cuaderno(c.id), CLAVES.cuadernos),
    onError: (e) => toast.error(e.message),
  })
  const borrar = useMutation({
    mutationFn: () => api.borrarCuaderno(c.id),
    onSuccess: () => {
      toast.success(`Borraste «${c.nombre}»`)
      refrescar(CLAVES.cuadernos, CLAVES.estado, CLAVES.documentos)
      ir({ pagina: 'cuadernos' })
    },
    onError: (e) => toast.error(e.message),
  })
  return (
    <header className="shrink-0 px-5 py-4">
      <a href={enlace({ pagina: 'cuadernos' })} className="mb-2 inline-flex items-center gap-1.5 text-xs text-tinta-suave hover:text-cita">
        <ArrowLeft className="size-3.5" aria-hidden /> Cuadernos
      </a>
      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <EdicionEnLinea
              valor={c.nombre}
              alGuardar={(nombre) => nombre.trim() && nombre !== c.nombre && cambiar.mutate({ nombre })}
              etiqueta="Nombre del cuaderno"
              className="font-display text-xl font-semibold tracking-tight lg:text-2xl"
            />
          </div>
          <Boton variante="fantasma" tamano="sm" aria-label="Borrar cuaderno" className="hover:text-peligro" onClick={() => setBorrando(true)}>
            <Trash2 />
            <span className="hidden sm:inline">Borrar</span>
          </Boton>
        </div>
        <EdicionEnLinea
          valor={c.descripcion}
          alGuardar={(descripcion) => descripcion !== c.descripcion && cambiar.mutate({ descripcion })}
          etiqueta="Descripción del cuaderno"
          vacio="Agregar una descripción…"
          className="text-tinta-suave max-lg:text-sm max-lg:[&>span]:line-clamp-1"
        />
        <p className="hidden text-xs text-tinta-tenue sm:block">
          {plural(c.documentos.length, 'fuente', 'fuentes')} · {plural(c.notas.length, 'nota', 'notas')} · Modificado{' '}
          {haceCuanto(c.actualizado)}
        </p>
      </div>
      <Confirmar
        abierto={borrando}
        alCambiar={setBorrando}
        titulo={`¿Borrar «${c.nombre}»?`}
        descripcion="Se borran sus notas y la conversación. Los documentos quedan en la biblioteca."
        accion="Borrar cuaderno"
        ocupado={borrar.isPending}
        alConfirmar={() => borrar.mutate()}
      />
    </header>
  )
}

/** Un texto que se edita al tocarlo. Enter guarda, Escape cancela. */
function EdicionEnLinea({
  valor,
  alGuardar,
  etiqueta,
  vacio,
  className,
}: {
  valor: string
  alGuardar: (v: string) => void
  etiqueta: string
  vacio?: string
  className?: string
}) {
  const [editando, setEditando] = useState(false)
  const [texto, setTexto] = useState(valor)
  useEffect(() => setTexto(valor), [valor])
  if (editando)
    return (
      <input
        autoFocus
        value={texto}
        aria-label={etiqueta}
        onChange={(e) => setTexto(e.target.value)}
        onBlur={() => {
          setEditando(false)
          alGuardar(texto.trim())
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
          if (e.key === 'Escape') {
            setTexto(valor)
            setEditando(false)
          }
        }}
        className={cn('-mx-1.5 block w-full rounded-md border border-cita bg-elevada px-1.5 focus:outline-none', className)}
      />
    )
  return (
    <button
      onClick={() => setEditando(true)}
      className={cn('-mx-1.5 block max-w-full rounded-md px-1.5 text-left hover:bg-hundida', className, !valor && 'text-tinta-tenue')}
      aria-label={`${etiqueta}: ${valor || 'vacío'}. Editar`}
    >
      <span className="line-clamp-2 break-words">{valor || vacio}</span>
    </button>
  )
}
