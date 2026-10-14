import './estilos.css'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from 'sonner'
import { Marco } from './componentes/Marco'
import { aplicarTema, temaGuardado, useRuta } from './lib/utiles'
import { PaginaAjustes } from './paginas/Ajustes'
import { PaginaBiblioteca } from './paginas/Biblioteca'
import { PaginaCuaderno } from './paginas/Cuaderno'
import { PaginaCuadernos } from './paginas/Cuadernos'
import { ProveedorAyuda } from './ui/piezas'
import { Arranque } from './web/Arranque'
import { ES_WEB } from './web/config'
import { iniciarWeb } from './web/puente'

aplicarTema(temaGuardado())
// en la versión web, los pedidos a api/ los atiende el motor en Python dentro del navegador
if (ES_WEB) iniciarWeb()

const cliente = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true, staleTime: 2_000 } },
})

function App() {
  const ruta = useRuta()
  return (
    <Marco ruta={ruta}>
      {ruta.pagina === 'cuaderno' ? (
        <PaginaCuaderno key={ruta.id} id={ruta.id} />
      ) : ruta.pagina === 'biblioteca' ? (
        <PaginaBiblioteca />
      ) : ruta.pagina === 'ajustes' ? (
        <PaginaAjustes />
      ) : (
        <PaginaCuadernos />
      )}
    </Marco>
  )
}

createRoot(document.getElementById('raiz')!).render(
  <StrictMode>
    <QueryClientProvider client={cliente}>
      <ProveedorAyuda>
        {ES_WEB ? (
          <Arranque>
            <App />
          </Arranque>
        ) : (
          <App />
        )}
        <Toaster position="bottom-right" toastOptions={{ className: 'font-sans' }} />
      </ProveedorAyuda>
    </QueryClientProvider>
  </StrictMode>,
)
