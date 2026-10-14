// Estudio: lo que Tesela escribe con las fuentes del chat (resumen, guía, cuestionario, mapa de ideas…) y las notas,
// propias o guardadas desde una respuesta. Como el panel Studio de NotebookLM y las transformaciones de Open Notebook.
import { useMutation } from '@tanstack/react-query'
import {
  Bot,
  CalendarRange,
  Check,
  CircleAlert,
  CircleHelp,
  Copy,
  FileUp,
  GraduationCap,
  Layers,
  ListChecks,
  MoreVertical,
  Network,
  Pencil,
  PencilLine,
  Plus,
  ScrollText,
  StickyNote,
  Trash2,
  TriangleAlert,
  User,
  X,
} from 'lucide-react'
import { type ElementType, type FormEvent, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { api, type Cuaderno, type Nota, type TipoEstudio } from '../lib/api'
import { CLAVES, useEstado, useRefrescar } from '../lib/consultas'
import { cancelar, claveNota, descartar, generarNota, TIPOS_ESTUDIO, useTrabajos } from '../lib/estudio'
import { abrirNota, pedirAlChat, useAbrirNota } from '../lib/eventos'
import { leerCuestionario, leerMapa, leerTarjetas, type Nodo, type Pregunta, type Tarjeta } from '../lib/formatos'
import { cn, haceCuanto, ir, plural, sinMarcas } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Ayuda, Campo, Confirmar, Dialogo, Etiqueta, Girando, MenuContenido, MenuDisparador, MenuItem, MenuRaiz, MenuSeparador, Texto } from '../ui/piezas'
import { Columna } from './Columna'
import { Cuestionario, MapaIdeas, Tarjetas } from './VistasEstudio'
import { ES_WEB } from '../web/config'

export const ICONO_ESTUDIO: Record<TipoEstudio, ElementType> = {
  resumen: ScrollText,
  guia: GraduationCap,
  faq: CircleHelp,
  cronologia: CalendarRange,
  cuestionario: ListChecks,
  tarjetas: Layers,
  mapa: Network,
  propia: PencilLine,
}
const ORDEN: TipoEstudio[] = ['resumen', 'guia', 'faq', 'cronologia', 'cuestionario', 'tarjetas', 'mapa', 'propia']

type Especial =
  | { nombre: 'mapa'; raiz: Nodo }
  | { nombre: 'tarjetas'; tarjetas: Tarjeta[] }
  | { nombre: 'cuestionario'; preguntas: Pregunta[] }
  | null

/** El mapa, las tarjetas o el cuestionario de una nota, si el modelo siguió el formato pedido. */
function vistaEspecial(n: Nota): Especial {
  if (n.tipo === 'mapa') {
    const raiz = leerMapa(n.titulo, n.contenido)
    return raiz && { nombre: 'mapa', raiz }
  }
  if (n.tipo === 'tarjetas') {
    const tarjetas = leerTarjetas(n.contenido)
    return tarjetas && { nombre: 'tarjetas', tarjetas }
  }
  if (n.tipo === 'cuestionario') {
    const preguntas = leerCuestionario(n.contenido)
    return preguntas && { nombre: 'cuestionario', preguntas }
  }
  return null
}

export function ColumnaEstudio({ cuaderno, plegada, alPlegar }: { cuaderno: Cuaderno; plegada?: boolean; alPlegar?: (p: boolean) => void }) {
  const [abierta, setAbierta] = useState<Nota | 'nueva' | null>(null)
  const [personalizado, setPersonalizado] = useState(false)
  const { data: estado } = useEstado()
  const trabajos = useTrabajos()
  const trabajo = trabajos[claveNota(cuaderno.id)]
  const refrescar = useRefrescar()
  const enChat = cuaderno.documentos.filter((d) => !cuaderno.fuera.includes(d.id)).length
  useAbrirNota((id) => {
    const nota = cuaderno.notas.find((n) => n.id === id)
    if (nota) setAbierta(nota)
  })

  const generar = async (tipo: TipoEstudio, instruccion = '') => {
    const nota = await generarNota(cuaderno.id, tipo, instruccion)
    await refrescar(CLAVES.cuaderno(cuaderno.id), CLAVES.cuadernos)
    if (nota) toast.success(`Listo: «${nota.titulo}»`, { action: { label: 'Abrir', onClick: () => abrirNota(nota.id) } })
  }
  const soloBuscar = estado?.modo === 'buscar'
  const ocupado = !!trabajo && !trabajo.error
  const motivo = soloBuscar
    ? `Estudio escribe con un modelo: elige ${ES_WEB ? 'una API' : 'Ollama o una API'} en Modelos.`
    : enChat === 0
      ? 'Incluye al menos una fuente en el chat para escribir con ella.'
      : ''

  return (
    <Columna
      titulo="Estudio"
      color="bg-nota"
      icono={GraduationCap}
      plegada={plegada}
      alPlegar={alPlegar}
      acciones={
        <Boton variante="fantasma" tamano="sm" aria-label="Escribir nota" onClick={() => setAbierta('nueva')}>
          <Plus />
          Nota
        </Boton>
      }
    >
      <section aria-label="Generar con las fuentes" className="space-y-2">
        <h3 className="text-xs font-medium text-tinta-suave">
          Escribir con {enChat ? plural(enChat, 'fuente del chat', 'fuentes del chat') : 'las fuentes del chat'}
        </h3>
        <div className="grid grid-cols-2 gap-1.5">
          {ORDEN.map((tipo) => {
            const Icono = ICONO_ESTUDIO[tipo]
            return (
              <Ayuda key={tipo} texto={TIPOS_ESTUDIO[tipo].descripcion}>
                <button
                  onClick={() => (tipo === 'propia' ? setPersonalizado(true) : void generar(tipo))}
                  disabled={ocupado || !!motivo}
                  className="flex min-h-10 items-center gap-2 rounded-md border bg-superficie px-2 py-1.5 text-left text-[12.5px] leading-tight font-medium transition-colors hover:border-nota/40 hover:bg-nota-tinte disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Icono className="size-4 shrink-0 text-nota" aria-hidden />
                  <span>{TIPOS_ESTUDIO[tipo].nombre}</span>
                </button>
              </Ayuda>
            )
          })}
        </div>
        {motivo && (
          <p className="text-xs text-tinta-suave">
            {motivo}{' '}
            {soloBuscar && (
              <button className="text-cita hover:underline" onClick={() => ir({ pagina: 'ajustes' })}>
                Ir a Modelos
              </button>
            )}
          </p>
        )}
      </section>

      <section aria-label="Notas" className="mt-4 space-y-2 border-t border-linea-suave pt-3">
        <h3 className="text-xs font-medium text-tinta-suave">Notas{cuaderno.notas.length ? ` (${cuaderno.notas.length})` : ''}</h3>
        {trabajo && <TarjetaTrabajo clave={claveNota(cuaderno.id)} titulo={trabajo.titulo} paso={trabajo.paso} error={trabajo.error} />}
        {cuaderno.notas.length === 0 && !trabajo ? (
          <div className="rounded-lg border border-dashed p-4 text-left">
            <StickyNote className="mb-3 size-5 text-nota" aria-hidden />
            <p className="mb-1 text-[13px] font-medium">Lo que vale la pena guardar</p>
            <p className="text-[13px] text-tinta-suave">Escribe una idea, guarda una respuesta del chat o pide arriba un resumen o una guía de estudio.</p>
          </div>
        ) : (
          cuaderno.notas.map((n) => <TarjetaNota key={n.id} nota={n} cuaderno={cuaderno.id} alAbrir={() => setAbierta(n)} />)
        )}
      </section>

      {/* la nota abierta se busca en el cuaderno al día: después de editarla se ve lo nuevo */}
      <DialogoNota
        cuaderno={cuaderno.id}
        nota={abierta && abierta !== 'nueva' ? (cuaderno.notas.find((n) => n.id === abierta.id) ?? abierta) : abierta}
        alCerrar={() => setAbierta(null)}
      />
      <DialogoPersonalizado
        abierto={personalizado}
        alCambiar={setPersonalizado}
        alEnviar={(instruccion) => {
          setPersonalizado(false)
          void generar('propia', instruccion)
        }}
      />
    </Columna>
  )
}

function TarjetaTrabajo({ clave, titulo, paso, error }: { clave: string; titulo: string; paso: string; error?: string }) {
  if (error)
    return (
      <div className="rounded-md border border-peligro/30 bg-peligro-tinte p-3 text-[13px]" role="alert">
        <div className="flex items-start gap-2">
          <CircleAlert className="mt-0.5 size-4 shrink-0 text-peligro" aria-hidden />
          <p className="min-w-0 flex-1">
            <span className="block font-medium">No pude escribir {titulo}</span>
            <span className="text-tinta-suave">{error}</span>
          </p>
          <Boton variante="fantasma" tamano="icono-sm" onClick={() => descartar(clave)} aria-label="Cerrar el aviso">
            <X />
          </Boton>
        </div>
      </div>
    )
  return (
    <div className="rounded-md border border-nota/30 bg-nota-tinte p-3 text-[13px]" role="status">
      <div className="flex items-start gap-2">
        <Girando className="mt-0.5 shrink-0 text-nota" />
        <p className="min-w-0 flex-1">
          <span className="block font-medium">Escribiendo {titulo}</span>
          {paso !== `Escribiendo ${titulo}` && <span className="block text-xs text-tinta-suave">{paso}</span>}
        </p>
      </div>
      <div className="mt-2 flex justify-end">
        <Boton variante="fantasma" tamano="sm" onClick={() => cancelar(clave)}>
          Cancelar
        </Boton>
      </div>
    </div>
  )
}

function insignia(n: Nota): { texto: string; icono: ElementType; clase: string } {
  if (n.origen === 'generada' && n.tipo) return { texto: TIPOS_ESTUDIO[n.tipo].nombre, icono: ICONO_ESTUDIO[n.tipo], clase: 'text-nota' }
  if (n.origen === 'respuesta') return { texto: 'Respuesta', icono: Bot, clase: 'text-cita' }
  return { texto: 'Tuya', icono: User, clase: 'text-tinta-suave' }
}

function useConvertirEnFuente(cuaderno: string, nota: Nota) {
  const refrescar = useRefrescar()
  return useMutation({
    mutationFn: async () => {
      const nombre = `${(nota.titulo || sinMarcas(nota.contenido).split('\n')[0] || 'Nota').slice(0, 80).replace(/[\\/:*?"<>|]/g, '')}.md`
      const procedencia = nota.origen === 'propia' ? '' : [
        '## Procedencia de esta nota',
        'Origen: texto generado por IA. Es una fuente derivada; comprueba sus afirmaciones en los documentos originales.',
        `Nota: ${nota.id}. Cuaderno: ${cuaderno}. Creada: ${nota.creado}.`,
        nota.modelo ? `Modelo: ${nota.modelo}.` : '',
        ...(nota.fuentes?.map((f) => `Fuente utilizada: ${f.nombre} (${f.id}).`) ?? []),
        ...(nota.avisos?.map((aviso) => `Advertencia de la nota original: ${aviso}`) ?? []),
        '## Contenido de la nota',
      ].filter(Boolean).join('\n\n') + '\n\n'
      const texto = `${nota.titulo ? `# ${nota.titulo}\n\n` : ''}${procedencia}${nota.contenido}`
      const final = await api.subir(new File([texto], nombre, { type: 'text/markdown' }), cuaderno, () => {})
      if (final.tipo === 'error') throw new Error(final.texto)
      return nombre
    },
    onSuccess: (nombre) => {
      toast.success(`«${nombre}» ya es una fuente`, { description: 'Entra al chat y a lo que escribas en Estudio.' })
      refrescar(CLAVES.cuaderno(cuaderno), CLAVES.documentos, CLAVES.cuadernos, CLAVES.estado)
    },
    onError: (e) => toast.error(e.message),
  })
}

function TarjetaNota({ nota: n, cuaderno, alAbrir }: { nota: Nota; cuaderno: string; alAbrir: () => void }) {
  const [borrando, setBorrando] = useState(false)
  const refrescar = useRefrescar()
  const convertir = useConvertirEnFuente(cuaderno, n)
  const borrar = useMutation({
    mutationFn: () => api.borrarNota(cuaderno, n.id),
    onSuccess: () => {
      setBorrando(false)
      refrescar(CLAVES.cuaderno(cuaderno), CLAVES.cuadernos)
    },
    onError: (e) => toast.error(e.message),
  })
  const { texto, icono: Icono, clase } = insignia(n)
  return (
    <article className="group relative rounded-md border bg-superficie p-3 transition-colors hover:bg-hundida/40">
      <div className="mb-1.5 flex items-center justify-between gap-2 pr-8">
        <span className="flex min-w-0 items-center gap-1.5">
          <Icono className={cn('size-3.5 shrink-0', clase)} aria-hidden />
          <span className="truncate text-xs font-medium text-tinta-suave">{texto}</span>
        </span>
        <span className="shrink-0 text-xs text-tinta-tenue">{haceCuanto(n.actualizado)}</span>
      </div>
      <button onClick={alAbrir} className="block w-full text-left after:absolute after:inset-0" aria-label={`Abrir la nota ${n.titulo || 'sin título'}`}>
        {n.titulo && <span className="mb-1 block text-[13.5px] leading-snug font-medium break-words">{n.titulo}</span>}
        {n.contenido && <span className="line-clamp-3 text-[13px] whitespace-pre-line text-tinta-suave">{sinMarcas(n.contenido)}</span>}
      </button>
      <MenuRaiz>
        <MenuDisparador asChild>
          <Boton
            variante="fantasma"
            tamano="icono-sm"
            className="absolute top-2 right-2 z-10 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
            aria-label={`Opciones de la nota ${n.titulo}`}
          >
            <MoreVertical />
          </Boton>
        </MenuDisparador>
        <MenuContenido>
          <MenuItem icono={FileUp} onSelect={() => convertir.mutate()} disabled={convertir.isPending}>
            Convertir en fuente
          </MenuItem>
          <MenuSeparador />
          <MenuItem icono={Trash2} peligro onSelect={() => setBorrando(true)}>
            Borrar nota
          </MenuItem>
        </MenuContenido>
      </MenuRaiz>
      <Confirmar
        abierto={borrando}
        alCambiar={setBorrando}
        titulo="¿Borrar la nota?"
        descripcion={n.titulo ? `«${n.titulo}» se borra y no se puede recuperar.` : 'No se puede recuperar.'}
        accion="Borrar nota"
        ocupado={borrar.isPending}
        alConfirmar={() => borrar.mutate()}
      />
    </article>
  )
}

function DialogoNota({ cuaderno, nota, alCerrar }: { cuaderno: string; nota: Nota | 'nueva' | null; alCerrar: () => void }) {
  const [editando, setEditando] = useState(false)
  // solo al abrir otra nota: si el cuaderno se vuelve a pedir mientras se edita, no se pierde lo escrito
  const clave = nota === 'nueva' ? 'nueva' : nota?.id
  useEffect(() => setEditando(clave === 'nueva'), [clave])
  const ancho = nota && nota !== 'nueva' && nota.tipo === 'mapa' && !editando ? 'max-w-5xl' : 'max-w-3xl'
  const titulo = nota === 'nueva' ? 'Nueva nota' : editando ? 'Editar nota' : nota?.titulo || 'Nota'
  return (
    <Dialogo
      abierto={nota !== null}
      alCambiar={(a) => !a && alCerrar()}
      titulo={titulo}
      descripcion={nota && nota !== 'nueva' && !editando ? <Procedencia nota={nota} /> : undefined}
      ancho={ancho}
    >
      {nota && (editando || nota === 'nueva' ? (
        <EditorNota cuaderno={cuaderno} nota={nota} alTerminar={nota === 'nueva' ? alCerrar : () => setEditando(false)} />
      ) : (
        <VisorNota cuaderno={cuaderno} nota={nota} alEditar={() => setEditando(true)} alCerrar={alCerrar} />
      ))}
    </Dialogo>
  )
}

function Procedencia({ nota: n }: { nota: Nota }) {
  const { texto } = insignia(n)
  const partes = [texto]
  if (n.origen === 'generada') {
    if (n.modelo) partes.push(n.modelo)
    if (n.fuentes?.length) partes.push(`con ${plural(n.fuentes.length, 'fuente', 'fuentes')}`)
  }
  partes.push(haceCuanto(n.creado))
  return <>{partes.join(' · ')}</>
}

function VisorNota({ cuaderno, nota: n, alEditar, alCerrar }: { cuaderno: string; nota: Nota; alEditar: () => void; alCerrar: () => void }) {
  const [comoTexto, setComoTexto] = useState(false)
  const [copiado, setCopiado] = useState(false)
  const [borrando, setBorrando] = useState(false)
  const refrescar = useRefrescar()
  const convertir = useConvertirEnFuente(cuaderno, n)
  const borrar = useMutation({
    mutationFn: () => api.borrarNota(cuaderno, n.id),
    onSuccess: () => {
      refrescar(CLAVES.cuaderno(cuaderno), CLAVES.cuadernos)
      alCerrar()
    },
    onError: (e) => toast.error(e.message),
  })
  const especial = useMemo(() => vistaEspecial(n), [n])
  const preguntar = (texto: string) => {
    alCerrar()
    pedirAlChat(`Explícame «${texto}» según las fuentes.`)
  }
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(n.titulo ? `# ${n.titulo}\n\n${n.contenido}` : n.contenido)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 1600)
    } catch {
      toast.error('No pude copiar al portapapeles.')
    }
  }
  return (
    <div className="flex flex-col">
      <div className="space-y-4 px-5 py-4">
        {!!n.avisos?.length && (
          <p className="flex items-start gap-2 rounded-md border border-aviso/30 bg-aviso-tinte px-3 py-2 text-[13px]" role="note">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-aviso" aria-hidden />
            <span>
              Revisa {n.avisos.length === 1 ? 'esta cifra: no aparece' : 'estas cifras: no aparecen'} en las fuentes:{' '}
              <strong className="font-semibold">{n.avisos.join(', ')}</strong>. Puede ser un cálculo o un error del modelo.
            </span>
          </p>
        )}
        {especial && !comoTexto ? (
          especial.nombre === 'mapa' ? (
            <MapaIdeas raiz={especial.raiz} alPreguntar={preguntar} />
          ) : especial.nombre === 'tarjetas' ? (
            <Tarjetas tarjetas={especial.tarjetas} />
          ) : (
            <Cuestionario preguntas={especial.preguntas} />
          )
        ) : (
          // el HTML lo arma el servidor a partir del texto escapado (web.markdown_nota)
          <div className="prosa max-w-[72ch] text-[14.5px] leading-relaxed" dangerouslySetInnerHTML={{ __html: n.html }} />
        )}
        {n.origen === 'generada' && (
          <div className="space-y-1.5 border-t pt-3 text-xs text-tinta-suave">
            {!!n.fuentes?.length && (
              <p className="flex flex-wrap items-center gap-1.5">
                <span>Escrito con:</span>
                {n.fuentes.map((f) => (
                  <span key={f.id} className="rounded-sm bg-hundida px-1.5 py-0.5 font-medium">
                    {f.nombre}
                  </span>
                ))}
              </p>
            )}
            {n.leido !== undefined && n.leido < 1 && (
              <p>
                Las fuentes eran largas: el modelo leyó un {Math.round(n.leido * 100)} % del texto, en partes repartidas por cada documento.
              </p>
            )}
            {n.instruccion && <p>Lo que pediste: «{n.instruccion}»</p>}
          </div>
        )}
      </div>
      <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-2 border-t bg-elevada px-5 py-3">
        <div className="flex flex-wrap gap-1">
          <Boton variante="fantasma" tamano="sm" onClick={alEditar}>
            <Pencil />
            Editar
          </Boton>
          <Boton variante="fantasma" tamano="sm" onClick={copiar}>
            {copiado ? <Check /> : <Copy />}
            {copiado ? 'Copiada' : 'Copiar'}
          </Boton>
          <Boton variante="fantasma" tamano="sm" onClick={() => convertir.mutate()} disabled={convertir.isPending || convertir.isSuccess}>
            {convertir.isPending ? <Girando /> : <FileUp />}
            {convertir.isSuccess ? 'Ya es una fuente' : 'Convertir en fuente'}
          </Boton>
          {especial && (
            <Boton variante="fantasma" tamano="sm" onClick={() => setComoTexto((x) => !x)}>
              {comoTexto ? `Ver ${especial.nombre === 'mapa' ? 'el mapa' : especial.nombre === 'tarjetas' ? 'las tarjetas' : 'el cuestionario'}` : 'Ver como texto'}
            </Boton>
          )}
        </div>
        <Boton variante="fantasma" tamano="sm" className="hover:text-peligro" onClick={() => setBorrando(true)}>
          <Trash2 />
          Borrar
        </Boton>
      </div>
      <Confirmar
        abierto={borrando}
        alCambiar={setBorrando}
        titulo="¿Borrar la nota?"
        descripcion={n.titulo ? `«${n.titulo}» se borra y no se puede recuperar.` : 'No se puede recuperar.'}
        accion="Borrar nota"
        ocupado={borrar.isPending}
        alConfirmar={() => borrar.mutate()}
      />
    </div>
  )
}

function EditorNota({ cuaderno, nota, alTerminar }: { cuaderno: string; nota: Nota | 'nueva'; alTerminar: () => void }) {
  const [titulo, setTitulo] = useState(nota !== 'nueva' ? nota.titulo : '')
  const [contenido, setContenido] = useState(nota !== 'nueva' ? nota.contenido : '')
  const refrescar = useRefrescar()
  const guardar = useMutation({
    mutationFn: () =>
      nota !== 'nueva' ? api.cambiarNota(cuaderno, nota.id, { titulo, contenido }) : api.crearNota(cuaderno, { titulo, contenido, origen: 'propia' }),
    onSuccess: async () => {
      await refrescar(CLAVES.cuaderno(cuaderno), CLAVES.cuadernos)
      alTerminar()
    },
    onError: (e) => toast.error(e.message),
  })
  const enviar = (e: FormEvent) => {
    e.preventDefault()
    if (titulo.trim() || contenido.trim()) guardar.mutate()
  }
  return (
    <form onSubmit={enviar} className="flex h-full flex-col gap-4 p-5">
      <div>
        <Etiqueta htmlFor="titulo-nota">Título</Etiqueta>
        <Campo id="titulo-nota" value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={200} placeholder="Sin título" />
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <Etiqueta htmlFor="contenido-nota">Contenido</Etiqueta>
        <Texto
          id="contenido-nota"
          value={contenido}
          onChange={(e) => setContenido(e.target.value)}
          rows={14}
          maxLength={50000}
          className="min-h-48 flex-1 leading-relaxed"
          autoFocus={nota === 'nueva'}
        />
        <p className="mt-1.5 text-xs text-tinta-tenue">Admite Markdown: **negrita**, listas con «- », títulos con «## ».</p>
      </div>
      <div className="flex justify-end gap-2">
        <Boton variante="contorno" onClick={alTerminar}>
          Cancelar
        </Boton>
        <Boton type="submit" variante="principal" disabled={guardar.isPending || !(titulo.trim() || contenido.trim())}>
          {guardar.isPending && <Girando className="text-sobre-primario" />}
          Guardar nota
        </Boton>
      </div>
    </form>
  )
}

const EJEMPLOS = [
  'Una tabla con cada plazo y quién es responsable',
  'Explica los conceptos como a alguien que recién empieza',
  'Una lista de los riesgos y cómo se controlan',
]

function DialogoPersonalizado({
  abierto,
  alCambiar,
  alEnviar,
}: {
  abierto: boolean
  alCambiar: (a: boolean) => void
  alEnviar: (instruccion: string) => void
}) {
  const [texto, setTexto] = useState('')
  useEffect(() => {
    if (abierto) setTexto('')
  }, [abierto])
  return (
    <Dialogo
      abierto={abierto}
      alCambiar={alCambiar}
      titulo="Escribir con tus fuentes"
      descripcion="Di qué quieres: el modelo lo escribe con las fuentes del chat y queda como nota."
    >
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault()
          if (texto.trim()) alEnviar(texto.trim())
        }}
      >
        <div>
          <Etiqueta htmlFor="instruccion">Qué escribir</Etiqueta>
          <Texto id="instruccion" value={texto} onChange={(e) => setTexto(e.target.value)} rows={4} maxLength={1500} autoFocus placeholder="Por ejemplo: un correo para el equipo que resuma los cambios" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {EJEMPLOS.map((e) => (
            <button key={e} type="button" onClick={() => setTexto(e)} className="rounded-full border bg-superficie px-2.5 py-1 text-xs text-tinta-suave hover:border-nota/40 hover:bg-nota-tinte hover:text-tinta">
              {e}
            </button>
          ))}
        </div>
        <div className="flex justify-end gap-2">
          <Boton variante="contorno" onClick={() => alCambiar(false)}>
            Cancelar
          </Boton>
          <Boton type="submit" variante="principal" disabled={!texto.trim()}>
            <PencilLine />
            Escribir
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}
