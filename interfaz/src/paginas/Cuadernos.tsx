import { useMutation } from '@tanstack/react-query'
import { Book, FileText, MoreHorizontal, Plus, Search, ShieldCheck, StickyNote, Trash2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { toast } from 'sonner'
import { api, type ResumenCuaderno } from '../lib/api'
import { CLAVES, useCuadernos, useRefrescar } from '../lib/consultas'
import { cn, enlace, haceCuanto, ir, plural } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Campo, Confirmar, Dialogo, Etiqueta, Girando, MenuContenido, MenuDisparador, MenuItem, MenuRaiz, Texto } from '../ui/piezas'
import { ES_WEB, URL_INSTALAR } from '../web/config'

export function PaginaCuadernos() {
  const { data: cuadernos, isLoading } = useCuadernos()
  const [filtro, setFiltro] = useState('')
  const [creando, setCreando] = useState(false)
  const visibles = (cuadernos ?? []).filter((c) =>
    `${c.nombre} ${c.descripcion}`.toLowerCase().includes(filtro.trim().toLowerCase()),
  )

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mesa-cuadernos space-y-7 p-5 sm:p-8 lg:p-10">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="mb-1 text-xs text-tinta-suave">Tu espacio documental</p><h1 className="font-display text-[28px] font-semibold tracking-tight">Cuadernos</h1></div>
          {!!cuadernos?.length && (
            <div className="flex gap-2">
              <div className="relative flex-1 sm:w-64 sm:flex-none">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-tinta-tenue" />
                <Campo
                  value={filtro}
                  onChange={(e) => setFiltro(e.target.value)}
                  placeholder="Buscar cuadernos"
                  aria-label="Buscar cuadernos"
                  className="pl-8"
                />
              </div>
              <Boton variante="principal" onClick={() => setCreando(true)}>
                <Plus />
                Nuevo cuaderno
              </Boton>
            </div>
          )}
        </div>

        {ES_WEB && <AvisoWeb />}

        {isLoading ? (
          <div className="flex justify-center py-16">
            <Girando className="size-6" />
          </div>
        ) : !cuadernos?.length ? (
          <Bienvenida alCrear={() => setCreando(true)} />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visibles.map((c) => (
              <TarjetaCuaderno key={c.id} cuaderno={c} />
            ))}
            {!visibles.length && <p className="text-tinta-suave">Ningún cuaderno se llama así.</p>}
          </div>
        )}
      </div>
      <DialogoNuevoCuaderno abierto={creando} alCambiar={setCreando} />
    </div>
  )
}

/** En la versión web: dónde quedan los documentos y qué trae la app instalada. */
function AvisoWeb() {
  return (
    <p className="flex gap-2.5 rounded-lg border bg-superficie px-4 py-3 text-[13px] leading-relaxed text-tinta-suave">
      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-acento" aria-hidden />
      <span>
        <strong className="font-medium text-tinta">Versión web.</strong> Tus documentos quedan guardados en este navegador y no se
        suben a ningún lado. Busca pasajes sin IA, o responde con la API que elijas en Modelos.{' '}
        <a href={URL_INSTALAR} target="_blank" rel="noreferrer" className="text-acento hover:underline">
          Instala Tesela
        </a>{' '}
        para usar una IA en tu computador, conectar carpetas y traer páginas web.
      </span>
    </p>
  )
}

/** Primer uso: acción concreta y una ilustración propia, sin datos ni respuestas precargadas. */
function Bienvenida({ alCrear }: { alCrear: () => void }) {
  return (
    <section className="grid overflow-hidden rounded-lg border bg-superficie lg:grid-cols-[1.3fr_1fr]">
      <div className="px-6 py-10 sm:px-10 sm:py-14">
        <span className="mb-6 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs text-tinta-suave"><Book className="size-3.5" aria-hidden /> Un tema, un cuaderno</span>
        <h2 className="max-w-sm font-display text-3xl leading-[1.15] font-semibold tracking-tight sm:text-4xl">
          Pregúntale a tus documentos
        </h2>
        <p className="mt-3 text-[15px] text-tinta-suave">
          Reúne archivos, encuentra el pasaje que necesitas y guarda lo que descubres. Elige si quieres buscar o conversar con una IA.
        </p>
        <Boton variante="principal" className="mt-6" onClick={alCrear}>
          <Plus />
          Crear el primer cuaderno
        </Boton>
        <p className="mt-5 text-xs text-tinta-suave">{ES_WEB ? 'PDF, Word, PowerPoint, Excel y texto' : 'PDF, Word, PowerPoint, Excel, páginas web y texto'}</p>
      </div>
      <div className="mesa-empty-art hidden items-center justify-center border-l p-10 lg:flex" aria-hidden>
        <svg viewBox="0 0 280 260" className="w-full max-w-72" fill="none">
          <rect x="42" y="36" width="174" height="194" rx="12" fill="var(--fondo-hondo)" stroke="var(--linea)" transform="rotate(-9 129 133)" />
          <rect x="64" y="30" width="172" height="194" rx="12" fill="var(--superficie)" stroke="var(--linea)" />
          <rect x="85" y="53" width="34" height="38" rx="5" fill="var(--cita-tinte)" />
          <path d="M95 64h14m-14 6h14m-14 6h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          <path d="M134 61h75m-75 10h51M85 112h128m-128 12h128m-128 12h82" stroke="var(--linea)" strokeWidth="5" strokeLinecap="round" />
          <rect x="81" y="152" width="132" height="22" rx="4" fill="var(--cita-tinte)" />
          <path d="M89 163h112" stroke="currentColor" strokeWidth="3" strokeLinecap="round" opacity=".6" />
          <rect x="24" y="185" width="174" height="48" rx="9" fill="var(--primario)" />
          <path d="m44 206 5 5 9-11m15 3h103m-103 10h69" stroke="var(--sobre-primario)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </section>
  )
}

function TarjetaCuaderno({ cuaderno: c }: { cuaderno: ResumenCuaderno }) {
  const [borrando, setBorrando] = useState(false)
  const refrescar = useRefrescar()
  const borrar = useMutation({
    mutationFn: () => api.borrarCuaderno(c.id),
    onSuccess: () => {
      setBorrando(false)
      toast.success(`Borraste «${c.nombre}»`)
      refrescar(CLAVES.cuadernos, CLAVES.estado, CLAVES.documentos)
    },
    onError: (e) => toast.error(e.message),
  })
  return (
    <article className="group relative flex flex-col overflow-hidden rounded-lg border bg-superficie transition-colors hover:border-cita/60 hover:bg-elevada">
      <a href={enlace({ pagina: 'cuaderno', id: c.id })} className="flex flex-1 flex-col p-6">
        <span aria-hidden className="mb-5 flex size-10 items-center justify-center rounded-lg bg-cita-tinte text-cita"><Book className="size-5" /></span>
        <h2 className="truncate pr-8 font-display text-base font-semibold">{c.nombre}</h2>
        <p className={cn('mt-1 line-clamp-2 pr-4 text-[13px]', c.descripcion ? 'text-tinta-suave' : 'text-tinta-tenue')}>
          {c.descripcion || 'Sin descripción'}
        </p>
        <p className="mt-auto pt-5 text-xs text-tinta-tenue">Modificado {haceCuanto(c.actualizado)}</p>
        <div className="mt-3 flex items-center gap-4 border-t pt-3 text-xs text-tinta-suave">
          <span className="flex items-center gap-1.5">
            <FileText className="size-3.5" aria-hidden />
            {plural(c.fuentes, 'fuente', 'fuentes')}
          </span>
          <span className="flex items-center gap-1.5">
            <StickyNote className="size-3.5" aria-hidden />
            {plural(c.notas, 'nota', 'notas')}
          </span>
        </div>
      </a>
      <MenuRaiz>
        <MenuDisparador asChild>
          <Boton
            variante="fantasma"
            tamano="icono"
            className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
            aria-label={`Opciones de ${c.nombre}`}
          >
            <MoreHorizontal />
          </Boton>
        </MenuDisparador>
        <MenuContenido>
          <MenuItem icono={Trash2} peligro onSelect={() => setBorrando(true)}>
            Borrar cuaderno
          </MenuItem>
        </MenuContenido>
      </MenuRaiz>
      <Confirmar
        abierto={borrando}
        alCambiar={setBorrando}
        titulo={`¿Borrar «${c.nombre}»?`}
        descripcion="Se borran sus notas y la conversación. Los documentos quedan en la biblioteca."
        accion="Borrar cuaderno"
        ocupado={borrar.isPending}
        alConfirmar={() => borrar.mutate()}
      />
    </article>
  )
}

export function DialogoNuevoCuaderno({ abierto, alCambiar }: { abierto: boolean; alCambiar: (a: boolean) => void }) {
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const refrescar = useRefrescar()
  const crear = useMutation({
    mutationFn: () => api.crearCuaderno(nombre, descripcion),
    onSuccess: (c) => {
      refrescar(CLAVES.cuadernos, CLAVES.estado)
      alCambiar(false)
      setNombre('')
      setDescripcion('')
      ir({ pagina: 'cuaderno', id: c.id })
    },
    onError: (e) => toast.error(e.message),
  })
  const enviar = (e: FormEvent) => {
    e.preventDefault()
    if (nombre.trim()) crear.mutate()
  }
  return (
    <Dialogo abierto={abierto} alCambiar={alCambiar} titulo="Nuevo cuaderno" descripcion="Un tema, con sus documentos y sus notas.">
      <form onSubmit={enviar} className="space-y-4 p-5">
        <div>
          <Etiqueta htmlFor="nombre-cuaderno">Nombre</Etiqueta>
          <Campo
            id="nombre-cuaderno"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Por ejemplo: Contratos de arriendo"
            maxLength={120}
            autoFocus
          />
        </div>
        <div>
          <Etiqueta htmlFor="descripcion-cuaderno">Descripción (opcional)</Etiqueta>
          <Texto
            id="descripcion-cuaderno"
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="Para qué es o qué tiene"
          />
        </div>
        <div className="flex justify-end gap-2">
          <Boton variante="contorno" onClick={() => alCambiar(false)}>
            Cancelar
          </Boton>
          <Boton type="submit" variante="principal" disabled={!nombre.trim() || crear.isPending}>
            {crear.isPending ? <Girando className="text-sobre-primario" /> : <Book />}
            Crear cuaderno
          </Boton>
        </div>
      </form>
    </Dialogo>
  )
}
