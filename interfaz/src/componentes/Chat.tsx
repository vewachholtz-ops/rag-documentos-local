import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Bot,
  Check,
  ChevronDown,
  CircleAlert,
  Copy,
  Download,
  FileText,
  History,
  Info,
  MessageSquare,
  MessageSquarePlus,
  Pencil,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  StickyNote,
  Trash2,
  User,
} from 'lucide-react'
import { type FormEvent, type KeyboardEvent, type MouseEvent, type ReactNode, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  api,
  type Cuaderno,
  type Estado,
  type FuenteRespuesta,
  type Largo,
  type Modo,
  type Pasaje,
  type Respuesta,
  type Vuelta,
} from '../lib/api'
import { CLAVES, useAjustes, useConversacion, useEstado, useRefrescar } from '../lib/consultas'
import { descargar, useDescargas } from '../lib/descargas'
import { usePedidosAlChat } from '../lib/eventos'
import { cn, haceCuanto, ir, plural } from '../lib/utiles'
import { Boton } from '../ui/boton'
import {
  Ayuda,
  Barra,
  Campo,
  Confirmar,
  Dialogo,
  Etiqueta,
  Girando,
  MenuContenido,
  MenuDisparador,
  MenuItem,
  MenuRaiz,
  MenuSeparador,
  Texto,
} from '../ui/piezas'
import { Columna } from './Columna'
import { textoEnChat } from './Fuentes'
import type { AbrirVisor } from './Visor'
import { BotonPreguntar } from './VistasEstudio'
import { ES_WEB } from '../web/config'

interface Pendiente {
  pregunta: string
  pasos: string[]
  error?: string
}

const claveActiva = (cuaderno: string) => `mesa.conversacion.${cuaderno}`

/** La conversación abierta (null: una nueva, que se crea con la primera pregunta). Se recuerda por cuaderno. */
function useActiva(cuaderno: Cuaderno) {
  const [activa, setActiva] = useState<string | null>(() => {
    try {
      const guardada = localStorage.getItem(claveActiva(cuaderno.id))
      if (guardada === 'nueva') return null
      if (guardada && cuaderno.conversaciones.some((c) => c.id === guardada)) return guardada
    } catch {
      /* sin almacenamiento: la más reciente */
    }
    return cuaderno.conversaciones[0]?.id ?? null
  })
  const cambiar = (id: string | null) => {
    setActiva(id)
    try {
      localStorage.setItem(claveActiva(cuaderno.id), id ?? 'nueva')
    } catch {
      /* no importa */
    }
  }
  // si la borraron, la más reciente que quede
  const existe = activa === null || cuaderno.conversaciones.some((c) => c.id === activa)
  return [existe ? activa : (cuaderno.conversaciones[0]?.id ?? null), cambiar] as const
}

export function ColumnaChat({ cuaderno, abrir }: { cuaderno: Cuaderno; abrir: AbrirVisor }) {
  const { data: estado } = useEstado()
  const [activa, setActiva] = useActiva(cuaderno)
  const { data: conversacion, isLoading: cargando } = useConversacion(cuaderno.id, activa)
  const [pendiente, setPendiente] = useState<Pendiente | null>(null)
  const [semilla, setSemilla] = useState<{ texto: string; n: number }>({ texto: '', n: 0 })
  const [estilo, setEstilo] = useState(false)
  const refrescar = useRefrescar()
  const cliente = useQueryClient()
  const lista = useRef<HTMLDivElement>(null)
  const fuera = new Set(cuaderno.fuera)
  const enChat = cuaderno.documentos.filter((d) => !fuera.has(d.id)).length
  const trozos = cuaderno.documentos.filter((d) => !fuera.has(d.id)).reduce((n, d) => n + d.trozos, 0)
  const vueltas = activa ? (conversacion?.vueltas ?? []) : []

  // mientras responde, se sigue el final; al llegar la respuesta, se muestra desde su pregunta
  useLayoutEffect(() => {
    lista.current?.scrollTo({ top: lista.current.scrollHeight })
  }, [pendiente?.pasos.length, pendiente?.error])
  const cuantas = useRef(vueltas.length)
  useLayoutEffect(() => {
    const antes = cuantas.current
    cuantas.current = vueltas.length
    const caja = lista.current
    if (!caja) return
    const ultima = Array.from(caja.querySelectorAll<HTMLElement>('[data-vuelta]')).at(-1)
    if (vueltas.length === antes + 1 && ultima && ultima.offsetHeight > caja.clientHeight) caja.scrollTo({ top: ultima.offsetTop - 12 })
    else caja.scrollTo({ top: caja.scrollHeight })
  }, [vueltas.length, activa])

  const ocupado = pendiente !== null && !pendiente.error
  const preguntar = async (pregunta: string) => {
    setPendiente({ pregunta, pasos: [] })
    try {
      const final = await api.preguntar(cuaderno.id, pregunta, activa, (e) => {
        if (e.tipo === 'paso') setPendiente((p) => (p ? { ...p, pasos: [...p.pasos, e.texto] } : p))
      })
      if (final.tipo === 'error') throw new Error(final.texto)
      if (final.tipo === 'vuelta') {
        // se trae la conversación antes de mostrarla: así no parpadea entre la pregunta pendiente y la guardada
        await cliente.fetchQuery({
          queryKey: CLAVES.conversacion(cuaderno.id, final.conversacion),
          queryFn: () => api.conversacion(cuaderno.id, final.conversacion),
          staleTime: 0,
        })
        await refrescar(CLAVES.cuaderno(cuaderno.id), CLAVES.cuadernos)
        setActiva(final.conversacion)
      }
      setPendiente(null)
    } catch (error) {
      setPendiente((p) => (p ? { ...p, error: (error as Error).message } : p))
      return false
    }
    return true
  }

  // un tema del mapa de ideas o una pregunta de la guía: se pregunta al tiro si se puede; si no, queda escrita
  usePedidosAlChat((texto) => {
    if (!ocupado && enChat > 0 && estado?.listo) void preguntar(texto)
    else setSemilla((s) => ({ texto, n: s.n + 1 }))
  })

  return (
    <Columna
      titulo="Chat"
      color="bg-cita"
      icono={MessageSquare}
      sinRelleno
      acciones={
        <>
          <SelectorConversacion cuaderno={cuaderno} activa={activa} alElegir={setActiva} deshabilitado={ocupado} />
          <Ayuda texto="Configurar el chat">
            <Boton variante="fantasma" tamano="icono-sm" className="text-tinta-suave" onClick={() => setEstilo(true)} aria-label="Configurar el chat">
              <Settings2 />
            </Boton>
          </Ayuda>
          <Ayuda texto="Nueva conversación">
            <Boton
              variante="fantasma"
              tamano="icono-sm"
              className="text-tinta-suave"
              onClick={() => setActiva(null)}
              disabled={ocupado || activa === null}
              aria-label="Nueva conversación"
            >
              <MessageSquarePlus />
            </Boton>
          </Ayuda>
        </>
      }
      pie={
        <>
          {estado && !estado.listo && <AvisoModelo estado={estado} />}
          <Contexto enChat={enChat} total={cuaderno.documentos.length} trozos={trozos} />
          <Redactor ocupado={ocupado} sinFuentes={enChat === 0} alEnviar={preguntar} estado={estado} semilla={semilla} />
        </>
      }
    >
      <div ref={lista} className="relative min-h-0 flex-1 overflow-y-auto px-4" aria-live="polite">
        <div className="mx-auto max-w-3xl space-y-4 py-4">
          {activa && cargando ? (
            <div className="flex justify-center py-10">
              <Girando className="size-5" />
            </div>
          ) : (
            vueltas.length === 0 &&
            !pendiente && (
              <Bienvenida
                sinFuentes={cuaderno.documentos.length === 0}
                apagadas={cuaderno.documentos.length > 0 && enChat === 0}
                sugerencias={estado?.listo && estado.modo !== 'buscar' ? cuaderno.sugerencias : []}
                alPreguntar={(texto) => void preguntar(texto)}
              />
            )
          )}
          {vueltas.map((v) => (
            <VueltaChat key={v.id} vuelta={v} cuaderno={cuaderno.id} abrir={abrir} />
          ))}
          {pendiente && (
            <div className="space-y-3">
              <BurbujaPregunta texto={pendiente.pregunta} />
              {pendiente.error ? (
                <div className="flex items-start gap-3" role="alert">
                  <Avatar modo="error" />
                  <div className="rounded-lg border border-peligro/30 bg-peligro-tinte px-4 py-3 text-sm">
                    <p>{pendiente.error}</p>
                    <div className="mt-2.5 flex gap-2">
                      <Boton tamano="sm" variante="contorno" onClick={() => preguntar(pendiente.pregunta)}>
                        Reintentar
                      </Boton>
                      <Boton tamano="sm" variante="fantasma" onClick={() => setPendiente(null)}>
                        Descartar
                      </Boton>
                    </div>
                  </div>
                </div>
              ) : (
                <Pasos pasos={pendiente.pasos} />
              )}
            </div>
          )}
        </div>
      </div>
      <DialogoEstilo abierto={estilo} alCambiar={setEstilo} cuaderno={cuaderno} soloBuscar={estado?.modo === 'buscar'} />
    </Columna>
  )
}

function Bienvenida({
  sinFuentes,
  apagadas,
  sugerencias,
  alPreguntar,
}: {
  sinFuentes: boolean
  apagadas: boolean
  sugerencias: string[]
  alPreguntar: (texto: string) => void
}) {
  return (
    <div className="mx-auto max-w-md px-4 py-10 text-center text-tinta-suave">
      <span className="mx-auto mb-5 flex size-12 items-center justify-center rounded-lg bg-cita-tinte text-cita"><MessageSquare className="size-6" aria-hidden /></span>
      <p className="text-base font-medium text-tinta">
        {sinFuentes ? 'Primero, agrega una fuente' : apagadas ? 'Todas las fuentes están fuera del chat' : 'Empieza una conversación sobre este cuaderno'}
      </p>
      <p className="mt-2 text-[13px] leading-relaxed">
        {sinFuentes
          ? 'Sube un PDF, un Word o un texto, o pega un enlace, en la columna Fuentes.'
          : apagadas
            ? 'Incluye al menos una con el ojo de su tarjeta.'
            : 'Pregunta para entender mejor tus fuentes; cada respuesta cita el pasaje exacto.'}
      </p>
      {!sinFuentes && !apagadas && sugerencias.length > 0 && (
        <div className="mt-6 space-y-1.5 text-left">
          <p className="text-xs font-medium">Para empezar</p>
          {sugerencias.map((s) => (
            <BotonPreguntar key={s} texto={s} alPreguntar={alPreguntar} />
          ))}
        </div>
      )}
    </div>
  )
}

function SelectorConversacion({
  cuaderno,
  activa,
  alElegir,
  deshabilitado,
}: {
  cuaderno: Cuaderno
  activa: string | null
  alElegir: (id: string | null) => void
  deshabilitado: boolean
}) {
  const [renombrando, setRenombrando] = useState(false)
  const [borrando, setBorrando] = useState(false)
  const [titulo, setTitulo] = useState('')
  const refrescar = useRefrescar()
  const actual = cuaderno.conversaciones.find((c) => c.id === activa)
  const renombrar = useMutation({
    mutationFn: () => api.renombrarConversacion(cuaderno.id, activa!, titulo),
    onSuccess: () => {
      setRenombrando(false)
      refrescar(CLAVES.cuaderno(cuaderno.id))
    },
    onError: (e) => toast.error(e.message),
  })
  const borrar = useMutation({
    mutationFn: () => api.borrarConversacion(cuaderno.id, activa!),
    onSuccess: async () => {
      setBorrando(false)
      await refrescar(CLAVES.cuaderno(cuaderno.id))
      alElegir(cuaderno.conversaciones.find((c) => c.id !== activa)?.id ?? null)
    },
    onError: (e) => toast.error(e.message),
  })
  if (!cuaderno.conversaciones.length) return null
  return (
    <>
      <MenuRaiz>
        <MenuDisparador asChild>
          <Boton variante="fantasma" tamano="sm" className="max-w-56 text-tinta-suave" disabled={deshabilitado} aria-label={`Conversación: ${actual?.titulo ?? 'nueva'}. Cambiar`}>
            <History />
            <span className="truncate">{actual?.titulo ?? 'Nueva conversación'}</span>
            <ChevronDown className="opacity-60" />
          </Boton>
        </MenuDisparador>
        <MenuContenido className="w-80">
          <MenuItem icono={MessageSquarePlus} onSelect={() => alElegir(null)} disabled={activa === null}>
            Nueva conversación
          </MenuItem>
          <MenuSeparador />
          <div className="max-h-72 overflow-y-auto" role="group" aria-label="Conversaciones">
            {cuaderno.conversaciones.map((c) => (
              <MenuItem key={c.id} onSelect={() => alElegir(c.id)} className="items-start py-2">
                <Check className={cn('mt-0.5', c.id === activa ? 'opacity-100' : 'opacity-0')} aria-hidden />
                <span className="min-w-0">
                  <span className="block truncate font-medium">{c.titulo}</span>
                  <span className="block text-xs text-tinta-suave">
                    {plural(c.preguntas, 'pregunta', 'preguntas')}, {haceCuanto(c.actualizado)}
                  </span>
                </span>
              </MenuItem>
            ))}
          </div>
          {actual && (
            <>
              <MenuSeparador />
              <MenuItem
                icono={Pencil}
                onSelect={() => {
                  setTitulo(actual.titulo)
                  setRenombrando(true)
                }}
              >
                Cambiar el nombre
              </MenuItem>
              <MenuItem icono={Trash2} peligro onSelect={() => setBorrando(true)}>
                Borrar esta conversación
              </MenuItem>
            </>
          )}
        </MenuContenido>
      </MenuRaiz>
      <Dialogo abierto={renombrando} alCambiar={setRenombrando} titulo="Nombre de la conversación">
        <form
          className="space-y-4 p-5"
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            if (titulo.trim()) renombrar.mutate()
          }}
        >
          <div>
            <Etiqueta htmlFor="titulo-conversacion">Nombre</Etiqueta>
            <Campo id="titulo-conversacion" value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={80} autoFocus />
          </div>
          <div className="flex justify-end gap-2">
            <Boton variante="contorno" onClick={() => setRenombrando(false)}>
              Cancelar
            </Boton>
            <Boton type="submit" variante="principal" disabled={!titulo.trim() || renombrar.isPending}>
              Guardar
            </Boton>
          </div>
        </form>
      </Dialogo>
      <Confirmar
        abierto={borrando}
        alCambiar={setBorrando}
        titulo="¿Borrar esta conversación?"
        descripcion={`«${actual?.titulo ?? ''}» se borra. Las notas que guardaste de ella quedan.`}
        accion="Borrar conversación"
        ocupado={borrar.isPending}
        alConfirmar={() => borrar.mutate()}
      />
    </>
  )
}

const LARGOS: { valor: Largo; titulo: string; texto: string }[] = [
  { valor: 'corto', titulo: 'Cortas', texto: 'Una o dos oraciones.' },
  { valor: 'normal', titulo: 'Normales', texto: 'Un párrafo o una lista corta.' },
  { valor: 'largo', titulo: 'Detalladas', texto: 'Varios párrafos; lee más pasajes antes de responder.' },
]

function DialogoEstilo({
  abierto,
  alCambiar,
  cuaderno,
  soloBuscar,
}: {
  abierto: boolean
  alCambiar: (a: boolean) => void
  cuaderno: Cuaderno
  soloBuscar: boolean
}) {
  const [largo, setLargo] = useState<Largo>(cuaderno.estilo.largo)
  const [instrucciones, setInstrucciones] = useState(cuaderno.estilo.instrucciones)
  const refrescar = useRefrescar()
  useEffect(() => {
    if (!abierto) return
    setLargo(cuaderno.estilo.largo)
    setInstrucciones(cuaderno.estilo.instrucciones)
  }, [abierto, cuaderno.estilo])
  const guardar = useMutation({
    mutationFn: () => api.cambiarCuaderno(cuaderno.id, { estilo: { largo, instrucciones } }),
    onSuccess: () => {
      alCambiar(false)
      toast.success('Listo: así responde el chat de este cuaderno')
      refrescar(CLAVES.cuaderno(cuaderno.id))
    },
    onError: (e) => toast.error(e.message),
  })
  return (
    <Dialogo abierto={abierto} alCambiar={alCambiar} titulo="Configurar el chat" descripcion={`Cómo responde el modelo en «${cuaderno.nombre}».`}>
      <form
        className="space-y-5 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          guardar.mutate()
        }}
      >
        <fieldset className="space-y-2">
          <legend className="mb-1.5 text-[13px] font-medium">Largo de las respuestas</legend>
          {LARGOS.map((o) => (
            <label
              key={o.valor}
              className={cn(
                'flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5 transition-colors',
                largo === o.valor ? 'border-acento bg-acento-tinte/50 shadow-[0_0_0_1px_var(--acento)]' : 'bg-superficie hover:bg-hundida/50',
              )}
            >
              <input type="radio" name="largo" value={o.valor} checked={largo === o.valor} onChange={() => setLargo(o.valor)} className="mt-1 accent-[var(--acento)]" />
              <span>
                <span className="block text-[13.5px] font-medium">{o.titulo}</span>
                <span className="block text-xs text-tinta-suave">{o.texto}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <div>
          <Etiqueta htmlFor="instrucciones-chat">Indicaciones para este cuaderno (opcional)</Etiqueta>
          <Texto
            id="instrucciones-chat"
            value={instrucciones}
            onChange={(e) => setInstrucciones(e.target.value)}
            rows={3}
            maxLength={600}
            placeholder="Por ejemplo: explícalo como a alguien que recién llega a la faena, con ejemplos."
          />
          <p className="mt-1.5 text-xs text-tinta-suave">
            Las reglas de las citas no cambian: cada dato sigue citando el pasaje que lo respalda.
            {soloBuscar && ' En el modo solo buscar no se usan: ahí no responde un modelo.'}
          </p>
        </div>
        <div className="flex justify-end gap-2">
          <Boton variante="contorno" onClick={() => alCambiar(false)}>
            Cancelar
          </Boton>
          <Boton type="submit" variante="principal" disabled={guardar.isPending}>
            Guardar
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}

function BurbujaPregunta({ texto }: { texto: string }) {
  return (
    <div className="flex justify-end gap-3">
      <p className="max-w-[80%] rounded-lg border bg-hundida px-4 py-2 text-sm break-words whitespace-pre-wrap">{texto}</p>
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full border bg-hundida">
        <User className="size-4 text-tinta-suave" aria-hidden />
      </div>
    </div>
  )
}

function Avatar({ modo }: { modo: Modo | 'error' }) {
  const Icono = modo === 'buscar' ? Search : modo === 'error' ? CircleAlert : Bot
  return (
    <div className={cn('flex size-8 shrink-0 items-center justify-center rounded-full', modo === 'error' ? 'bg-peligro-tinte' : 'bg-cita-tinte')}>
      <Icono className={cn('size-4', modo === 'error' ? 'text-peligro' : 'text-cita')} aria-hidden />
    </div>
  )
}

function Pasos({ pasos }: { pasos: string[] }) {
  const lista = pasos.length ? pasos : ['Empezando']
  return (
    <div className="flex items-start gap-3" role="status">
      <Avatar modo="ollama" />
      <ol className="space-y-1.5 rounded-lg border bg-superficie px-4 py-2.5 text-[13px]">
        {lista.map((p, i) => {
          const actual = i === lista.length - 1
          return (
            <li key={`${i}-${p}`} className={cn('flex items-center gap-2', actual ? 'text-tinta' : 'text-tinta-tenue')}>
              {actual ? <Girando className="text-cita" /> : <Check className="size-4 text-acento" aria-hidden />}
              {p}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function VueltaChat({ vuelta: v, cuaderno, abrir }: { vuelta: Vuelta; cuaderno: string; abrir: AbrirVisor }) {
  return (
    <div className="space-y-3" data-vuelta>
      <BurbujaPregunta texto={v.pregunta} />
      <div className="flex items-start gap-3">
        <Avatar modo={v.modo} />
        <div className="min-w-0 max-w-[88%] flex-1">
          {v.respuesta && <BloqueRespuesta vuelta={v} respuesta={v.respuesta} cuaderno={cuaderno} abrir={abrir} />}
          {v.pasajes && <BloquePasajes pasajes={v.pasajes.pasajes} busqueda={v.pasajes.busqueda} abrir={abrir} />}
        </div>
      </div>
    </div>
  )
}

function vistaDe(f: FuenteRespuesta | Pasaje) {
  return { doc_id: f.doc_id, documento: f.documento, tipo: f.tipo, pagina: f.pagina, seccion: f.seccion, pasaje: f.html, n: f.n }
}

function lugar(f: { pagina?: number | null; seccion: string; documento: string }) {
  return f.pagina ? `página ${f.pagina}` : f.seccion !== f.documento ? f.seccion : ''
}

function textoParaCopiar(r: Respuesta) {
  const citadas = r.fuentes.filter((f) => f.citada)
  const fuentes = citadas.map((f) => `[${f.n}] ${f.documento}${lugar(f) ? `, ${lugar(f)}` : ''}`)
  return fuentes.length ? `${r.texto.trim()}\n\nFuentes:\n${fuentes.join('\n')}` : r.texto.trim()
}

function BloqueRespuesta({ vuelta, respuesta: r, cuaderno, abrir }: { vuelta: Vuelta; respuesta: Respuesta; cuaderno: string; abrir: AbrirVisor }) {
  const [copiado, setCopiado] = useState(false)
  const refrescar = useRefrescar()
  const citadas = r.fuentes.filter((f) => f.citada)
  const otras = r.fuentes.filter((f) => !f.citada)
  const guardar = useMutation({
    mutationFn: () => api.crearNota(cuaderno, { titulo: vuelta.pregunta.slice(0, 200), contenido: textoParaCopiar(r), origen: 'respuesta' }),
    onSuccess: () => {
      toast.success('Guardada en Notas')
      refrescar(CLAVES.cuaderno(cuaderno), CLAVES.cuadernos)
    },
    onError: (e) => toast.error(e.message),
  })
  const alTocar = (e: MouseEvent<HTMLDivElement>) => {
    const boton = (e.target as HTMLElement).closest<HTMLButtonElement>('button.cita')
    const f = boton && r.fuentes.find((x) => x.n === Number(boton.dataset.n))
    if (f) abrir(vistaDe(f))
  }
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(textoParaCopiar(r))
      setCopiado(true)
      setTimeout(() => setCopiado(false), 1600)
    } catch {
      toast.error('No pude copiar al portapapeles.')
    }
  }
  const Icono = r.estado.tipo === 'alerta' ? CircleAlert : r.estado.tipo === 'neutro' ? Info : ShieldCheck
  return (
    <div className="space-y-2">
      {r.consulta && <p className="text-xs text-tinta-suave">Entendí: «{r.consulta}»</p>}
      {/* el HTML viene escapado del servidor; solo trae párrafos y los botones de cita */}
      <div
        className="prosa rounded-lg border bg-superficie px-4 py-2.5 text-sm leading-relaxed"
        onClick={alTocar}
        dangerouslySetInnerHTML={{ __html: r.html }}
      />

      {citadas.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Fuentes citadas">
          {citadas.map((f) => (
            <li key={f.n}>
              <ChipFuente fuente={f} alAbrir={() => abrir(vistaDe(f))} />
            </li>
          ))}
        </ul>
      )}

      <details className="group rounded-md border bg-superficie text-[13px] open:bg-elevada">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 [&::-webkit-details-marker]:hidden">
          <Icono className={cn('size-4 shrink-0', r.estado.tipo === 'alerta' ? 'text-aviso' : r.estado.tipo === 'literal' ? 'text-acento' : 'text-tinta-suave')} aria-hidden />
          <span className="flex-1">{r.estado.texto}</span>
          <ChevronDown className="size-4 text-tinta-tenue transition-transform group-open:rotate-180" aria-hidden />
        </summary>
        <div className="space-y-2 border-t px-3 py-2.5 text-tinta-suave">
          {r.estado.detalle && <p>{r.estado.detalle}</p>}
          {otras.length > 0 && (
            <div>
              <p className="mb-1.5">También leyó, sin citarlos:</p>
              <ul className="flex flex-wrap gap-1.5">
                {otras.map((f) => (
                  <li key={f.n}>
                    <ChipFuente fuente={f} alAbrir={() => abrir(vistaDe(f))} tenue />
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-xs text-tinta-tenue">
            {vuelta.modelo}
            {vuelta.modo === 'openai' ? ', por API' : ES_WEB ? ', en este navegador' : ', en este computador'}, {r.segundos} s
          </p>
        </div>
      </details>

      <div className="-ml-2 flex gap-1">
        <Boton variante="fantasma" tamano="sm" onClick={copiar}>
          {copiado ? <Check /> : <Copy />}
          {copiado ? 'Copiado' : 'Copiar'}
        </Boton>
        <Boton variante="fantasma" tamano="sm" onClick={() => guardar.mutate()} disabled={guardar.isPending || guardar.isSuccess}>
          <StickyNote />
          {guardar.isSuccess ? 'Guardada' : 'Guardar como nota'}
        </Boton>
      </div>
    </div>
  )
}

function ChipFuente({ fuente: f, alAbrir, tenue }: { fuente: FuenteRespuesta | Pasaje; alAbrir: () => void; tenue?: boolean }) {
  const donde = lugar(f)
  return (
    <button
      onClick={alAbrir}
      className={cn(
        'flex max-w-72 items-center gap-1.5 rounded-md border px-2 py-1 text-left text-xs transition-colors hover:border-cita/50 hover:bg-cita-tinte',
        tenue ? 'bg-superficie text-tinta-suave' : 'bg-elevada',
      )}
    >
      <span className="inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-sm bg-cita-tinte px-1 text-[10.5px] font-semibold text-cita-hondo">
        {f.n}
      </span>
      <span className="truncate">
        {f.documento}
        {donde && <span className="text-tinta-suave">, {donde}</span>}
      </span>
    </button>
  )
}

function BloquePasajes({ pasajes, busqueda, abrir }: { pasajes: Pasaje[]; busqueda: string; abrir: AbrirVisor }) {
  if (!pasajes.length) return <p className="pt-1 text-[14px] text-tinta-suave">Ningún pasaje tiene esas palabras.</p>
  return (
    <div className="space-y-2.5">
      <p className="pt-1 text-[13px] text-tinta-suave">
        {plural(pasajes.length, 'pasaje', 'pasajes')} que más calzan, buscados {busqueda}:
      </p>
      <ol className="space-y-2">
        {pasajes.map((p) => (
          <li key={p.n}>
            <button onClick={() => abrir(vistaDe(p))} className="block w-full rounded-md border bg-elevada p-3 text-left transition-colors hover:border-cita/50">
              <span className="flex items-center gap-2 text-xs text-tinta-suave">
                <span className="inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-sm bg-cita-tinte px-1 text-[10.5px] font-semibold text-cita-hondo">
                  {p.n}
                </span>
                <span className="truncate font-medium text-tinta">{p.documento}</span>
                {lugar(p) && <span className="truncate">{lugar(p)}</span>}
              </span>
              <span
                className="prosa mt-2 block max-h-32 overflow-hidden text-[13.5px] leading-relaxed [mask-image:linear-gradient(to_bottom,black_70%,transparent)]"
                dangerouslySetInnerHTML={{ __html: p.html }}
              />
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}

// ---- lo que falta para preguntar con IA ----
function AvisoModelo({ estado: e }: { estado: Estado }) {
  const descargas = useDescargas()
  const refrescar = useRefrescar()
  const usarBuscar = useMutation({
    mutationFn: () => api.cambiarAjustes({ modo: 'buscar' }),
    onSuccess: () => refrescar(CLAVES.estado, CLAVES.ajustes),
  })
  let titulo: string
  let cuerpo: ReactNode
  if (e.modo === 'openai') {
    titulo = 'Falta configurar la API'
    cuerpo = (
      <Boton tamano="sm" variante="contorno" onClick={() => ir({ pagina: 'ajustes' })}>
        Ir a Modelos
      </Boton>
    )
  } else if (!e.ollama) {
    titulo = 'Ollama está cerrado'
    cuerpo = (
      <>
        <p>Ábrelo para que responda la IA. Mientras, puedes buscar pasajes sin IA.</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Boton tamano="sm" variante="contorno" onClick={() => usarBuscar.mutate()}>
            <Search />
            Usar solo buscar
          </Boton>
          <a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[13px] font-medium text-cita hover:bg-hundida">
            Descargar Ollama
          </a>
        </div>
      </>
    )
  } else {
    titulo = `Falta descargar ${e.faltan.join(' y ')}`
    cuerpo = (
      <div className="space-y-2">
        {e.faltan.map((m) => {
          const d = descargas[m]
          return (
            <div key={m}>
              {d && !d.error ? (
                <div className="space-y-1">
                  <p className="text-xs">
                    {m}: {d.total ? `${Math.round((d.hecho / d.total) * 100)} %` : d.estado || 'empezando'}
                  </p>
                  <Barra valor={d.total ? d.hecho / d.total : 0} />
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <Boton tamano="sm" variante="principal" onClick={() => descargar(m, () => refrescar(CLAVES.estado))}>
                    <Download />
                    Descargar {m}
                  </Boton>
                  {m.startsWith('gpt-oss') && <span className="text-xs">unos 13 GB, una sola vez</span>}
                  {d?.error && <span className="text-xs text-peligro">{d.error}</span>}
                </div>
              )}
            </div>
          )
        })}
      </div>
    )
  }
  return (
    <div className="mx-3 mb-1 rounded-md border border-aviso/30 bg-aviso-tinte px-3 py-2.5 text-[13px]" role="status">
      <p className="mb-1.5 font-medium">{titulo}</p>
      {cuerpo}
    </div>
  )
}

// ---- la caja para preguntar ----
const NOMBRE_MODO: Record<Modo, string> = { buscar: 'Solo buscar', ollama: 'Ollama', openai: 'API' }

/** Alcance visible de la consulta actual. */
function Contexto({ enChat, total, trozos }: { enChat: number; total: number; trozos: number }) {
  if (total === 0) return null
  if (enChat === 0)
    return (
      <div className="shrink-0 border-t px-3 py-2 text-xs text-tinta-suave">
        Ninguna fuente entra al chat. Incluye alguna con el ojo de su tarjeta.
      </div>
    )
  return (
    <div className="flex shrink-0 items-center justify-between gap-2 border-t bg-hundida/30 px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-tinta-suave">Consultando</span>
        <Ayuda texto={textoEnChat(enChat, total)}>
          <span className="flex cursor-default items-center gap-1 rounded-md border border-acento/50 px-1.5 py-0.5 text-xs text-acento">
            <FileText className="size-3" aria-hidden />
            <span>{plural(enChat, 'fuente', 'fuentes')}</span>
            <span className="sr-only">{textoEnChat(enChat, total)}</span>
          </span>
        </Ayuda>
      </div>
      <span className="text-xs text-tinta-suave">{plural(trozos, 'pasaje', 'pasajes')}</span>
    </div>
  )
}

function Redactor({
  ocupado,
  sinFuentes,
  alEnviar,
  estado,
  semilla,
}: {
  ocupado: boolean
  sinFuentes: boolean
  alEnviar: (pregunta: string) => Promise<boolean>
  estado?: Estado
  /** Un texto que llega de otra parte (el mapa de ideas, la guía) cuando no se puede preguntar al tiro. */
  semilla: { texto: string; n: number }
}) {
  const [texto, setTexto] = useState('')
  const caja = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    if (!semilla.n) return
    setTexto(semilla.texto)
    caja.current?.focus()
  }, [semilla])
  const puede = !ocupado && !sinFuentes && !!texto.trim() && (!estado || estado.listo)
  useEffect(() => {
    const t = caja.current
    if (!t) return
    t.style.height = 'auto'
    t.style.height = `${Math.min(Math.max(t.scrollHeight, 40), 100)}px`
  }, [texto])
  const enviar = async () => {
    if (!puede) return
    const pregunta = texto.trim()
    setTexto('')
    const bien = await alEnviar(pregunta)
    if (!bien) setTexto((t) => t || pregunta)
  }
  const alTeclear = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void enviar()
    }
  }
  const marcador = sinFuentes
    ? 'Agrega una fuente para preguntar'
    : estado?.modo === 'buscar'
      ? 'Escribe qué buscar en tus fuentes (Enter para enviar)'
      : 'Pregunta lo que quieras sobre tus fuentes (Enter para enviar)'
  return (
    <div className="shrink-0 space-y-2 border-t p-3 lg:space-y-3 lg:p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-tinta-suave">{estado?.modo === 'buscar' ? 'Modo' : 'Modelo'}</span>
        <SelectorModo estado={estado} />
      </div>
      <div className="flex min-w-0 items-end gap-2">
        <textarea
          ref={caja}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={alTeclear}
          placeholder={marcador}
          aria-label="Pregunta"
          rows={1}
          maxLength={1000}
          disabled={sinFuentes}
          className="max-h-[100px] min-h-[40px] min-w-0 flex-1 resize-none rounded-md border bg-superficie px-3 py-2 text-sm placeholder:text-tinta-tenue focus-visible:border-cita focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60"
        />
        <Boton
          variante="principal"
          className="size-10 shrink-0 justify-center p-0"
          disabled={!puede}
          onClick={() => void enviar()}
          aria-label={estado?.modo === 'buscar' ? 'Buscar' : 'Preguntar'}
        >
          {ocupado ? <Girando className="text-sobre-primario" /> : <Send />}
        </Boton>
      </div>
    </div>
  )
}

function SelectorModo({ estado }: { estado?: Estado }) {
  const { data: ajustes } = useAjustes()
  const refrescar = useRefrescar()
  const cambiar = useMutation({
    mutationFn: (modo: Modo) => api.cambiarAjustes({ modo }),
    onSuccess: () => refrescar(CLAVES.estado, CLAVES.ajustes),
    onError: (e) => toast.error(e.message),
  })
  if (!estado || !ajustes) return null
  const detalle: Record<Modo, string> = {
    buscar: 'Muestra los pasajes que calzan. Sin IA.',
    ollama: `${ajustes.modelo}, en este computador`,
    openai: ajustes.openai.modelo ? `${ajustes.openai.modelo}${ajustes.openai.local ? '' : ', por internet'}` : 'Sin configurar',
  }
  return (
    <MenuRaiz>
      <MenuDisparador asChild>
        <Boton variante="contorno" tamano="sm" className="bg-transparent" aria-label={`Responde con: ${NOMBRE_MODO[estado.modo]}. Cambiar`}>
          <SlidersHorizontal aria-hidden />
          <span className={cn('size-1.5 rounded-full', estado.listo ? 'bg-acento' : 'bg-aviso')} aria-hidden />
          {estado.modo === 'buscar' ? 'Solo buscar' : estado.modelo || NOMBRE_MODO[estado.modo]}
        </Boton>
      </MenuDisparador>
      <MenuContenido align="end" className="w-72">
        {(['ollama', 'openai', 'buscar'] as Modo[]).map((m) => (
          <MenuItem
            key={m}
            onSelect={() => (m === 'openai' && !ajustes.openai.modelo ? ir({ pagina: 'ajustes' }) : cambiar.mutate(m))}
            className="items-start py-2"
          >
            <Check className={cn('mt-0.5', ajustes.modo === m ? 'opacity-100' : 'opacity-0')} aria-hidden />
            <span>
              <span className="block font-medium">{NOMBRE_MODO[m]}</span>
              <span className="block text-xs text-tinta-suave">{detalle[m]}</span>
            </span>
          </MenuItem>
        ))}
        <MenuSeparador />
        <MenuItem onSelect={() => ir({ pagina: 'ajustes' })}>Más opciones</MenuItem>
      </MenuContenido>
    </MenuRaiz>
  )
}
