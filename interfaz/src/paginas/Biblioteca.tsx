// Todos los documentos, estén en el cuaderno que estén.
import { useMutation } from '@tanstack/react-query'
import { Download, ExternalLink, FileText, Globe, Library, Search, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { ListaCarpetas } from '../componentes/Carpetas'
import { DialogoAgregarFuente } from '../componentes/AgregarFuente'
import { COLOR_TIPO, detalleDocumento, vistaDe } from '../componentes/Fuentes'
import { Visor, type Vista } from '../componentes/Visor'
import { api, type Documento, TIPOS_ACEPTADOS } from '../lib/api'
import { CLAVES, useDocumentos, useEstado, useRefrescar } from '../lib/consultas'
import { abrirOriginal, etiquetaOriginal } from '../lib/original'
import { useSubidas } from '../lib/subidas'
import { cn, enlace, haceCuanto } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Barra, Campo, Confirmar, Girando, Vacio } from '../ui/piezas'
import { ES_WEB } from '../web/config'

export function PaginaBiblioteca() {
  const { data: documentos, isLoading } = useDocumentos()
  const { data: estado } = useEstado()
  const { subidas, agregar, descartar } = useSubidas(null)
  const [filtro, setFiltro] = useState('')
  const [vista, setVista] = useState<Vista | null>(null)
  const [conEnlace, setEnlace] = useState(false)
  const selector = useRef<HTMLInputElement>(null)
  const visibles = (documentos ?? []).filter((d) => d.nombre.toLowerCase().includes(filtro.trim().toLowerCase()))

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="space-y-5 p-4 sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-display text-2xl font-bold tracking-tight">Fuentes</h1>
            <p className="mt-0.5 text-[13px] text-tinta-suave">Todos tus documentos, estén en el cuaderno que estén. Uno puede estar en varios.</p>
          </div>
          <div className="flex gap-2">
            {!!documentos?.length && (
              <div className="relative flex-1 sm:w-56 sm:flex-none">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-tinta-tenue" />
                <Campo value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder="Buscar por nombre" aria-label="Buscar documentos" className="pl-8" />
              </div>
            )}
            <input
              ref={selector}
              type="file"
              multiple
              accept={TIPOS_ACEPTADOS}
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) agregar(e.target.files)
                e.target.value = ''
              }}
            />
            {!ES_WEB && (
              <Boton variante="contorno" onClick={() => setEnlace(true)}>
                <Globe />
                <span className="max-sm:sr-only">Agregar un enlace</span>
              </Boton>
            )}
            <Boton variante="principal" onClick={() => selector.current?.click()}>
              <Upload />
              Subir archivos
            </Boton>
          </div>
        </div>

        {subidas.length > 0 && (
          <ul className="space-y-2">
            {subidas.map((s) => (
              <li key={s.clave} className={cn('rounded-md border p-3', s.error ? 'border-peligro/40 bg-peligro-tinte' : 'bg-superficie')}>
                <div className="flex items-center justify-between gap-3 text-[13px]">
                  <span className="truncate font-medium">{s.nombre}</span>
                  {s.error ? (
                    <button onClick={() => descartar(s.clave)} className="text-xs text-peligro hover:underline">
                      {s.error} (cerrar)
                    </button>
                  ) : (
                    <span className="shrink-0 text-xs text-tinta-suave">{s.paso}</span>
                  )}
                </div>
                {!s.error && (
                  <div className="mt-2">
                    <Barra valor={s.avance} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        <ListaCarpetas todas />

        {isLoading ? (
          <div className="flex justify-center py-16">
            <Girando className="size-6" />
          </div>
        ) : !documentos?.length ? (
          <div className="rounded-lg border bg-superficie">
            <Vacio icono={Library} titulo="Todavía no hay fuentes">
              Los documentos que agregues a un cuaderno quedan aquí. También puedes subirlos directo y sumarlos a un cuaderno después.
            </Vacio>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border bg-superficie">
            <ul className="divide-y">
              {visibles.map((d) => (
                <FilaDocumento key={d.id} documento={d} alVer={() => setVista(vistaDe(d, estado?.modo === 'buscar'))} />
              ))}
              {!visibles.length && <li className="px-4 py-6 text-center text-tinta-suave">Ningún documento se llama así.</li>}
            </ul>
          </div>
        )}
      </div>
      <Visor vista={vista} alCerrar={() => setVista(null)} />
      <DialogoAgregarFuente abierto={conEnlace} alCambiar={setEnlace} tipoInicial="enlace" />
    </div>
  )
}

function FilaDocumento({ documento: d, alVer }: { documento: Documento; alVer: () => void }) {
  const [borrando, setBorrando] = useState(false)
  const refrescar = useRefrescar()
  const borrar = useMutation({
    mutationFn: () => api.borrarDocumento(d.id),
    onSuccess: () => {
      setBorrando(false)
      toast.success(`Borraste «${d.nombre}»`)
      refrescar(CLAVES.documentos, CLAVES.cuadernos, CLAVES.estado, ['cuaderno'])
    },
    onError: (e) => toast.error(e.message),
  })
  const cuadernos = d.cuadernos ?? []
  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
      <button onClick={alVer} className="flex min-w-0 flex-1 items-start gap-3 text-left">
        <span aria-hidden className={cn('mt-1.5 size-2 shrink-0 rounded-[3px]', COLOR_TIPO[d.tipo])} />
        <span className="min-w-0">
          <span className="block truncate text-[14px] font-medium hover:underline">{d.nombre}</span>
          <span className="block text-xs text-tinta-suave">
            {detalleDocumento(d)}, agregado {haceCuanto(d.agregado)}
            {!d.por_significado && !ES_WEB && ', se busca solo por palabras hasta que Ollama calcule sus embeddings'}
          </span>
        </span>
      </button>
      <div className="flex flex-wrap items-center gap-1.5 pl-5 sm:pl-0">
        {cuadernos.length === 0 ? (
          <span className="text-xs text-tinta-tenue">En ningún cuaderno</span>
        ) : (
          cuadernos.map((c) => (
            <a key={c.id} href={enlace({ pagina: 'cuaderno', id: c.id })} className="rounded-sm bg-cita-tinte px-1.5 py-0.5 text-[11px] font-medium text-cita-hondo hover:underline">
              {c.nombre}
            </a>
          ))
        )}
        <Boton variante="fantasma" tamano="icono" onClick={alVer} aria-label={`Ver ${d.nombre}`}>
          <FileText />
        </Boton>
        <Boton
          variante="fantasma"
          tamano="icono"
          onClick={() => abrirOriginal(d)}
          aria-label={`${etiquetaOriginal(d)} de ${d.nombre}`}
        >
          {d.url || d.tipo === 'pdf' ? <ExternalLink /> : <Download />}
        </Boton>
        <Boton variante="fantasma" tamano="icono" className="hover:bg-peligro-tinte hover:text-peligro" onClick={() => setBorrando(true)} aria-label={`Borrar ${d.nombre}`}>
          <Trash2 />
        </Boton>
      </div>
      <Confirmar
        abierto={borrando}
        alCambiar={setBorrando}
        titulo={`¿Borrar «${d.nombre}»?`}
        descripcion={
          cuadernos.length
            ? `Sale de la biblioteca y de ${cuadernos.length === 1 ? 'el cuaderno' : `los ${cuadernos.length} cuadernos`} donde está. El archivo original en tu computador no se toca.`
            : 'Sale de la biblioteca. El archivo original en tu computador no se toca.'
        }
        accion="Borrar documento"
        ocupado={borrar.isPending}
        alConfirmar={() => borrar.mutate()}
      />
    </li>
  )
}
