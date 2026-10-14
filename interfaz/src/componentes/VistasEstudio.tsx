// Cómo se ven las notas de Estudio que no son solo texto: el mapa de ideas, las tarjetas y el cuestionario.
import { Check, ChevronLeft, ChevronRight, MessageSquare, RotateCcw, Shuffle, X } from 'lucide-react'
import { type KeyboardEvent, useMemo, useState } from 'react'
import { contarNodos, type Nodo, type Pregunta, type Tarjeta } from '../lib/formatos'
import { cn } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Ayuda } from '../ui/piezas'

// ---- mapa de ideas ----
function ids(n: Nodo, hasta: number, nivel = 0, salida = new Set<string>()) {
  if (nivel < hasta && n.hijos.length) {
    salida.add(n.id)
    n.hijos.forEach((h) => ids(h, hasta, nivel + 1, salida))
  }
  return salida
}

export function MapaIdeas({ raiz, alPreguntar }: { raiz: Nodo; alPreguntar?: (texto: string) => void }) {
  // un mapa chico se ve entero; uno grande parte mostrando solo los temas principales
  const inicial = useMemo(() => ids(raiz, contarNodos(raiz) <= 24 ? 99 : 1), [raiz])
  const [abiertos, setAbiertos] = useState(inicial)
  const alternar = (id: string) =>
    setAbiertos((a) => {
      const b = new Set(a)
      if (b.has(id)) b.delete(id)
      else b.add(id)
      return b
    })
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-tinta-suave">
          {alPreguntar ? 'Toca una idea para preguntar por ella en el chat. Las flechas abren y cierran las ramas.' : 'Las flechas abren y cierran las ramas.'}
        </p>
        <div className="flex gap-1">
          <Boton variante="fantasma" tamano="sm" onClick={() => setAbiertos(ids(raiz, 99))}>
            Abrir todo
          </Boton>
          <Boton variante="fantasma" tamano="sm" onClick={() => setAbiertos(new Set([raiz.id]))}>
            Cerrar
          </Boton>
        </div>
      </div>
      <div className="mapa overflow-auto rounded-lg border p-5" role="tree" aria-label={`Mapa de ideas: ${raiz.texto}`}>
        <Rama nodo={raiz} nivel={0} abiertos={abiertos} alAlternar={alternar} alPreguntar={alPreguntar} />
      </div>
    </div>
  )
}

function Rama({
  nodo,
  nivel,
  abiertos,
  alAlternar,
  alPreguntar,
}: {
  nodo: Nodo
  nivel: number
  abiertos: Set<string>
  alAlternar: (id: string) => void
  alPreguntar?: (texto: string) => void
}) {
  const abierto = abiertos.has(nodo.id)
  const estilo =
    nivel === 0
      ? 'bg-cita text-sobre-primario border-cita font-semibold text-[14px] px-4 py-2'
      : nivel === 1
        ? 'bg-cita-tinte text-cita-hondo border-cita/30 font-medium'
        : 'bg-superficie text-tinta'
  const etiqueta = (
    <span className={cn('block max-w-56 rounded-md border px-3 py-1.5 text-left text-[13px] leading-snug', estilo)}>{nodo.texto}</span>
  )
  return (
    <div className="mapa-rama" role="treeitem" aria-expanded={nodo.hijos.length ? abierto : undefined} aria-label={nodo.texto}>
      <div className="flex shrink-0 items-center">
        {alPreguntar ? (
          <Ayuda texto="Preguntar por esto en el chat">
            <button onClick={() => alPreguntar(nodo.texto)} className="rounded-md transition-transform hover:-translate-y-px focus-visible:outline-offset-2">
              {etiqueta}
            </button>
          </Ayuda>
        ) : (
          etiqueta
        )}
        {nodo.hijos.length > 0 && (
          <button
            onClick={() => alAlternar(nodo.id)}
            className="-ml-1.5 flex size-6 shrink-0 items-center justify-center rounded-full border bg-elevada text-tinta-suave shadow-sm hover:text-cita"
            aria-label={abierto ? `Cerrar ${nodo.texto}` : `Abrir ${nodo.texto} (${nodo.hijos.length})`}
          >
            {abierto ? <ChevronLeft className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          </button>
        )}
      </div>
      {abierto && nodo.hijos.length > 0 && (
        <ul className="mapa-hijos" role="group">
          {nodo.hijos.map((h) => (
            <li key={h.id}>
              <Rama nodo={h} nivel={nivel + 1} abiertos={abiertos} alAlternar={alAlternar} alPreguntar={alPreguntar} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ---- tarjetas ----
export function Tarjetas({ tarjetas: originales }: { tarjetas: Tarjeta[] }) {
  const [orden, setOrden] = useState(() => originales.map((_, i) => i))
  const [i, setI] = useState(0)
  const [volteada, setVolteada] = useState(false)
  const t = originales[orden[i]]
  const ir = (paso: number) => {
    setI((x) => Math.min(orden.length - 1, Math.max(0, x + paso)))
    setVolteada(false)
  }
  const alTeclear = (e: KeyboardEvent) => {
    if (e.key === 'ArrowRight') ir(1)
    else if (e.key === 'ArrowLeft') ir(-1)
    else return
    e.preventDefault()
  }
  return (
    <div className="mx-auto max-w-xl space-y-4" onKeyDown={alTeclear}>
      <button
        onClick={() => setVolteada((v) => !v)}
        className={cn(
          'flex min-h-56 w-full flex-col rounded-lg border p-6 text-left shadow-flota transition-colors duration-200',
          volteada ? 'border-cita/40 bg-cita-tinte' : 'bg-elevada',
        )}
        aria-label={volteada ? `Respuesta: ${t.respuesta}. Toca para ver la pregunta` : `Pregunta: ${t.pregunta}. Toca para ver la respuesta`}
      >
        <span className={cn('text-xs font-medium', volteada ? 'text-cita-hondo' : 'text-tinta-suave')}>
          {volteada ? 'Respuesta' : 'Pregunta'}
        </span>
        <span key={`${orden[i]}-${volteada}`} className="flex flex-1 items-center justify-center py-4 text-center text-lg leading-snug font-medium text-balance animate-[aparecer_160ms_ease-out]">
          {volteada ? t.respuesta : t.pregunta}
        </span>
        <span className="text-center text-xs text-tinta-tenue">{volteada ? 'Toca para volver a la pregunta' : 'Toca para ver la respuesta'}</span>
      </button>
      <div className="flex items-center justify-between gap-2">
        <Boton variante="contorno" tamano="icono" onClick={() => ir(-1)} disabled={i === 0} aria-label="Tarjeta anterior">
          <ChevronLeft />
        </Boton>
        <span className="text-[13px] text-tinta-suave" aria-live="polite">
          {i + 1} de {orden.length}
        </span>
        <div className="flex gap-1">
          <Ayuda texto="Revolver las tarjetas">
            <Boton
              variante="fantasma"
              tamano="icono"
              aria-label="Revolver las tarjetas"
              onClick={() => {
                setOrden((o) => [...o].sort(() => Math.random() - 0.5))
                setI(0)
                setVolteada(false)
              }}
            >
              <Shuffle />
            </Boton>
          </Ayuda>
          <Boton variante="contorno" tamano="icono" onClick={() => ir(1)} disabled={i === orden.length - 1} aria-label="Tarjeta siguiente">
            <ChevronRight />
          </Boton>
        </div>
      </div>
    </div>
  )
}

// ---- cuestionario ----
export function Cuestionario({ preguntas }: { preguntas: Pregunta[] }) {
  const [elegidas, setElegidas] = useState<Record<number, string>>({})
  const respondidas = Object.keys(elegidas).length
  const buenas = preguntas.filter((p) => elegidas[p.n] === p.correcta).length
  return (
    <div className="space-y-4">
      <div className="sticky top-0 z-10 -mx-1 flex items-center justify-between gap-2 rounded-md bg-elevada/95 px-1 py-1.5 backdrop-blur">
        <p className="text-[13px] text-tinta-suave" aria-live="polite">
          {respondidas === preguntas.length
            ? `Terminaste: ${buenas} de ${preguntas.length} ${preguntas.length === 1 ? 'correcta' : 'correctas'}.`
            : `Respondiste ${respondidas} de ${preguntas.length}${respondidas ? `, ${buenas} ${buenas === 1 ? 'correcta' : 'correctas'}` : ''}.`}
        </p>
        {respondidas > 0 && (
          <Boton variante="fantasma" tamano="sm" onClick={() => setElegidas({})}>
            <RotateCcw />
            Empezar de nuevo
          </Boton>
        )}
      </div>
      <ol className="space-y-5">
        {preguntas.map((p) => {
          const elegida = elegidas[p.n]
          return (
            <li key={p.n} className="space-y-2">
              <p className="font-medium">
                {p.n}. {p.texto}
              </p>
              <div className="grid gap-1.5" role="group" aria-label={`Alternativas de la pregunta ${p.n}`}>
                {p.opciones.map((o) => {
                  const esCorrecta = o.letra === p.correcta
                  const marcada = elegida === o.letra
                  return (
                    <button
                      key={o.letra}
                      disabled={!!elegida}
                      onClick={() => setElegidas((e) => ({ ...e, [p.n]: o.letra }))}
                      className={cn(
                        'flex items-start gap-2.5 rounded-md border px-3 py-2 text-left text-[13.5px] transition-colors disabled:cursor-default',
                        !elegida && 'bg-superficie hover:border-cita/50 hover:bg-cita-tinte',
                        elegida && esCorrecta && 'border-acento/50 bg-acento-tinte',
                        elegida && marcada && !esCorrecta && 'border-peligro/40 bg-peligro-tinte',
                        elegida && !marcada && !esCorrecta && 'opacity-60',
                      )}
                    >
                      <span className="mt-px flex size-5 shrink-0 items-center justify-center rounded-sm bg-hundida text-[11px] font-semibold uppercase">
                        {elegida && esCorrecta ? <Check className="size-3.5 text-acento" /> : elegida && marcada ? <X className="size-3.5 text-peligro" /> : o.letra}
                      </span>
                      <span>{o.texto}</span>
                    </button>
                  )
                })}
              </div>
              {elegida && (
                <p className={cn('text-[13px]', elegida === p.correcta ? 'text-acento' : 'text-peligro')} role="status">
                  {elegida === p.correcta ? 'Correcta. ' : `Era la ${p.correcta.toUpperCase()}. `}
                  <span className="text-tinta-suave">{p.porque}</span>
                </p>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export function BotonPreguntar({ texto, alPreguntar }: { texto: string; alPreguntar: (texto: string) => void }) {
  return (
    <button
      onClick={() => alPreguntar(texto)}
      className="flex w-full items-start gap-2 rounded-md border bg-superficie px-3 py-2 text-left text-[13px] transition-colors hover:border-cita/50 hover:bg-cita-tinte"
    >
      <MessageSquare className="mt-0.5 size-3.5 shrink-0 text-cita" aria-hidden />
      <span>{texto}</span>
    </button>
  )
}
