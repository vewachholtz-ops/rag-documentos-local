import { ES_WEB } from '../web/config'
import { api, type Documento, llamar } from './api'

type FuenteOriginal = { id: string; tipo?: Documento['tipo'] | null; url?: string }

export function etiquetaOriginal(fuente: FuenteOriginal, pagina?: number | null) {
  if (fuente.url) return 'Abrir la página'
  if (fuente.tipo === 'pdf') return pagina ? `Abrir el PDF en la página ${pagina}` : 'Abrir el PDF'
  return 'Descargar el original'
}

/** Los textos se leen en el visor de Tesela; el archivo original se conserva como descarga. */
export function abrirOriginal(fuente: FuenteOriginal, pagina?: number | null) {
  if (ES_WEB && !fuente.url) return void abrirEnLaVersionWeb(fuente, pagina)
  const url = fuente.url ?? api.original(fuente.id, pagina)
  if (fuente.url || fuente.tipo === 'pdf') {
    window.open(url, '_blank', 'noopener,noreferrer')
    return
  }
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = ''
  document.body.append(enlace)
  enlace.click()
  enlace.remove()
}

/** En la versión web no hay servidor que entregue el archivo: se le pide al motor y se abre desde la memoria. */
async function abrirEnLaVersionWeb(fuente: FuenteOriginal, pagina?: number | null) {
  // la pestaña del PDF se abre dentro del clic; si se abriera después de esperar, el navegador la bloquearía
  const ventana = fuente.tipo === 'pdf' ? window.open('', '_blank') : null
  const r = await llamar(api.original(fuente.id, pagina))
  if (!r.ok) {
    ventana?.close()
    return
  }
  const disposicion = r.headers.get('Content-Disposition') ?? ''
  const nombre = decodeURIComponent(/filename\*=UTF-8''([^;]+)/.exec(disposicion)?.[1] ?? 'documento')
  const url = URL.createObjectURL(await r.blob())
  if (ventana) {
    ventana.location.href = pagina ? `${url}#page=${pagina}` : url
    return
  }
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  document.body.append(enlace)
  enlace.click()
  enlace.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
