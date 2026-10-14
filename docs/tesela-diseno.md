# Tesela: identidad y espacio de trabajo

## Referencias y decisiones

Se revisaron Fuente, Mesa documental y, como inspiración, NotebookLM y
[Open Notebook](https://github.com/lfnovo/open-notebook/blob/main/docs/3-USER-GUIDE/interface-overview.md):
de ahí viene la idea de organizar el trabajo en cuadernos con fuentes, notas y chat. Marca, paleta,
tipografía y componentes son propios de Tesela.

- Marca: **Tesela** (hasta el 13 de octubre de 2026 se llamó Mesa). La marca es un mosaico de cuatro piezas
  redondeadas en un solo color: las fuentes de un cuaderno; la pieza sin relleno es la que se está citando. En la
  barra lateral va sola, en el color primario; el ícono de la app y del acceso directo la pone en celeste sobre la
  tinta de la barra (`interfaz/public/tesela.svg` y `tesela.ico`).
- Trabajo principal: reunir documentos, consultar sus pasajes y conservar notas.
- Navegación: Cuadernos, Fuentes y Modelos en una lista simple, sin las divisiones
  Reunir/Procesar/Administrar de la referencia.
- Composición: fuentes a la izquierda, conversación al centro y Estudio (lo que se escribe con las fuentes y las
  notas) a la derecha. El mapa de ideas es el único elemento que se sale de la cuadrícula: un árbol sobre papel
  punteado.
  El ancho favorece la lectura. En móvil, pestañas y chat como vista inicial.
- Paleta: papel frío, tinta azul y acento cobalto; grafito en oscuro, ámbar en Estudio y notas.
  Se reemplaza la paleta Quiet Green. Colores semánticos para avisos y errores.
- Tipografía: Instrument Sans para texto y títulos; jerarquía por tamaño y peso.
- Estados: biblioteca vacía, carga, búsqueda, respuesta, fuente abierta y errores
  siguen usando datos reales del servidor. No se precargan respuestas de ejemplo.
- Accesibilidad: controles de teclado, foco visible, reducción de movimiento y
  contraste suficiente en ambos temas. Validar 320, 768, 1024 y 1440 px.

Se conservan rutas, datos, preferencias guardadas y contratos del servidor. Esta
tarea no completa F5/F7 ni convierte los resultados históricos de Fuente en una
evaluación del producto actual. Las licencias y los créditos no se eliminan.
