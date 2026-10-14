// Carpetas conectadas: Tesela lee los documentos de una carpeta del computador y los mantiene al día al sincronizar.
import { useMutation } from '@tanstack/react-query'
import { CircleAlert, Folder, FolderSync, MoreVertical, RefreshCw, Unplug } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { api, type Carpeta } from '../lib/api'
import { CLAVES, useCarpetas, useRefrescar } from '../lib/consultas'
import { enCurso, resumen, sincronizacionDe, sincronizar, useSincronizaciones } from '../lib/sincronizar'
import { cn, haceCuanto, plural } from '../lib/utiles'
import { Boton } from '../ui/boton'
import { Campo, Confirmar, Dialogo, Etiqueta, Girando, MenuContenido, MenuDisparador, MenuItem, MenuRaiz } from '../ui/piezas'

function useAlTerminar(cuaderno: string | null) {
  const refrescar = useRefrescar()
  return () =>
    refrescar(CLAVES.carpetas, CLAVES.documentos, CLAVES.cuadernos, CLAVES.estado, ...(cuaderno ? [CLAVES.cuaderno(cuaderno)] : []))
}

export function DialogoCarpeta({ abierto, alCambiar, cuaderno }: { abierto: boolean; alCambiar: (a: boolean) => void; cuaderno: string }) {
  const [ruta, setRuta] = useState('')
  const [id, setId] = useState<string | null>(null)
  const sincronizaciones = useSincronizaciones()
  const alTerminar = useAlTerminar(cuaderno)
  const actual = id ? sincronizaciones[id] : undefined
  useEffect(() => {
    if (abierto) {
      setRuta('')
      setId(null)
    }
  }, [abierto])
  const conectar = useMutation({
    mutationFn: () => api.conectarCarpeta(ruta, cuaderno),
    onSuccess: (carpeta) => {
      setId(carpeta.id)
      void sincronizar(carpeta.id, alTerminar)
      alTerminar()
    },
  })
  const enviar = (e: FormEvent) => {
    e.preventDefault()
    if (ruta.trim()) conectar.mutate()
  }
  return (
    <Dialogo
      abierto={abierto}
      alCambiar={alCambiar}
      titulo="Conectar una carpeta"
      descripcion="Tesela lee los PDF, Word, PowerPoint, Excel y textos de la carpeta y de sus subcarpetas y los agrega a este cuaderno. Tus archivos no se tocan: Tesela guarda su propia copia."
    >
      <div className="space-y-4 p-5">
        {!id ? (
          <form onSubmit={enviar} className="space-y-4">
            <div>
              <Etiqueta htmlFor="ruta-carpeta">Ruta de la carpeta</Etiqueta>
              <Campo
                id="ruta-carpeta"
                value={ruta}
                onChange={(e) => setRuta(e.target.value)}
                placeholder="C:\Users\tu-nombre\Documents\Contratos"
                autoFocus
                spellCheck={false}
              />
              <p className="mt-1.5 text-xs text-tinta-suave">
                En el Explorador de Windows: clic derecho sobre la carpeta, «Copiar como ruta de acceso», y pégala aquí.
              </p>
              {conectar.error && <p className="mt-2 text-[13px] text-peligro" role="alert">{conectar.error.message}</p>}
            </div>
            <div className="flex justify-end gap-2">
              <Boton variante="contorno" onClick={() => alCambiar(false)}>
                Cancelar
              </Boton>
              <Boton type="submit" variante="principal" disabled={!ruta.trim() || conectar.isPending}>
                {conectar.isPending ? <Girando className="text-sobre-primario" /> : <FolderSync />}
                Conectar y leer
              </Boton>
            </div>
          </form>
        ) : (
          <EstadoSincronizacion id={id} alCerrar={() => alCambiar(false)} actual={actual} />
        )}
      </div>
    </Dialogo>
  )
}

function EstadoSincronizacion({ actual, alCerrar }: { id: string; actual?: ReturnType<typeof useSincronizaciones>[string]; alCerrar: () => void }) {
  if (!actual || enCurso(actual))
    return (
      <p className="flex items-center gap-2 text-sm" role="status">
        <Girando className="text-cita" />
        {actual?.paso || 'Empezando'}
      </p>
    )
  return (
    <div className="space-y-3" role="status">
      {actual.error ? (
        <p className="flex items-start gap-2 text-sm text-peligro">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {actual.error}
        </p>
      ) : (
        actual.informe && <InformeCarpeta informe={actual.informe} />
      )}
      <div className="flex justify-end">
        <Boton variante="principal" onClick={alCerrar}>
          Listo
        </Boton>
      </div>
    </div>
  )
}

function InformeCarpeta({ informe }: { informe: NonNullable<ReturnType<typeof useSincronizaciones>[string]['informe']> }) {
  const problemas = [...informe.errores, ...informe.omitidos]
  return (
    <div className="space-y-2 text-sm">
      <p className="font-medium">{resumen(informe)}</p>
      {problemas.length > 0 && (
        <div className="rounded-md border border-aviso/30 bg-aviso-tinte px-3 py-2">
          <p className="mb-1 text-[13px] font-medium">{plural(problemas.length, 'archivo no se agregó', 'archivos no se agregaron')}:</p>
          <ul className="space-y-0.5 text-xs">
            {problemas.slice(0, 8).map((x) => (
              <li key={x.archivo}>
                <span className="font-medium">{x.archivo}</span>: {x.texto}
              </li>
            ))}
            {problemas.length > 8 && <li>y {problemas.length - 8} más</li>}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Las carpetas conectadas a un cuaderno (o todas, en la página de Fuentes), con su botón para sincronizar. */
export function ListaCarpetas({ cuaderno, todas }: { cuaderno?: string; todas?: boolean }) {
  const { data: carpetas } = useCarpetas()
  const visibles = (carpetas ?? []).filter((c) => todas || c.cuaderno === cuaderno)
  if (!visibles.length) return null
  return (
    <ul className="space-y-2" aria-label="Carpetas conectadas">
      {visibles.map((c) => (
        <FilaCarpeta key={c.id} carpeta={c} conCuaderno={todas} />
      ))}
    </ul>
  )
}

function FilaCarpeta({ carpeta: c, conCuaderno }: { carpeta: Carpeta; conCuaderno?: boolean }) {
  const sincronizaciones = useSincronizaciones()
  const s = sincronizaciones[c.id]
  const alTerminar = useAlTerminar(c.cuaderno)
  const [desconectando, setDesconectando] = useState(false)
  const refrescar = useRefrescar()
  const desconectar = useMutation({
    mutationFn: () => api.desconectarCarpeta(c.id),
    onSuccess: () => {
      setDesconectando(false)
      toast(`Desconectaste ${nombreCarpeta(c.ruta)}`, { description: 'Los documentos que ya trajo se quedan.' })
      refrescar(CLAVES.carpetas)
    },
    onError: (e) => toast.error(e.message),
  })
  const ocupada = enCurso(s)
  return (
    <li className="rounded-lg border border-dashed bg-superficie px-3 py-2.5">
      <div className="flex items-center gap-2.5">
        <Folder className="size-4 shrink-0 text-cita" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium" title={c.ruta}>
            {nombreCarpeta(c.ruta)}
            {conCuaderno && c.cuaderno_nombre && <span className="font-normal text-tinta-suave"> → {c.cuaderno_nombre}</span>}
          </p>
          <p className={cn('truncate text-xs', s?.error ? 'text-peligro' : 'text-tinta-suave')} title={s?.error}>
            {ocupada
              ? s?.paso
              : s?.error
                ? s.error
                : `${plural(c.documentos, 'documento', 'documentos')}${c.sincronizada ? `, sincronizada ${haceCuanto(c.sincronizada)}` : ''}`}
          </p>
        </div>
        <Boton
          variante="fantasma"
          tamano="icono-sm"
          onClick={() =>
            sincronizar(c.id, () => {
              alTerminar()
              const final = sincronizacionDe(c.id)
              if (final?.informe) {
                const problemas = final.informe.errores.length + final.informe.omitidos.length
                toast.success(`${nombreCarpeta(c.ruta)}: ${resumen(final.informe).toLowerCase()}`, {
                  description: problemas ? `${plural(problemas, 'archivo no se agregó', 'archivos no se agregaron')}.` : undefined,
                })
              }
            })
          }
          disabled={ocupada}
          aria-label={`Sincronizar ${nombreCarpeta(c.ruta)}`}
          title="Sincronizar: agrega los nuevos, actualiza los que cambiaron y quita los que ya no están"
        >
          {ocupada ? <Girando /> : <RefreshCw />}
        </Boton>
        <MenuRaiz>
          <MenuDisparador asChild>
            <Boton variante="fantasma" tamano="icono-sm" aria-label={`Opciones de ${nombreCarpeta(c.ruta)}`}>
              <MoreVertical />
            </Boton>
          </MenuDisparador>
          <MenuContenido>
            <MenuItem icono={Unplug} onSelect={() => setDesconectando(true)}>
              Desconectar
            </MenuItem>
          </MenuContenido>
        </MenuRaiz>
      </div>
      <Confirmar
        abierto={desconectando}
        alCambiar={setDesconectando}
        titulo={`¿Desconectar ${nombreCarpeta(c.ruta)}?`}
        descripcion="Tesela deja de seguir esta carpeta. Los documentos que ya trajo se quedan en la biblioteca y en el cuaderno."
        accion="Desconectar"
        ocupado={desconectar.isPending}
        alConfirmar={() => desconectar.mutate()}
      />
    </li>
  )
}

function nombreCarpeta(ruta: string) {
  return ruta.split(/[\\/]/).filter(Boolean).at(-1) || ruta
}
