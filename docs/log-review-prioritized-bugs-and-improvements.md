# Revisión de logs — Bugs y mejoras priorizadas para ejecución técnica

Este documento resume los principales hallazgos detectados en los logs recientes del copiloto y los traduce en tareas concretas para ejecución técnica.

Fuente base del análisis: logs compartidos por el usuario en conversación.

---

## Resumen ejecutivo

### Lo que sí mejoró
- Ya existe detección de ambigüedad en follow-ups.
- Ya se evita, en algunos casos, responder automáticamente con una entidad equivocada.
- Ya existen métricas útiles como `entity_candidates`, `entity_conflict_detected`, `followup_confidence` y `clarification_reason`.

### Lo que sigue fallando
1. Algunas consultas tienen **intent mal interpretado**.
2. Se siguen haciendo **lecturas con campos inválidos** antes de corregir en la siguiente iteración.
3. La **aclaración explícita del usuario no siempre se consume correctamente**.
4. La semántica de **factura de compra vs factura de venta** sigue siendo inconsistente.
5. Las latencias siguen siendo altas por exceso de iteraciones, retries y tool misuse.

---

# Prioridad 1 — Consumir correctamente la aclaración explícita del usuario

## Problema
Cuando el usuario ya aclaró explícitamente la entidad, el sistema a veces vuelve a preguntar o no fija correctamente la entidad resultante.

## Evidencia observada
Caso similar a:
- Usuario: `venta DCN 0426-0060`
- Respuesta del agente: vuelve a preguntar si se refiere a la venta o a la compra previa.

Eso indica que la aclaración del usuario no está cerrando el conflicto, sino que el sistema sigue arrastrando entidades candidatas viejas.

## Impacto
- Mala UX.
- Doble aclaración innecesaria.
- Sensación de torpeza conversacional.
- Riesgo de seguir contaminando la memoria activa.

## Acción requerida
Implementar una ruta explícita de **resolución de aclaración**:
- si el usuario menciona una entidad concreta tras una aclaración,
- esa entidad debe fijarse como la entidad activa,
- se debe limpiar el conflicto previo,
- y no se debe volver a pedir aclaración por el mismo motivo.

## Criterios de aceptación
- Si el usuario responde con `venta DCN 0426-0060`, el conflicto queda resuelto.
- `primary_entity` y/o `last_explicit_entity` se actualizan.
- El siguiente turno ya no re-pregunta por la misma ambigüedad.
- Los logs reflejan que la aclaración fue consumida correctamente.

## Subtareas
- Crear ruta explícita `clarification_resolution`.
- Detectar respuesta del usuario que contiene entidad concreta.
- Actualizar memoria activa y limpiar candidatos conflictivos.
- Agregar tests multi-turno de aclaración.

---

# Prioridad 2 — Corregir la semántica de factura para compras

## Problema
La lógica de facturas sigue cruzando semántica de venta y compra. En algunos flujos de compra se observa uso de filtros o relaciones de factura de venta.

## Evidencia observada
Caso `compra PO-I-10-00044`:
- búsqueda por campos inválidos o dudosos como `purchase_order_id`, `sale_order_id`, `sale_id`
- mezcla de entidades no relacionadas
- uso de `move_type in ('out_invoice', 'out_refund')` cuando el contexto es compra

## Impacto
- Riesgo alto de respuesta incorrecta.
- Búsquedas erróneas sobre `account.move`.
- Alto costo en iteraciones y latencia.

## Acción requerida
Definir una capa explícita de resolución relacional de facturas según tipo de documento origen.

## Reglas requeridas
- `sale.order` → `move_type in ('out_invoice', 'out_refund')`
- `purchase.order` → `move_type in ('in_invoice', 'in_refund')`

## Criterios de aceptación
- Una compra nunca consulta facturas de venta.
- Una venta nunca consulta facturas de compra.
- El dominio final usado queda alineado con el tipo del documento.
- Se eliminan rutas exploratorias con campos relacionales inválidos.

## Subtareas
- Crear mapper `document_model -> invoice_resolution_strategy`.
- Bloquear relaciones inválidas por schema.
- Agregar tests para venta/factura y compra/factura.

---

# Prioridad 3 — Separar mejor intención de resumen vs listado

## Problema
Consultas como `ventas del mes` se están resolviendo como listado de registros, cuando semánticamente parecen una consulta agregada o de resumen.

## Evidencia observada
Para `ventas del mes` el sistema hizo:
- `search` de `sale.order`
- `read` de 5 registros
- respuesta narrativa con 5 ventas concretas

Cuando la expectativa más natural suele ser:
- total del mes,
- cantidad de ventas,
- resumen,
- o pedir aclaración entre resumen y detalle.

## Impacto
- Respuestas útiles pero semánticamente torcidas.
- Menor calidad de UX.
- Más tool calls y más latencia de lo necesario.

## Acción requerida
Refinar la clasificación de intención para distinguir al menos:
- resumen agregado
- listado
- top N
- último registro
- detalle de entidad

## Criterios de aceptación
- `ventas del mes` devuelve resumen o pide precisión.
- `dame las ventas del mes` puede devolver listado si corresponde.
- `top ventas del mes` usa ranking/agregación.

## Subtareas
- Revisar heurísticas actuales de intent.
- Definir intents mínimos de negocio.
- Mapear cada intent a ruta determinística o tool adecuada.
- Agregar tests de intención para frases frecuentes.

---

# Prioridad 4 — Evitar primer intento con fields inválidos

## Problema
En consultas como `última compra` o `última venta`, el agente hace un primer `read` con campos inválidos y recién corrige en la siguiente iteración.

## Evidencia observada
Se intentó leer campos como:
- `display_name`
- `ref`
- `invoice_origin`

Luego Odoo respondió `ERR_INVALID_QUERY` y recién después se corrigió usando campos válidos.

## Impacto
- Iteraciones innecesarias.
- Mayor latencia.
- Mayor consumo de tokens.
- Menor robustez.

## Acción requerida
Fortalecer allowlist/schema de lectura por modelo para que el primer intento use directamente el set correcto de campos.

## Criterios de aceptación
- El primer `read` ya usa campos válidos.
- Se eliminan errores `ERR_INVALID_QUERY` evitables en flujos comunes.
- Baja el número de iteraciones en consultas simples.

## Subtareas
- Revisar allowlist por modelo.
- Definir campos por defecto para `sale.order` y `purchase.order`.
- Añadir validación previa antes del `query_odoo_read`.

---

# Prioridad 5 — Limpiar memoria candidata vieja y reducir contaminación contextual

## Problema
En algunos casos aparecen entidades candidatas viejas que siguen contaminando el contexto aunque el usuario ya esté operando sobre otra entidad reciente.

## Evidencia observada
Ejemplo: se detectan candidatos conflictivos antiguos junto con la entidad actual, generando aclaraciones innecesarias o ruido en la resolución.

## Impacto
- Aclaraciones redundantes.
- Menor confianza del usuario.
- Riesgo de rutas equivocadas en multi-turno.

## Acción requerida
Revisar reglas de expiración, reemplazo y limpieza de entidades candidatas.

## Criterios de aceptación
- Las entidades viejas no compiten indefinidamente con una entidad explícita nueva.
- La memoria refleja mejor el contexto reciente.
- Los `entity_candidates` son realmente relevantes para el turno actual.

## Subtareas
- Revisar TTL de entidad conversacional.
- Priorizar `last_explicit_entity` reciente.
- Limpiar candidatos al cerrar aclaración.
- Loggear cuándo se purga memoria candidata.

---

# Prioridad 6 — Reducir latencia en rutas comunes

## Problema
Consultas simples siguen teniendo latencias muy altas por exceso de iteraciones, retries y exploración incorrecta de tools.

## Evidencia observada
Casos de latencia alta:
- `ventas del mes` ~10s
- `última compra` ~6s
- `última venta` ~7s
- `compra PO-I-10-00044` ~19s

## Impacto
- Peor UX.
- Mayor costo en tokens.
- Sensación de lentitud incluso en preguntas fáciles.

## Acción requerida
Optimizar rutas frecuentes para que salgan por caminos más cerrados y determinísticos.

## Criterios de aceptación
- Consultas comunes bajan de forma consistente en tool calls e iteraciones.
- `pass_optimo` mejora en casos simples.
- Se reducen warnings de `high_iterations`, `high_latency`, `high_tokens`.

## Subtareas
- Crear rutas rápidas para `última venta`, `última compra`, `ventas del mes`, `top ventas`.
- Evitar tool retries cuando el schema ya descarta un campo.
- Acortar respuesta final cuando el resultado es simple.

---

# Lista corta de bugs concretos para ejecutar primero

## Bug 1
**La aclaración explícita del usuario no fija correctamente la entidad activa.**

## Bug 2
**La semántica de facturas para compras sigue mezclándose con lógica de ventas.**

## Bug 3
**El intent de consultas tipo resumen/listado no está bien separado.**

## Bug 4
**Se siguen intentando lecturas con fields inválidos antes de usar los correctos.**

## Bug 5
**La memoria de entidades candidatas arrastra contexto viejo y genera ruido.**

---

# Orden recomendado de ejecución

## Sprint corto 1
1. Consumir correctamente la aclaración explícita del usuario.
2. Corregir semántica de facturas para compras.
3. Evitar primer intento con fields inválidos.

## Sprint corto 2
4. Separar intención de resumen vs listado.
5. Limpiar memoria candidata vieja.
6. Optimizar latencia en rutas comunes.

---

# Criterio de cierre

Este lote de problemas se considera bien resuelto cuando:
- el usuario puede aclarar una entidad una sola vez y el sistema la fija correctamente,
- las compras consultan facturas de compra y las ventas consultan facturas de venta,
- `ventas del mes` y consultas similares siguen una semántica consistente,
- se eliminan errores evitables de `ERR_INVALID_QUERY`,
- y las rutas comunes bajan significativamente en iteraciones y latencia.
