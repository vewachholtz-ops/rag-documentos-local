import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// La página construida va a ../app, que sirve `uv run rag servir`. En desarrollo (`npm run dev`), /api se pasa a
// ese servidor en el puerto 8000 con su propio Host y Origin, que son los únicos que acepta.
// Con VITE_WEB=1 se construye la versión web (../site/app, publicada en GitHub Pages): el motor de Python corre en
// el navegador con Pyodide; scripts/construir_web.py le agrega después el motor empaquetado (py/).
const SERVIDOR = 'http://127.0.0.1:8000'
const WEB = process.env.VITE_WEB === '1'

/** La app instalada no usa el Worker de la versión web: no se publica en app/. */
function sinTrabajadorWeb(): Plugin {
  return {
    name: 'sin-trabajador-web',
    apply: 'build',
    generateBundle(_, paquete) {
      if (WEB) return
      for (const nombre of Object.keys(paquete)) if (/(^|\/)trabajador-[\w-]+\.js$/.test(nombre)) delete paquete[nombre]
    },
  }
}

/** Deja en app/licencias.txt la licencia de cada paquete que termina dentro de la página construida (React,
 * Radix, las tipografías, etc.): la licencia MIT pide incluir el aviso en las copias. */
function licencias(): Plugin {
  return {
    name: 'licencias',
    apply: 'build',
    generateBundle() {
      const paquetes = new Map<string, string>()
      for (const id of this.getModuleIds()) {
        const ruta = id.replace(/\0/g, '').split('?')[0]
        const i = ruta.lastIndexOf('/node_modules/')
        if (i < 0) continue
        const resto = ruta.slice(i + '/node_modules/'.length).split('/')
        const nombre = resto[0].startsWith('@') ? `${resto[0]}/${resto[1]}` : resto[0]
        paquetes.set(nombre, join(ruta.slice(0, i), 'node_modules', nombre))
      }
      // las tipografías entran por CSS y no siempre aparecen como módulos
      for (const fuente of ['@fontsource-variable/instrument-sans'])
        paquetes.set(fuente, join(process.cwd(), 'node_modules', fuente))
      const partes = [...paquetes.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([nombre, carpeta]) => {
          const datos = JSON.parse(readFileSync(join(carpeta, 'package.json'), 'utf8'))
          const archivo = existsSync(carpeta) ? readdirSync(carpeta).find((f) => /^(licen[cs]e|copying)/i.test(f)) : undefined
          const texto = archivo ? readFileSync(join(carpeta, archivo), 'utf8').trim() : `Licencia: ${datos.license}`
          return `${nombre} ${datos.version} (${datos.license})\n\n${texto}`
        })
      this.emitFile({
        type: 'asset',
        fileName: 'licencias.txt',
        source: `${readFileSync(join(process.cwd(), '../TERCEROS.md'), 'utf8')}\n\nLicencias del código incluido en la página.\n\n${partes.join(`\n\n${'-'.repeat(72)}\n\n`)}\n`,
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), licencias(), sinTrabajadorWeb()],
  base: './',
  build: { outDir: WEB ? '../site/app' : '../app', emptyOutDir: true, chunkSizeWarningLimit: 800 },
  worker: { format: 'es' },
  server: {
    proxy: {
      '/api': {
        target: SERVIDOR,
        changeOrigin: true,
        // con `MESA_TOKEN=dev uv run rag servir` y `MESA_TOKEN=dev npm run dev`, el token de la sesión es conocido
        configure: (proxy) =>
          proxy.on('proxyReq', (pedido) => {
            pedido.setHeader('origin', SERVIDOR)
            if (process.env.MESA_TOKEN) pedido.setHeader('x-mesa-token', process.env.MESA_TOKEN)
          }),
      },
    },
  },
})

