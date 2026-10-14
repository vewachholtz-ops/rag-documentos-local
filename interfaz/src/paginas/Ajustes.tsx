// Con qué responde Tesela: solo buscar, Ollama o una API compatible con OpenAI.
import { useMutation } from '@tanstack/react-query'
import { Cloud, Cpu, Download, Search, ShieldAlert } from 'lucide-react'
import { type ElementType, type FormEvent, type ReactNode, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { api, type Ajustes, type Estado, type Modo } from '../lib/api'
import { CLAVES, useAjustes, useEstado, useRefrescar } from '../lib/consultas'
import { descargar, useDescargas } from '../lib/descargas'
import { cn } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Barra, Campo, Etiqueta, Girando } from '../ui/piezas'
import { ES_WEB, URL_INSTALAR } from '../web/config'

const OPCIONES: { modo: Modo; titulo: string; icono: ElementType; texto: string }[] = [
  {
    modo: 'ollama',
    titulo: 'Ollama, en este computador',
    icono: Cpu,
    texto: 'La IA redacta respuestas con citas comprobadas. Nada sale del computador. Necesita Ollama y unos 14 GB de modelos.',
  },
  {
    modo: 'openai',
    titulo: 'API compatible con OpenAI',
    icono: Cloud,
    texto: ES_WEB
      ? 'La IA redacta respuestas con citas comprobadas, con un modelo de OpenAI, Groq, OpenRouter o LM Studio. La pregunta y los pasajes elegidos salen a ese servicio.'
      : 'Lo mismo, con un modelo de OpenAI, Groq, OpenRouter o LM Studio. Para computadores que no pueden correr un modelo local.',
  },
  {
    modo: 'buscar',
    titulo: 'Solo buscar',
    icono: Search,
    texto: 'Sin IA: muestra los pasajes de tus documentos que más calzan con lo que escribes, con las palabras marcadas.',
  },
]

const SERVICIOS = [
  { nombre: 'OpenAI', url: 'https://api.openai.com/v1' },
  { nombre: 'Groq', url: 'https://api.groq.com/openai/v1' },
  { nombre: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { nombre: 'LM Studio', url: 'http://localhost:1234/v1' },
]

type Cambios = { modo?: Modo; modelo?: string; a_fondo?: boolean }

export function PaginaAjustes() {
  const { data: ajustes } = useAjustes()
  const { data: estado } = useEstado()
  const refrescar = useRefrescar()
  // lo elegido se ve al tiro (un radio controlado que espera al servidor rebota); si el servidor no lo acepta,
  // vuelve a lo guardado
  const [elegido, setElegido] = useState<Cambios>({})
  const cambiar = useMutation({
    mutationFn: (cambios: Cambios) => api.cambiarAjustes(cambios),
    onError: (e) => toast.error(e.message),
    onSettled: async () => {
      await refrescar(CLAVES.ajustes, CLAVES.estado)
      setElegido({})
    },
  })
  const elegir = (cambios: Cambios) => {
    setElegido((x) => ({ ...x, ...cambios }))
    cambiar.mutate(cambios)
  }

  if (!ajustes || !estado)
    return (
      <div className="flex flex-1 items-center justify-center">
        <Girando className="size-6" />
      </div>
    )

  const vista: Ajustes = { ...ajustes, ...elegido }
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-8 p-4 sm:p-6">
        <h1 className="font-display text-2xl font-bold tracking-tight">Modelos</h1>

        <Seccion titulo="Con qué responde" texto="La búsqueda en tus documentos es siempre local. Esto elige quién redacta la respuesta.">
          <fieldset className="grid gap-2">
            <legend className="sr-only">Con qué responde</legend>
            {OPCIONES.filter((o) => !(ES_WEB && o.modo === 'ollama')).map((o) => {
              const elegida = vista.modo === o.modo
              return (
                <label
                  key={o.modo}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors',
                    elegida ? 'border-acento bg-acento-tinte/50 shadow-[0_0_0_1px_var(--acento)]' : 'bg-superficie hover:bg-elevada',
                  )}
                >
                  <input
                    type="radio"
                    name="modo"
                    value={o.modo}
                    checked={elegida}
                    onChange={() => elegir({ modo: o.modo })}
                    className="mt-1 accent-[var(--acento)]"
                  />
                  <o.icono className={cn('mt-0.5 size-5 shrink-0', elegida ? 'text-acento' : 'text-tinta-tenue')} aria-hidden />
                  <span>
                    <span className="block font-medium">{o.titulo}</span>
                    <span className="mt-0.5 block text-[13px] text-tinta-suave">{o.texto}</span>
                  </span>
                </label>
              )
            })}
          </fieldset>
        </Seccion>

        {vista.modo === 'ollama' && <AjustesOllama ajustes={vista} estado={estado} alCambiar={elegir} />}
        {vista.modo === 'openai' && <AjustesApi ajustes={vista} />}

        {vista.modo !== 'buscar' && (
          <Seccion titulo="Búsqueda a fondo">
            <label className="flex cursor-pointer items-start gap-3 rounded-lg border bg-superficie p-4">
              <input
                type="checkbox"
                checked={vista.a_fondo}
                onChange={(e) => elegir({ a_fondo: e.target.checked })}
                className="mt-1 accent-[var(--acento)]"
              />
              <span>
                <span className="block font-medium">Reformular la pregunta y reordenar los pasajes con el modelo</span>
                <span className="mt-0.5 block text-[13px] text-tinta-suave">
                  En la evaluación, la sección correcta quedó primera en el 98 % de las preguntas, frente al 68 % sin esto. Cada
                  respuesta tarda unos 20 segundos más con un modelo local.
                </span>
              </span>
            </label>
          </Seccion>
        )}

        <Seccion titulo="Tus datos">
          {ES_WEB ? (
            <p className="text-[13.5px] text-tinta-suave">
              Los documentos, cuadernos, notas y ajustes quedan guardados en este navegador, en este computador: no se suben a
              ningún servidor. Si borras los datos del sitio en el navegador, se pierden. Para usar una IA en tu computador
              (Ollama), conectar carpetas o traer páginas web,{' '}
              <a href={URL_INSTALAR} target="_blank" rel="noreferrer" className="text-acento hover:underline">
                instala Tesela
              </a>
              .
            </p>
          ) : (
            <p className="text-[13.5px] text-tinta-suave">
              Los documentos, cuadernos, notas y ajustes quedan en la carpeta <code className="rounded-sm bg-hundida px-1">biblioteca</code>{' '}
              dentro de la carpeta de Tesela. Borrar un documento aquí no toca el archivo original.
            </p>
          )}
        </Seccion>
      </div>
    </div>
  )
}

function Seccion({ titulo, texto, children }: { titulo: string; texto?: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="font-display text-lg font-semibold">{titulo}</h2>
      {texto && <p className="mt-0.5 mb-3 text-[13px] text-tinta-suave">{texto}</p>}
      <div className={texto ? '' : 'mt-3'}>{children}</div>
    </section>
  )
}

function AjustesOllama({ ajustes, estado, alCambiar }: { ajustes: Ajustes; estado: Estado; alCambiar: (c: { modelo: string }) => void }) {
  const descargas = useDescargas()
  const refrescar = useRefrescar()
  const modelos = Array.from(new Set([ajustes.modelo, ...estado.modelos]))
  return (
    <Seccion titulo="Ollama">
      <div className="space-y-4 rounded-lg border bg-superficie p-4">
        <p className="flex items-center gap-2 text-[13.5px]">
          <span className={cn('size-2 rounded-full', estado.ollama ? 'bg-acento' : 'bg-aviso')} aria-hidden />
          {estado.ollama ? 'Ollama está abierto.' : 'Ollama está cerrado o no está instalado.'}
          {!estado.ollama && (
            <a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer" className="text-cita hover:underline">
              Descargar Ollama
            </a>
          )}
        </p>
        <div>
          <Etiqueta htmlFor="modelo-ollama">Modelo que responde</Etiqueta>
          <select
            id="modelo-ollama"
            value={ajustes.modelo}
            onChange={(e) => alCambiar({ modelo: e.target.value })}
            className="h-9 w-full rounded-md border bg-elevada px-2.5 text-sm sm:w-80"
          >
            {modelos.map((m) => (
              <option key={m} value={m}>
                {m}
                {!estado.modelos.includes(m) ? ' (sin descargar)' : ''}
              </option>
            ))}
          </select>
          <p className="mt-1.5 text-xs text-tinta-suave">
            El motor se evaluó con gpt-oss:20b. Otro modelo puede citar peor; la comprobación de citas lo avisa.
          </p>
        </div>
        {estado.faltan.length > 0 && estado.ollama && (
          <div className="space-y-2 border-t pt-4">
            <p className="text-[13.5px] font-medium">Falta descargar</p>
            {estado.faltan.map((m) => {
              const d = descargas[m]
              return d && !d.error ? (
                <div key={m} className="space-y-1">
                  <p className="text-xs text-tinta-suave">
                    {m}: {d.total ? `${Math.round((d.hecho / d.total) * 100)} %` : d.estado || 'empezando'}
                  </p>
                  <Barra valor={d.total ? d.hecho / d.total : 0} />
                </div>
              ) : (
                <div key={m} className="flex flex-wrap items-center gap-2">
                  <Boton tamano="sm" variante="principal" onClick={() => descargar(m, () => refrescar(CLAVES.estado))}>
                    <Download />
                    Descargar {m}
                  </Boton>
                  {d?.error && <span className="text-xs text-peligro">{d.error}</span>}
                </div>
              )
            })}
          </div>
        )}
        <p className="border-t pt-4 text-xs text-tinta-suave">
          Embeddings: {estado.embeddings}{' '}
          {estado.busqueda_por_significado ? '(listo: se busca por significado y por palabras)' : '(sin descargar: se busca solo por palabras)'}
        </p>
      </div>
    </Seccion>
  )
}

function AjustesApi({ ajustes }: { ajustes: Ajustes }) {
  const [url, setUrl] = useState(ajustes.openai.url)
  const [modelo, setModelo] = useState(ajustes.openai.modelo)
  const [clave, setClave] = useState('')
  const refrescar = useRefrescar()
  useEffect(() => {
    setUrl(ajustes.openai.url)
    setModelo(ajustes.openai.modelo)
  }, [ajustes.openai.url, ajustes.openai.modelo])
  const guardar = useMutation({
    mutationFn: () => api.cambiarAjustes({ openai: { url, modelo, ...(clave ? { clave } : {}) } }),
    onSuccess: () => {
      setClave('')
      toast.success('Guardado')
      refrescar(CLAVES.ajustes, CLAVES.estado)
    },
    onError: (e) => toast.error(e.message),
  })
  const quitarClave = useMutation({
    mutationFn: () => api.cambiarAjustes({ openai: { clave: '' } }),
    onSuccess: () => refrescar(CLAVES.ajustes),
  })
  let anfitrion = ''
  try {
    anfitrion = url ? new URL(url).host : ''
  } catch {
    anfitrion = ''
  }
  const local = /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(anfitrion)
  const enviar = (e: FormEvent) => {
    e.preventDefault()
    guardar.mutate()
  }
  return (
    <Seccion titulo="API compatible con OpenAI">
      <form onSubmit={enviar} className="space-y-4 rounded-lg border bg-superficie p-4">
        <div>
          <Etiqueta htmlFor="url-api">Dirección</Etiqueta>
          <Campo id="url-api" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://api.openai.com/v1" inputMode="url" />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {SERVICIOS.map((s) => (
              <button
                key={s.nombre}
                type="button"
                onClick={() => setUrl(s.url)}
                className={cn('rounded-sm border px-2 py-0.5 text-xs hover:bg-hundida', url === s.url && 'border-acento bg-acento-tinte')}
              >
                {s.nombre}
              </button>
            ))}
          </div>
        </div>
        <div>
          <Etiqueta htmlFor="modelo-api">Modelo</Etiqueta>
          <Campo id="modelo-api" value={modelo} onChange={(e) => setModelo(e.target.value)} placeholder="Por ejemplo: gpt-4.1-mini" />
        </div>
        <div>
          <Etiqueta htmlFor="clave-api">Clave</Etiqueta>
          <Campo
            id="clave-api"
            type="password"
            autoComplete="off"
            value={clave}
            onChange={(e) => setClave(e.target.value)}
            placeholder={ajustes.openai.hay_clave ? 'Guardada. Escribe otra para cambiarla' : 'sk-…'}
          />
          <p className="mt-1.5 text-xs text-tinta-suave">
            {ES_WEB ? 'Queda guardada en este navegador' : 'Queda en este computador (biblioteca/ajustes-secretos.json)'} y la app no la vuelve a mostrar.{' '}
            {ajustes.openai.hay_clave && (
              <button type="button" onClick={() => quitarClave.mutate()} className="text-peligro hover:underline">
                Borrar la clave guardada
              </button>
            )}
          </p>
        </div>
        {anfitrion && !local && (
          <p className="flex gap-2 rounded-md border border-aviso/30 bg-aviso-tinte p-3 text-[13px]">
            <ShieldAlert className="mt-0.5 size-4 shrink-0 text-aviso" aria-hidden />
            <span>
              Con este modo, cada pregunta y los pasajes elegidos para responderla se envían a <strong>{anfitrion}</strong>. Los
              documentos completos no salen {ES_WEB ? 'del navegador' : 'del computador'}.
            </span>
          </p>
        )}
        <div className="flex justify-end">
          <Boton type="submit" variante="principal" disabled={guardar.isPending}>
            {guardar.isPending && <Girando className="text-sobre-primario" />}
            Guardar
          </Boton>
        </div>
      </form>
    </Seccion>
  )
}
