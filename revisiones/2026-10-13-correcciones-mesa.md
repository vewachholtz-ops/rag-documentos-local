# Revisión y correcciones de Mesa

Codex, 13 de octubre de 2026. Base revisada: `4f73d51` de Claude.

## Problemas corregidos

1. «Abrir el original» mostraba Markdown crudo en otra pestaña. Se añadió «Leer en Mesa» y una descarga real,
   con nombres y acciones consistentes en el visor, las fuentes del cuaderno y la biblioteca.
2. Excel convertía `1234567890.12` en `1234567890`. Se conserva el valor textual numérico del archivo.
3. La resolución DNS comprobada podía cambiar antes de conectar. La conexión ahora usa la IP validada sin
   volver a resolver, tanto en HTTP como en HTTPS y en cada redirección. No se usan proxies del entorno.
4. Cancelar Estudio durante la última llamada todavía guardaba una nota. Hay detección de desconexión durante
   la espera y un paso confirmado antes de guardar, también para la guía de una fuente.
5. El historial descartaba automáticamente conversaciones y mensajes antiguos. Se conserva completo en disco;
   el contexto del modelo mantiene su límite independiente.
6. Al convertir notas de IA en fuentes se perdían sus advertencias y origen. Ahora acompañan al contenido.
7. Las cuotas de lectura podían exceder las 36 partes previstas. Se reparte el presupuesto exacto; una selección
   con más fuentes largas que cupos muestra un mensaje, sin omitir fuentes silenciosamente.
8. Windows permitía enlazar un segundo servidor al mismo puerto. Se exige exclusividad y se conserva el aviso de
   puerto ocupado; la prueba evita quedarse sirviendo indefinidamente si esto vuelve a fallar.

## Validación

- Se reprodujeron antes de corregir la pérdida de cifras, el acceso local por cambio DNS y el recorte de historial.
- Pruebas específicas para cancelación durante la última llamada, conexión a IP fija, Host/SNI/certificados,
  cuotas, lectura desde la guía, descarga exacta del original y procedencia de notas.
- Compilación de React y revisión de formato y estilo en Windows.
- Revisión cruzada del backend: sin nuevas regresiones materiales encontradas.
- Comprobación manual en la pestaña del usuario: «Leer en Mesa» muestra el documento y conserva el cuaderno.
- Suite completa: **197 pruebas aprobadas en Windows**, incluidas las de navegador (70,54 segundos).
- `ruff check`, `ruff format --check`, `git diff --check` y `npm run build` aprobados.

## Límites que siguen pendientes

La batería utiliza modelos simulados. Falta medir los flujos completos con Ollama y PDF largos, así como una API
real. Las notas generadas siguen necesitando contraste con las fuentes: conservar procedencia no verifica cada
afirmación. Los Excel ya indexados deben reimportarse para aplicar la corrección numérica.

No se modificaron los prompts ni los resultados de la evaluación histórica, ni la licencia.
