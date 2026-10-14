// El visor de una fuente: su guía (resumen, temas y preguntas), el pasaje citado con la frase marcada y el texto
// completo del documento.
import * as Tabs from '@radix-ui/react-tabs'
import { useQuery } from '@tanstack/react-query'
import { CircleAlert, Download, ExternalLink, FileText, Lightbulb, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, type Documento } from '../lib/api'
import { CLAVES, useEstado, useRefrescar } from '../lib/consultas'
import { cancelar, claveGuia, escribirGuia, useTrabajos } from '../lib/estudio'
import { abrirOriginal, etiquetaOriginal } from '../lib/original'
import { cn, haceCuanto, ir } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Dialogo, Girando } from '../ui/piezas'
import { BotonPreguntar } from './VistasEstudio'
import { ES_WEB } from '../web/config'

export interface Vista {
  doc_id: string
  documento: string
  tipo?: Documento['tipo'] | null
  pagina?: number | null
  seccion?: string
  /** El HTML del pasaje con la frase marcada, si se abrió desde una cita o un resultado. */
  pasaje?: string
  n?: number
  /** El enlace de la página, si la fuente vino de la web. */
  url?: string
  /** Qué mostrar primero cuando no se abre desde una cita. */
  pestana?: 'guia' | 'documento'
}
export type AbrirVisor = (v: Vista) => void

export function Visor({ vista, alCerrar, alPreguntar }: { vista: Vista | null; alCerrar: () => void; alPreguntar?: (texto: string) => void }) {
  const [pestana, setPestana] = useState('pasaje')
  useEffect(() => setPestana(vista?.pasaje ? 'pasaje' : (vista?.pestana ?? 'guia')), [vista])
  if (!vista) return null
  const lugar = vista.pagina ? `Página ${vista.pagina}` : vista.seccion
  const original = { id: vista.doc_id, tipo: vista.tipo, url: vista.url }
  return (
    <Dialogo
      abierto
      alCambiar={(a) => !a && alCerrar()}
      ancho="max-w-3xl"
      titulo={
        <span className="flex items-center gap-2">
          {vista.n !== undefined && (
            <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-sm bg-cita-tinte px-1.5 text-xs font-semibold text-cita-hondo">
              {vista.n}
            </span>
          )}
          <span className="truncate">{vista.documento}</span>
        </span>
      }
      descripcion={lugar}
    >
      <Tabs.Root value={pestana} onValueChange={setPestana} className="flex min-h-0 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-2">
          <Tabs.List className="flex gap-1" aria-label="Qué mostrar">
            <Pestana valor="guia">Guía</Pestana>
            {vista.pasaje && <Pestana valor="pasaje">Pasaje</Pestana>}
            <Pestana valor="documento">Documento completo</Pestana>
          </Tabs.List>
          <Boton variante="contorno" tamano="sm" onClick={() => abrirOriginal(original, vista.pagina)}>
            {vista.url || vista.tipo === 'pdf' ? <ExternalLink /> : <Download />}
            {etiquetaOriginal(original, vista.pagina)}
          </Boton>
        </div>
        <Tabs.Content value="guia" className="px-5 py-4">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-md border bg-hundida px-3 py-3">
            <p className="text-[13px] text-tinta-suave">Consulta el documento completo sin salir de Tesela.</p>
            <Boton variante="contorno" tamano="sm" onClick={() => setPestana('documento')}>
              <FileText />
              Leer en Tesela
            </Boton>
          </div>
          <GuiaFuente id={vista.doc_id} alPreguntar={alPreguntar} />
        </Tabs.Content>
        {vista.pasaje && (
          <Tabs.Content value="pasaje" className="px-5 py-4">
            <div className="prosa rounded-md bg-extracto px-4 py-3 text-[14.5px] leading-relaxed" dangerouslySetInnerHTML={{ __html: vista.pasaje }} />
            <p className="mt-3 text-xs text-tinta-suave">Lo marcado es lo que se usó en la respuesta o lo que calzó con la búsqueda.</p>
          </Tabs.Content>
        )}
        <Tabs.Content value="documento" className="min-h-[40vh] px-5 py-4">
          <DocumentoCompleto id={vista.doc_id} pagina={vista.pagina} />
        </Tabs.Content>
      </Tabs.Root>
    </Dialogo>
  )
}

function Pestana({ valor, children }: { valor: string; children: string }) {
  return (
    <Tabs.Trigger
      value={valor}
      className={cn(
        'h-8 rounded-md px-3 text-[13px] text-tinta-suave hover:text-tinta',
        'data-[state=active]:bg-hundida data-[state=active]:font-medium data-[state=active]:text-tinta',
      )}
    >
      {children}
    </Tabs.Trigger>
  )
}

function useDocumento(id: string) {
  return useQuery({ queryKey: CLAVES.documento(id), queryFn: () => api.documento(id), retry: false })
}

function GuiaFuente({ id, alPreguntar }: { id: string; alPreguntar?: (texto: string) => void }) {
  const { data, isLoading, isError } = useDocumento(id)
  const { data: estado } = useEstado()
  const trabajo = useTrabajos()[claveGuia(id)]
  const refrescar = useRefrescar()
  const escribir = async () => {
    if (await escribirGuia(id)) await refrescar(CLAVES.documento(id), CLAVES.documentos, ['cuaderno'])
  }
  if (isLoading)
    return (
      <div className="flex justify-center py-10">
        <Girando className="size-5" />
      </div>
    )
  if (isError || !data) return <p className="py-10 text-center text-tinta-suave">Este documento ya no está en la biblioteca.</p>
  const guia = data.guia
  const soloBuscar = estado?.modo === 'buscar'

  if (trabajo && !trabajo.error)
    return (
      <div className="flex items-start gap-3 rounded-md border border-cita/25 bg-cita-tinte px-4 py-3 text-[13px]" role="status">
        <Girando className="mt-0.5 text-cita" />
        <p className="min-w-0 flex-1">
          <span className="block font-medium">Escribiendo la guía</span>
          <span className="text-tinta-suave">{trabajo.paso}</span>
        </p>
        <Boton variante="fantasma" tamano="sm" onClick={() => cancelar(claveGuia(id))}>
          Cancelar
        </Boton>
      </div>
    )

  const error = trabajo?.error && (
    <p className="mb-3 flex items-start gap-2 rounded-md border border-peligro/30 bg-peligro-tinte px-3 py-2 text-[13px]" role="alert">
      <CircleAlert className="mt-0.5 size-4 shrink-0 text-peligro" aria-hidden />
      {trabajo.error}
    </p>
  )

  if (!guia)
    return (
      <div className="mx-auto max-w-md py-6 text-center">
        {error}
        <span className="mx-auto mb-4 flex size-11 items-center justify-center rounded-lg bg-cita-tinte text-cita">
          <Lightbulb className="size-5" aria-hidden />
        </span>
        <p className="font-medium">Todavía no tiene guía</p>
        <p className="mt-1.5 text-[13px] text-tinta-suave">
          El modelo lee el documento y escribe de qué trata, sus temas y preguntas para empezar. En un documento largo, con un modelo
          local, puede tardar unos minutos.
        </p>
        {soloBuscar ? (
          <p className="mt-4 text-[13px] text-tinta-suave">
            Para escribirla hace falta un modelo.{' '}
            <button className="text-cita hover:underline" onClick={() => ir({ pagina: 'ajustes' })}>
              {ES_WEB ? 'Elige una API en Modelos' : 'Elige Ollama o una API en Modelos'}
            </button>
            .
          </p>
        ) : (
          <Boton variante="principal" className="mt-4" onClick={() => void escribir()}>
            <Lightbulb />
            Escribir la guía
          </Boton>
        )}
      </div>
    )

  return (
    <div className="space-y-5">
      {error}
      <section>
        <h3 className="mb-1.5 text-xs font-medium text-tinta-suave">Resumen</h3>
        <p className="max-w-[68ch] text-[14.5px] leading-relaxed">{guia.resumen}</p>
      </section>
      {guia.temas.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-medium text-tinta-suave">Temas</h3>
          <ul className="flex flex-wrap gap-1.5">
            {guia.temas.map((t) => (
              <li key={t}>
                {alPreguntar ? (
                  <button
                    onClick={() => alPreguntar(`Explícame «${t}» según las fuentes.`)}
                    className="rounded-full border border-cita/30 bg-cita-tinte px-3 py-1 text-[13px] text-cita-hondo transition-colors hover:border-cita"
                  >
                    {t}
                  </button>
                ) : (
                  <span className="inline-block rounded-full border bg-hundida px-3 py-1 text-[13px]">{t}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {guia.preguntas.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-medium text-tinta-suave">Preguntas para empezar</h3>
          {alPreguntar ? (
            <div className="grid gap-1.5">
              {guia.preguntas.map((p) => (
                <BotonPreguntar key={p} texto={p} alPreguntar={alPreguntar} />
              ))}
            </div>
          ) : (
            <ul className="list-disc space-y-1 pl-5 text-[13.5px]">
              {guia.preguntas.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
        </section>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3 text-xs text-tinta-suave">
        <span>
          Escrita por {guia.modelo} {haceCuanto(guia.creada)}
          {guia.leido < 1 && `; leyó un ${Math.round(guia.leido * 100)} % del texto, en partes repartidas`}.
        </span>
        {!soloBuscar && (
          <Boton variante="fantasma" tamano="sm" onClick={() => void escribir()}>
            <RotateCcw />
            Volver a escribir
          </Boton>
        )}
      </div>
    </div>
  )
}

function DocumentoCompleto({ id, pagina }: { id: string; pagina?: number | null }) {
  const { data, isLoading, isError } = useDocumento(id)
  const caja = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (data && pagina) caja.current?.querySelector(`#pagina-${pagina}`)?.scrollIntoView({ block: 'start' })
  }, [data, pagina])
  if (isLoading)
    return (
      <div className="flex justify-center py-10">
        <Girando className="size-5" />
      </div>
    )
  if (isError || !data) return <p className="py-10 text-center text-tinta-suave">Este documento ya no está en la biblioteca.</p>
  // los títulos «Página N» del texto de un PDF llevan un id, para saltar a la página de la cita
  const html = data.html.replace(/<h4>Página (\d+)<\/h4>/g, '<h4 id="pagina-$1">Página $1</h4>')
  return <div ref={caja} className="prosa max-w-[72ch] text-[14.5px] leading-relaxed" dangerouslySetInnerHTML={{ __html: html }} />
}
