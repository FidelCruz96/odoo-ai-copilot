# Propuesta de rediseño UI/UX — Odoo AI Copilot

Este documento resume una propuesta práctica de rediseño del chat actual para que se sienta más como un **copiloto ERP** y menos como una caja de mensajes.

---

## Objetivo

Mejorar la experiencia actual en 5 frentes:

1. **Claridad visual**
2. **Confianza del usuario**
3. **Respuestas más estructuradas**
4. **Acciones rápidas dentro de Odoo**
5. **Mejor uso del contexto activo**

---

## Diagnóstico del estado actual

### Lo que ya está bien

- El header ya muestra contexto activo.
- El estado `En línea` ya ayuda a dar sensación de sistema vivo.
- Existen chips de sugerencias.
- La conversación ya es legible y limpia.

### Problemas detectados

1. **Mucho espacio muerto** en la pantalla.
2. Las respuestas del bot todavía parecen **texto libre**, no resultados de ERP.
3. Los chips actuales son útiles, pero no siempre son **contextuales al documento activo**.
4. El contexto activo mostrado es demasiado técnico y poco orientado al negocio.
5. El sistema responde, pero casi no empuja al usuario a una **acción siguiente**.
6. La latencia visible en milisegundos crudos (`6549 ms`) se siente más de debug que de UX.

---

## Propuesta de rediseño por zonas

## 1) Header

### Estado actual

- Título: `AI Assistant`
- Contexto activo: `purchase.order #176`
- Estado: `En línea 6549 ms`

### Propuesta

Convertir el header en una zona más útil y humana.

### Nuevo contenido sugerido

**AI Assistant**  
**Compra #176 · Proveedor: [nombre] · Estado: [estado] · Pickings: 2**  
`● En línea`

### Recomendaciones

- Mantener el título actual.
- Cambiar `purchase.order #176` por una versión más entendible para usuario final.
- Mostrar latencia de forma más discreta o solo cuando aporte valor.

### Ejemplo

- `● En línea`
- `Procesado en ~6.5 s`
- o mostrar la latencia solo en tooltip o modo debug

---

## 2) Chips de sugerencias

### Problema actual

Los chips son útiles, pero hoy se sienten demasiado generales. En contexto de compra, mostrar `Ventas del mes` o `Top clientes` no siempre ayuda.

### Propuesta

Hacer los chips **dependientes del modelo activo**.

### Ejemplo para `purchase.order`

- `Ver pickings`
- `Recepciones pendientes`
- `Recepciones canceladas`
- `Facturas del proveedor`
- `Productos pendientes`

### Ejemplo para `sale.order`

- `Facturas relacionadas`
- `Pagos pendientes`
- `Productos vendidos`
- `Margen estimado`

### Recomendación técnica

Resolver los chips desde una pequeña configuración por modelo:

- `purchase.order` → chips de compras/logística
- `sale.order` → chips de ventas/facturación
- `account.move` → chips financieros
- `stock.picking` → chips de inventario/movimientos

---

## 3) Cuerpo del chat

### Problema actual

Las respuestas todavía parecen mensajes escritos por un bot, no bloques de información operacional.

Ejemplo actual:

> Los pickings asociados a esta compra son:
> 1. Picking ID 211 ...
> 2. Picking ID 210 ...

Eso funciona, pero visualmente no parece una respuesta ERP fuerte.

### Propuesta

Pasar de **mensajes de texto** a **cards de resultado**.

### Estructura sugerida de una respuesta

- badge de tipo de respuesta
- título corto
- resumen
- detalle estructurado
- acciones rápidas

### Ejemplo visual sugerido

**Consulta ERP**

**Pickings asociados: 2**

| ID | Nombre | Estado |
|---|---|---|
| 211 | EXPRC/IN/00096 | Hecho |
| 210 | EXPRC/IN/00095 | Cancelado |

**Acciones**
- `Ver solo borrador`
- `Abrir pickings`
- `Ver cancelados`

### Beneficio

- mejor escaneo visual
- más confianza
- menos sensación de texto improvisado
- más valor operativo

---

## 4) Tipos de respuesta visual

### Propuesta

La UI debería diferenciar visualmente al menos estos tipos:

1. **Consulta ERP**
2. **Resumen**
3. **Aclaración requerida**
4. **Error funcional**
5. **Confirmación de acción**

### Ejemplos de badges

- `Consulta ERP`
- `Resumen`
- `Aclaración`
- `Error`
- `Acción completada`

### Uso

No hace falta sobrecargar de colores. Basta con un badge discreto y consistente.

---

## 5) Acciones rápidas por respuesta

### Problema actual

El sistema responde, pero rara vez invita al siguiente paso.

### Propuesta

Toda respuesta relevante debería evaluar si puede ofrecer entre 1 y 3 acciones rápidas.

### Ejemplo para pickings

- `Abrir pickings`
- `Ver solo borrador`
- `Ver cancelados`

### Ejemplo para stock negativo

- `Abrir productos`
- `Ver movimientos`
- `Exportar CSV`

### Ejemplo para facturas pendientes

- `Abrir facturas`
- `Ver vencidas`
- `Filtrar por cliente`

### Regla práctica

Las acciones deben:

- depender del contexto
- ser pocas
- llevar a algo real en Odoo
- no ser decorativas

---

## 6) Campo de entrada

### Problema actual

El input todavía se ve básico y un poco perdido dentro del espacio general.

### Propuesta

Mejorar el footer del chat para que se sienta más sólido.

### Cambios sugeridos

- hacer el input ligeramente más alto
- mantener placeholder útil
- bajar el protagonismo del botón `Limpiar`
- mantener `Enviar` como acción principal
- agregar sugerencias rápidas debajo del input cuando aplique

### Placeholder sugerido

- `Haz una consulta sobre este documento...`
- `Pregúntame sobre esta compra, sus pickings o sus facturas relacionadas...`

---

## 7) Densidad visual y layout

### Problema actual

Hay demasiado espacio vacío y el contenido útil no domina la pantalla.

### Propuesta

Aumentar densidad visual útil sin recargar.

### Recomendaciones

- dar más protagonismo al contenedor del chat
- mejorar padding interno de respuestas
- reducir sensación de lienzo vacío
- hacer que las cards de respuesta ocupen mejor el ancho

### Regla

El espacio debe ayudar a respirar, no a parecer que el sistema todavía no cargó nada.

---

## 8) Aclaraciones guiadas

### Propuesta

Cuando falte precisión, no pedir siempre texto libre. Usar opciones rápidas.

### Ejemplo

**Aclaración**  
¿Cómo quieres verlo?

- `Solo borrador`
- `Solo cancelados`
- `Todos`

### Beneficio

- menos fricción
- menos ambigüedad
- respuestas más rápidas
- mejor UX para usuarios no técnicos

---

## 9) Latencia y percepción

### Problema actual

Mostrar `6549 ms` crudo puede hacer ver lenta la UI, aunque el sistema esté funcionando bien.

### Propuesta

Separar información de producto de información técnica.

### Sugerencia

- visible normal: `● En línea`
- opcional: `Procesado en ~6.5 s`
- técnico/debug: `6549 ms`

Así la interfaz no parece panel de monitoreo.

---

## Mockup textual sugerido

```text
┌ AI Assistant ─────────────────────────────────────────────── ● En línea
│ Compra #176 · Proveedor: ACME · Estado: Confirmada · 2 pickings
├───────────────────────────────────────────────────────────────────────────
│ [Ver pickings] [Recepciones pendientes] [Recepciones canceladas]
│ [Facturas del proveedor] [Productos pendientes]
├───────────────────────────────────────────────────────────────────────────
│ Tú · 17:44
│ ¿Cuáles son?
│
│ Consulta ERP
│ Pickings asociados: 2
│
│ ID    Nombre            Estado
│ 211   EXPRC/IN/00096    Hecho
│ 210   EXPRC/IN/00095    Cancelado
│
│ [Abrir pickings] [Ver solo borrador] [Ver cancelados]
├───────────────────────────────────────────────────────────────────────────
│ Haz una consulta sobre este documento...
│                                                [Limpiar] [Enviar]
└───────────────────────────────────────────────────────────────────────────
```

---

## Prioridades recomendadas para implementación

### Prioridad 1
**Pasar respuestas de texto libre a cards de resultado estructuradas**

Impacto más alto en percepción de calidad.

### Prioridad 2
**Hacer chips contextuales por modelo activo**

Eso hace que el copiloto se sienta realmente integrado a Odoo.

### Prioridad 3
**Agregar acciones rápidas contextuales**

Sube mucho el valor operativo.

### Prioridad 4
**Mejorar header con contexto más útil para negocio**

Más claridad y confianza.

### Prioridad 5
**Reducir sensación de espacio muerto y mejorar el input**

Pulido visual general.

---

## Recomendación final para desarrollo

No rediseñar todo de golpe.

### Fase 1
- header más útil
- chips contextuales
- cards de resultado

### Fase 2
- acciones rápidas
- aclaraciones guiadas
- mejor input/footer

### Fase 3
- refinamiento visual
- badges de tipo de respuesta
- mejora de estados y errores

---

## Conclusión

La UI actual ya mejoró y dejó de verse como una caja de chat básica, pero todavía está en una etapa intermedia: **funcional, ordenada, pero aún no convincente como copiloto ERP premium**.

La mejora con mayor impacto no es solo estética. Es estructural:

- respuestas más tipo sistema
- chips verdaderamente contextuales
- acciones rápidas
- contexto de negocio más claro

Con esos cambios, la percepción del producto sube bastante sin necesidad de rehacer toda la interfaz.
