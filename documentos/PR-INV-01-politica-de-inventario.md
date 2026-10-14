# PR-INV-01 Política de inventario de repuestos

Versión 1, vigente desde el 1 de abril de 2026. Responsable: jefe de planificación de materiales.

## Clasificación ABC

Cada repuesto se clasifica una vez al año según su consumo valorizado de los últimos 12 meses:

- **A:** los repuestos que suman el 80 % del consumo valorizado.
- **B:** los que suman el siguiente 15 %.
- **C:** el 5 % restante.

## Política de reposición

Los repuestos con consumo regular se reponen con una política de revisión periódica (R, S): cada R semanas se revisa el inventario y se pide lo necesario para llegar al nivel S.

| Clase | Revisión (R) | Nivel de servicio objetivo |
|---|---|---|
| A | cada 1 semana | 98 % |
| B | cada 2 semanas | 95 % |
| C | cada 4 semanas | 90 % |

El stock de seguridad se calcula como z · σ · √(L + R), donde σ es la desviación estándar de la demanda semanal, L el plazo del proveedor en semanas y z el factor del nivel de servicio.

## Repuestos críticos sin consumo regular

Los repuestos críticos de baja rotación (por ejemplo, un motor de tracción) no siguen la política (R, S). Se mantiene un stock fijo definido por el comité de criticidad, revisado cada 6 meses.

## Inventario obsoleto

Un repuesto sin movimiento en 24 meses se marca como obsoleto. El comité de criticidad decide en un plazo de 3 meses si se mantiene, se vende o se da de baja.
