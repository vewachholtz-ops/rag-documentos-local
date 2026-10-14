import { useMutation } from '@tanstack/react-query'
import {
  CircleAlert,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FileText,
  FolderSync,
  Globe,
  Lightbulb,
  Link2,
  MoreVertical,
  Plus,
  Trash2,
  Type,
  Unlink,
  Upload,
  X,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { api, type Cuaderno, type Documento, TIPOS_ACEPTADOS } from '../lib/api'
import { CLAVES, useDocumentos, useEstado, useRefrescar } from '../lib/consultas'
import { abrirOriginal, etiquetaOriginal } from '../lib/original'
import type { Subida } from '../lib/subidas'
import { cn, dominio, NOMBRE_TIPO, plural, tamanoArchivo } from '../lib/utiles'
import { Boton } from '../ui/boton'
import {
  Ayuda,
  Barra,
  Confirmar,
  Dialogo,
  Girando,
  MenuContenido,
  MenuDisparador,
  MenuItem,
  MenuRaiz,
  MenuSeparador,
} from '../ui/piezas'
import { DialogoAgregarFuente } from './AgregarFuente'
import { DialogoCarpeta, ListaCarpetas } from './Carpetas'
import { Columna } from './Columna'
import type { AbrirVisor } from './Visor'
import { ES_WEB } from '../web/config'

export const COLOR_TIPO: Record<Documento['tipo'], string> = {
  pdf: 'bg-nota',
  docx: 'bg-pizarra',
  pptx: 'bg-aviso',
  xlsx: 'bg-acento',
  csv: 'bg-acento',
  html: 'bg-cita',
  md: 'bg-gris',
  txt: 'bg-gris',
}

export function detalleDocumento(d: Documento) {
  if (d.url) return `Página web · ${dominio(d.url)}`
  const partes: string[] = [NOMBRE_TIPO[d.tipo]]
  if (d.paginas) partes.push(plural(d.paginas, 'página', 'páginas'))
  partes.push(tamanoArchivo(d.bytes))
  return partes.join(' · ')
}

/** Lo que se ve al abrir una fuente: su guía si la tiene (o si hay un modelo para escribirla); si no, el texto. */
export function vistaDe(d: Documento, soloBuscar: boolean) {
  return {
    doc_id: d.id,
    documento: d.nombre,
    tipo: d.tipo,
    url: d.url,
    pestana: d.guia || !soloBuscar ? ('guia' as const) : ('documento' as const),
  }
}

export function ColumnaFuentes({
  cuaderno,
  subidas,
  alSubir,
  alDescartar,
  abrir,
  plegada,
  alPlegar,
}: {
  cuaderno: Cuaderno
  subidas: Subida[]
  alSubir: (archivos: FileList | File[]) => void
  alDescartar: (clave: string) => void
  abrir: AbrirVisor
  plegada?: boolean
  alPlegar?: (p: boolean) => void
}) {
  const selector = useRef<HTMLInputElement>(null)
  const [desdeBiblioteca, setDesdeBiblioteca] = useState(false)
  const [agregarComo, setAgregarComo] = useState<'texto' | 'enlace' | null>(null)
  const [conectarCarpeta, setConectarCarpeta] = useState(false)
  const refrescar = useRefrescar()
  const fuera = new Set(cuaderno.fuera)

  const cambiarFuera = useMutation({
    mutationFn: (nuevas: string[]) => api.cambiarCuaderno(cuaderno.id, { fuera: nuevas }),
    onSuccess: () => refrescar(CLAVES.cuaderno(cuaderno.id)),
    onError: (e) => toast.error(e.message),
  })
  const alternar = (id: string) =>
    cambiarFuera.mutate(fuera.has(id) ? cuaderno.fuera.filter((x) => x !== id) : [...cuaderno.fuera, id])

  return (
    <Columna
      titulo="Fuentes"
      color="bg-gris"
      icono={FileText}
      plegada={plegada}
      alPlegar={alPlegar}
      acciones={
        <>
          <input
            ref={selector}
            type="file"
            multiple
            accept={TIPOS_ACEPTADOS}
            className="hidden"
            data-prueba="elegir-archivos"
            onChange={(e) => {
              if (e.target.files?.length) alSubir(e.target.files)
              e.target.value = ''
            }}
          />
          <MenuRaiz>
            <MenuDisparador asChild>
              <Boton variante="contorno" tamano="sm" aria-label="Agregar fuente">
                <Plus />
                <span className="hidden max-lg:inline xl:inline">Agregar</span>
              </Boton>
            </MenuDisparador>
            <MenuContenido>
              <MenuItem icono={Upload} onSelect={() => selector.current?.click()}>
                Subir archivos
              </MenuItem>
              {!ES_WEB && (
                <MenuItem icono={Globe} onSelect={() => setAgregarComo('enlace')}>
                  Agregar un enlace
                </MenuItem>
              )}
              <MenuItem icono={Type} onSelect={() => setAgregarComo('texto')}>
                Pegar texto
              </MenuItem>
              <MenuItem icono={Link2} onSelect={() => setDesdeBiblioteca(true)}>
                Agregar una que ya está en la biblioteca
              </MenuItem>
              {!ES_WEB && (
                <MenuItem icono={FolderSync} onSelect={() => setConectarCarpeta(true)}>
                  Conectar una carpeta
                </MenuItem>
              )}
            </MenuContenido>
          </MenuRaiz>
        </>
      }
    >
      <div className="space-y-2">
        <ListaCarpetas cuaderno={cuaderno.id} />
        {subidas.map((s) => (
          <FilaSubida key={s.clave} subida={s} alDescartar={() => alDescartar(s.clave)} />
        ))}
        {cuaderno.documentos.length === 0 && subidas.length === 0 ? (
          <ZonaVacia alElegir={() => selector.current?.click()} alEnlace={() => setAgregarComo('enlace')} />
        ) : (
          cuaderno.documentos.map((d) => (
            <TarjetaFuente
              key={d.id}
              documento={d}
              cuaderno={cuaderno.id}
              enChat={!fuera.has(d.id)}
              alAlternar={() => alternar(d.id)}
              abrir={abrir}
            />
          ))
        )}
      </div>
      <DialogoBiblioteca abierto={desdeBiblioteca} alCambiar={setDesdeBiblioteca} cuaderno={cuaderno} />
      <DialogoAgregarFuente
        abierto={agregarComo !== null}
        alCambiar={(a) => !a && setAgregarComo(null)}
        cuaderno={cuaderno.id}
        tipoInicial={agregarComo ?? 'texto'}
      />
      <DialogoCarpeta abierto={conectarCarpeta} alCambiar={setConectarCarpeta} cuaderno={cuaderno.id} />
    </Columna>
  )
}

export function textoEnChat(enChat: number, total: number) {
  if (enChat === total) return total === 1 ? 'La fuente entra al chat' : `Las ${total} fuentes entran al chat`
  if (enChat === 0) return 'Ninguna fuente entra al chat'
  return `${enChat} de ${total} fuentes entran al chat`
}

function ZonaVacia({ alElegir, alEnlace }: { alElegir: () => void; alEnlace: () => void }) {
  return (
    <div className="py-12 text-center">
      <FileText className="mx-auto mb-4 size-12 text-tinta-suave/60" aria-hidden />
      <h3 className="mb-2 text-lg font-medium">Agrega tus documentos</h3>
      <p className="mb-4 text-tinta-suave">
        {ES_WEB
          ? 'PDF, Word, PowerPoint, Excel o texto. Arrástralos aquí o elígelos.'
          : 'PDF, Word, PowerPoint, Excel o texto. Arrástralos aquí, elígelos o pega el enlace de una página.'}
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        <Boton variante="principal" tamano="sm" onClick={alElegir}>
          <Upload />
          Subir archivos
        </Boton>
        {!ES_WEB && (
          <Boton variante="contorno" tamano="sm" onClick={alEnlace}>
            <Globe />
            Un enlace
          </Boton>
        )}
      </div>
    </div>
  )
}

function FilaSubida({ subida: s, alDescartar }: { subida: Subida; alDescartar: () => void }) {
  return (
    <div className={cn('rounded-md border p-3', s.error ? 'border-peligro/40 bg-peligro-tinte' : 'bg-elevada')} role="status">
      <div className="flex items-start gap-2">
        {s.error ? <CircleAlert className="mt-0.5 size-4 shrink-0 text-peligro" aria-hidden /> : <Girando className="mt-0.5 shrink-0" />}
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium">{s.nombre}</p>
          <p className={cn('text-xs', s.error ? 'text-peligro' : 'text-tinta-suave')}>{s.error ?? s.paso}</p>
        </div>
        {s.error && (
          <Boton variante="fantasma" tamano="icono-sm" onClick={alDescartar} aria-label={`Descartar el aviso de ${s.nombre}`}>
            <X />
          </Boton>
        )}
      </div>
      {!s.error && (
        <div className="mt-2.5">
          <Barra valor={s.avance} />
        </div>
      )}
    </div>
  )
}

function TarjetaFuente({
  documento: d,
  cuaderno,
  enChat,
  alAlternar,
  abrir,
}: {
  documento: Documento
  cuaderno: string
  enChat: boolean
  alAlternar: () => void
  abrir: AbrirVisor
}) {
  const [borrando, setBorrando] = useState(false)
  const { data: estado } = useEstado()
  const refrescar = useRefrescar()
  const actualizar = () => refrescar(CLAVES.cuaderno(cuaderno), CLAVES.documentos, CLAVES.cuadernos, CLAVES.estado)
  const ver = (pestana?: 'guia' | 'documento') => abrir({ ...vistaDe(d, estado?.modo === 'buscar'), ...(pestana ? { pestana } : {}) })
  const IconoTipo = d.url ? Globe : FileText
  const sacar = useMutation({
    mutationFn: () => api.desenlazar(cuaderno, d.id),
    onSuccess: () => {
      toast(`Sacaste «${d.nombre}» del cuaderno`, { description: 'Sigue en la biblioteca.' })
      actualizar()
    },
    onError: (e) => toast.error(e.message),
  })
  const borrar = useMutation({
    mutationFn: () => api.borrarDocumento(d.id),
    onSuccess: () => {
      setBorrando(false)
      toast.success(`Borraste «${d.nombre}»`)
      actualizar()
    },
    onError: (e) => toast.error(e.message),
  })
  return (
    <article className="group relative rounded-lg border bg-superficie transition-colors duration-150 hover:border-gris/50">
      <button onClick={() => ver()} className="block w-full px-4 py-6 pr-14 text-left" aria-label={`Ver ${d.nombre}`}>
        <span className={cn('line-clamp-2 block text-sm leading-tight font-medium break-words', !enChat && 'text-tinta-suave')}>
          {d.nombre}
        </span>
        <span className="mt-1.5 flex items-center gap-1.5 text-xs text-tinta-suave">
          <IconoTipo className="size-3 shrink-0" aria-hidden />
          <span className="truncate">{detalleDocumento(d)}</span>
        </span>
      </button>
      <div className="absolute top-1/2 right-3 -translate-y-1/2">
        <Ayuda texto={enChat ? 'Entra al chat. Toca para dejarla fuera.' : 'Fuera del chat. Toca para incluirla.'}>
          <Boton
            variante="fantasma"
            tamano="icono"
            onClick={alAlternar}
            aria-pressed={enChat}
            aria-label={enChat ? `Dejar ${d.nombre} fuera del chat` : `Incluir ${d.nombre} en el chat`}
            className={enChat ? 'text-acento hover:bg-acento-tinte hover:text-acento' : 'text-tinta-tenue'}
          >
            {enChat ? <Eye /> : <EyeOff />}
          </Boton>
        </Ayuda>
      </div>
      <MenuRaiz>
        <MenuDisparador asChild>
          <Boton
            variante="fantasma"
            tamano="icono-sm"
            className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
            aria-label={`Opciones de ${d.nombre}`}
          >
            <MoreVertical />
          </Boton>
        </MenuDisparador>
        <MenuContenido>
          <MenuItem icono={Lightbulb} onSelect={() => ver('guia')}>
            {d.guia ? 'Ver la guía' : 'Escribir la guía'}
          </MenuItem>
          <MenuItem icono={FileText} onSelect={() => ver('documento')}>
            Ver el texto
          </MenuItem>
          <MenuItem icono={d.url || d.tipo === 'pdf' ? ExternalLink : Download} onSelect={() => abrirOriginal(d)}>
            {etiquetaOriginal(d)}
          </MenuItem>
          <MenuSeparador />
          <MenuItem icono={Unlink} onSelect={() => sacar.mutate()}>
            Sacar del cuaderno
          </MenuItem>
          <MenuItem icono={Trash2} peligro onSelect={() => setBorrando(true)}>
            Borrar de la biblioteca
          </MenuItem>
        </MenuContenido>
      </MenuRaiz>
      <Confirmar
        abierto={borrando}
        alCambiar={setBorrando}
        titulo={`¿Borrar «${d.nombre}»?`}
        descripcion="Sale de la biblioteca y de todos los cuadernos. El archivo original en tu computador no se toca."
        accion="Borrar documento"
        ocupado={borrar.isPending}
        alConfirmar={() => borrar.mutate()}
      />
    </article>
  )
}

function DialogoBiblioteca({ abierto, alCambiar, cuaderno }: { abierto: boolean; alCambiar: (a: boolean) => void; cuaderno: Cuaderno }) {
  const { data: documentos, isLoading } = useDocumentos()
  const refrescar = useRefrescar()
  const ya = new Set(cuaderno.documentos.map((d) => d.id))
  const disponibles = (documentos ?? []).filter((d) => !ya.has(d.id))
  const enlazar = useMutation({
    mutationFn: (id: string) => api.enlazar(cuaderno.id, id),
    onSuccess: () => refrescar(CLAVES.cuaderno(cuaderno.id), CLAVES.documentos, CLAVES.cuadernos),
    onError: (e) => toast.error(e.message),
  })
  return (
    <Dialogo
      abierto={abierto}
      alCambiar={alCambiar}
      titulo="Agregar desde la biblioteca"
      descripcion="Documentos que ya subiste en otros cuadernos. No se copian: el mismo documento queda en los dos."
    >
      <div className="p-3">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <Girando />
          </div>
        ) : disponibles.length === 0 ? (
          <p className="px-2 py-8 text-center text-[13px] text-tinta-suave">
            {documentos?.length ? 'Todos los documentos de la biblioteca ya están en este cuaderno.' : 'La biblioteca todavía está vacía.'}
          </p>
        ) : (
          <ul className="space-y-1">
            {disponibles.map((d) => (
              <li key={d.id} className="flex items-center gap-3 rounded-md px-2 py-2 hover:bg-hundida">
                <span aria-hidden className={cn('size-2 shrink-0 rounded-[3px]', COLOR_TIPO[d.tipo])} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] font-medium">{d.nombre}</span>
                  <span className="block text-xs text-tinta-suave">{detalleDocumento(d)}</span>
                </span>
                <Boton
                  tamano="sm"
                  variante="contorno"
                  disabled={enlazar.isPending && enlazar.variables === d.id}
                  onClick={() => enlazar.mutate(d.id)}
                >
                  <Plus />
                  Agregar
                </Boton>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Dialogo>
  )
}
