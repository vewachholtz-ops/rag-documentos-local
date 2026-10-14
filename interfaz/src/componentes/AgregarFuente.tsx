// Agregar fuentes: pestañas por tipo (subir archivos, un enlace o pegar texto) y
// el cuaderno donde queda. El avance se ve en el mismo diálogo.
import * as Tabs from '@radix-ui/react-tabs'
import { CircleAlert, FileText, Globe, Type, Upload } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { TIPOS_ACEPTADOS } from '../lib/api'
import { useCuadernos } from '../lib/consultas'
import { useSubidas } from '../lib/subidas'
import { cn } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Barra, Campo, Dialogo, Etiqueta, Girando, Texto } from '../ui/piezas'
import { ES_WEB } from '../web/config'

export function DialogoAgregarFuente({
  abierto,
  alCambiar,
  cuaderno: inicial = '',
  tipoInicial = 'archivo',
}: {
  abierto: boolean
  alCambiar: (a: boolean) => void
  cuaderno?: string
  tipoInicial?: 'archivo' | 'texto' | 'enlace'
}) {
  const { data: cuadernos } = useCuadernos()
  const [cuaderno, setCuaderno] = useState(inicial)
  const [tipo, setTipo] = useState('archivo')
  const [titulo, setTitulo] = useState('')
  const [texto, setTexto] = useState('')
  const [url, setUrl] = useState('')
  const [encima, setEncima] = useState(false)
  const selector = useRef<HTMLInputElement>(null)
  const { subidas, agregar, agregarEnlace, descartar } = useSubidas(cuaderno || null, true)
  useEffect(() => {
    if (!abierto) return
    setCuaderno(inicial)
    setTipo(tipoInicial)
  }, [abierto, inicial, tipoInicial])

  const pegar = (e: FormEvent) => {
    e.preventDefault()
    if (!texto.trim()) return
    const nombre = `${(titulo.trim() || texto.trim().split('\n')[0]).slice(0, 80).replace(/[\\/:*?"<>|]/g, '')}.md`
    agregar([new File([titulo.trim() ? `# ${titulo.trim()}\n\n${texto}` : texto], nombre, { type: 'text/markdown' })])
    setTitulo('')
    setTexto('')
  }

  const traer = (e: FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    agregarEnlace(url.trim())
    setUrl('')
  }

  return (
    <Dialogo
      abierto={abierto}
      alCambiar={alCambiar}
      titulo="Agregar fuente"
      descripcion={`Se lee, se divide en trozos y queda lista para buscar y preguntar. Todo queda en este ${ES_WEB ? 'navegador' : 'computador'}.`}
      ancho="max-w-xl"
    >
      <div className="space-y-5 p-5">
        <Tabs.Root value={tipo} onValueChange={setTipo}>
          <Tabs.List className={cn('grid w-full rounded-md bg-hundida p-1', ES_WEB ? 'grid-cols-2' : 'grid-cols-3')} aria-label="Tipo de fuente">
            {[
              { valor: 'archivo', nombre: 'Subir archivos', icono: Upload },
              // la versión web no puede pedirle páginas a otros sitios
              ...(ES_WEB ? [] : [{ valor: 'enlace', nombre: 'Enlace', icono: Globe }]),
              { valor: 'texto', nombre: 'Pegar texto', icono: Type },
            ].map((t) => (
              <Tabs.Trigger
                key={t.valor}
                value={t.valor}
                className="flex h-8 items-center justify-center gap-2 rounded-sm text-[13px] text-tinta-suave data-[state=active]:bg-superficie data-[state=active]:font-medium data-[state=active]:text-tinta data-[state=active]:shadow-[0_0_0_1px_var(--linea)]"
              >
                <t.icono className="size-4" aria-hidden />
                {t.nombre}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
          <Tabs.Content value="archivo" className="mt-4">
            <input
              ref={selector}
              type="file"
              multiple
              accept={TIPOS_ACEPTADOS}
              className="hidden"
              data-prueba="elegir-archivos-dialogo"
              onChange={(e) => {
                if (e.target.files?.length) agregar(e.target.files)
                e.target.value = ''
              }}
            />
            <button
              type="button"
              onClick={() => selector.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setEncima(true)
              }}
              onDragLeave={() => setEncima(false)}
              onDrop={(e) => {
                e.preventDefault()
                setEncima(false)
                if (e.dataTransfer.files.length) agregar(e.dataTransfer.files)
              }}
              className={cn(
                'flex w-full flex-col items-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors',
                encima ? 'border-cita bg-cita-tinte' : 'hover:bg-hundida',
              )}
            >
              <Upload className="mb-2 size-8 text-tinta-tenue" aria-hidden />
              <span className="font-medium">Arrastra los archivos aquí o elige desde el computador</span>
              <span className="mt-1 text-[13px] text-tinta-suave">PDF, Word, PowerPoint, Excel, CSV, HTML, Markdown o texto, de hasta 30 MB</span>
            </button>
          </Tabs.Content>
          <Tabs.Content value="enlace" className="mt-4">
            <form onSubmit={traer} className="space-y-3">
              <div>
                <Etiqueta htmlFor="enlace-fuente">Enlace de la página</Etiqueta>
                <Campo
                  id="enlace-fuente"
                  inputMode="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://"
                  spellCheck={false}
                  autoFocus
                />
                <p className="mt-1.5 text-xs text-tinta-suave">
                  Tesela descarga la página una vez y guarda su texto, sin menús ni publicidad. Sirve para artículos, documentación y PDF
                  publicados; las páginas que piden iniciar sesión no se pueden leer.
                </p>
              </div>
              <div className="flex justify-end">
                <Boton type="submit" variante="principal" disabled={!url.trim()}>
                  <Globe />
                  Agregar página
                </Boton>
              </div>
            </form>
          </Tabs.Content>
          <Tabs.Content value="texto" className="mt-4">
            <form onSubmit={pegar} className="space-y-3">
              <div>
                <Etiqueta htmlFor="titulo-texto">Título (opcional)</Etiqueta>
                <Campo id="titulo-texto" value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={80} placeholder="Por ejemplo: Correo del proveedor" />
              </div>
              <div>
                <Etiqueta htmlFor="contenido-texto">Texto</Etiqueta>
                <Texto id="contenido-texto" value={texto} onChange={(e) => setTexto(e.target.value)} rows={7} placeholder="Pega aquí el texto" />
              </div>
              <div className="flex justify-end">
                <Boton type="submit" variante="principal" disabled={!texto.trim()}>
                  <FileText />
                  Agregar texto
                </Boton>
              </div>
            </form>
          </Tabs.Content>
        </Tabs.Root>

        <div>
          <Etiqueta htmlFor="cuaderno-fuente">Cuaderno</Etiqueta>
          <select
            id="cuaderno-fuente"
            value={cuaderno}
            onChange={(e) => setCuaderno(e.target.value)}
            className="h-9 w-full rounded-md border bg-elevada px-2.5 text-sm"
          >
            <option value="">Ninguno: solo a la biblioteca</option>
            {(cuadernos ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
          </select>
        </div>

        {subidas.length > 0 && (
          <ul className="space-y-2" aria-label="Avance">
            {subidas.map((s) => (
              <li key={s.clave} className={cn('rounded-md border p-3', s.error ? 'border-peligro/40 bg-peligro-tinte' : 'bg-superficie')}>
                <div className="flex items-start gap-2 text-[13px]">
                  {s.error ? <CircleAlert className="mt-0.5 size-4 shrink-0 text-peligro" aria-hidden /> : <Girando className="mt-0.5 shrink-0" />}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{s.nombre}</span>
                    <span className={cn('block text-xs', s.error ? 'text-peligro' : 'text-tinta-suave')}>{s.error ?? s.paso}</span>
                  </span>
                  {s.error && (
                    <button onClick={() => descartar(s.clave)} className="text-xs text-tinta-suave hover:underline">
                      Cerrar
                    </button>
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
      </div>
    </Dialogo>
  )
}
