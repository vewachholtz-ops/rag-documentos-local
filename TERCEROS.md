# Código de otros proyectos

El código propio de Tesela usa la licencia PolyForm Noncommercial 1.0.0 (ver `LICENSE`). Lo que viene de otros
proyectos conserva su licencia original, que se lista aquí.

## Mesa documental

El modo sin IA, la política de contenido (CSP), el token por sesión, los límites contra archivos que se inflan y
la idea de conectar carpetas vienen de Mesa documental, el RAG que escribió Codex en paralelo para este mismo
portafolio.

## Tipografía y bibliotecas

- Instrument Sans, por [Fontsource](https://fontsource.org): SIL Open Font License 1.1.
- React, Radix UI, TanStack Query, lucide-react (ISC), sonner, clsx y tailwind-merge (MIT), y las demás piezas que
  van dentro de la página: la lista con versión y licencia completa de cada una la arma `npm run build` en
  [`app/licencias.txt`](app/licencias.txt). Tailwind CSS, Vite y TypeScript (MIT, Apache-2.0) solo se usan para
  construirla.
- numpy (BSD) y pypdf (BSD) en el servidor.
- En la versión web (site/app/), el navegador baja [Pyodide](https://pyodide.org) 0.27.7 (Mozilla Public License 2.0)
  desde su CDN, con numpy (BSD) y pyodide-http (MIT); la rueda de pypdf (BSD) va junto a la página, en `py/`.

## Ideas

Las ideas del motor de búsqueda y de la comprobación de citas, con sus fuentes y licencias, están en
[docs/como-funciona.md](docs/como-funciona.md#de-dónde-salió-cada-idea). La organización en cuadernos con fuentes,
notas y chat, y el panel Estudio (guía de cada fuente, resumen, guía de estudio, cuestionario, tarjetas, mapa de
ideas), se inspiraron en NotebookLM y en [Open Notebook](https://github.com/lfnovo/open-notebook), sin usar su
código. Leer un documento largo por partes y escribir con las notas (map-reduce) es la técnica conocida para
resumir textos que no caben en el contexto de un modelo.
