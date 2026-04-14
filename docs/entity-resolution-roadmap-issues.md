# Roadmap de resolución de entidad conversacional — Issues propuestas

Este documento traduce el problema de contexto/memoria detectado en el copiloto a un backlog accionable de GitHub Issues.

Caso base observado:
- El usuario cambió explícitamente de una venta a una compra.
- El agente resolvió bien la compra explícita.
- El follow-up `tiene alguna factura?` reutilizó memoria previa de venta.
- Resultado: se consultó una factura de la venta `DCN 0426-0056` en vez de la compra `PO-I-10-00015`.

Objetivo:
Blindar la **resolución de entidad conversacional** para evitar errores silenciosos en follow-ups multi-turno.

---

## Epic 1 — Promoción correcta de entidad explícita

### Issue 1 — Promover entidad explícita resuelta como entidad primaria

**Problema**
Cuando el usuario menciona explícitamente un documento (por ejemplo, `PO-I-10-00015`) y este se resuelve correctamente, el sistema no siempre actualiza la entidad principal de la conversación.

**Objetivo**
Toda entidad explícita resuelta con éxito debe poder sobrescribir la entidad primaria conversacional.

**Alcance**
- Detectar referencias explícitas a documentos.
- Actualizar `primary_entity` cuando la resolución sea exitosa.
- Persistir `model`, `id`, `display_name`, `source` y `timestamp`.

**Criterios de aceptación**
- Si el usuario menciona una compra explícita y esta se resuelve, la entidad primaria pasa a ser esa compra.
- La entidad explícita gana sobre memoria vieja y sobre el contexto visual atrasado.
- El log registra el cambio de entidad.

**Subtareas**
- Extraer identificadores explícitos de documento.
- Crear helper `promote_primary_entity(...)`.
- Integrar promoción tras resolución exitosa.
- Loggear entidad previa y entidad nueva.

**Prioridad**
Alta

**Estimación**
M

**Labels sugeridos**
- `backend`
- `memory`
- `agent`
- `high-priority`

---

### Issue 2 — No depender ciegamente de `ui_active_model` cuando exista entidad explícita reciente

**Problema**
El UI puede seguir apuntando a un modelo viejo mientras la conversación ya cambió a otra entidad explícita.

**Objetivo**
Dar prioridad a la entidad explícita reciente sobre `ui_active_model` y `ui_active_id` cuando exista evidencia fuerte.

**Alcance**
- Definir regla de precedencia entre memoria y contexto UI.
- Aplicar override cuando el usuario haya mencionado un documento explícito recientemente.

**Criterios de aceptación**
- El contexto visual no pisa una entidad explícita reciente.
- La ruta seleccionada usa la entidad conversacional correcta.
- Queda trazado cuándo se usó override sobre el contexto UI.

**Subtareas**
- Definir precedencia de fuentes de entidad.
- Implementar `entity_source_priority`.
- Agregar log `ui_context_overridden`.

**Prioridad**
Alta

**Estimación**
S/M

**Labels sugeridos**
- `backend`
- `context`
- `memory`

---

## Epic 2 — Memoria conversacional robusta

### Issue 3 — Introducir `last_explicit_entity` y separar fuentes de memoria

**Problema**
Hoy la memoria conversacional no distingue con suficiente claridad si una entidad vino del UI, de una inferencia o de una mención explícita del usuario.

**Objetivo**
Separar la memoria por origen para que los follow-ups usen la referencia correcta.

**Alcance**
- Agregar `last_explicit_entity`.
- Agregar `last_ui_entity`.
- Agregar `last_inferred_entity` o equivalente.
- Registrar `source` por entidad.

**Criterios de aceptación**
- El sistema puede identificar cuál fue la última entidad explícita válida.
- Los follow-ups priorizan correctamente la fuente de memoria.
- La estructura queda documentada.

**Subtareas**
- Redefinir esquema de memoria.
- Migrar estructura actual.
- Documentar campos de entidad y sus fuentes.

**Prioridad**
Alta

**Estimación**
M

**Labels sugeridos**
- `memory`
- `backend`
- `agent`

---

### Issue 4 — Definir prioridad formal para resolución de follow-ups

**Problema**
Los follow-ups relacionales pueden elegir una entidad incorrecta si no existe una regla estable de precedencia.

**Objetivo**
Formalizar la regla de resolución para follow-ups cortos como `tiene factura`, `tiene picking`, `tiene pagos`.

**Regla sugerida**
`last_explicit_entity > primary_entity > last_ui_entity > inferred_entity`

**Alcance**
- Implementar prioridad de entidades.
- Centralizar la resolución de entidad para follow-ups.
- Registrar la entidad candidata elegida y las descartadas.

**Criterios de aceptación**
- Los follow-ups usan primero la entidad explícita reciente.
- El log muestra por qué entidad se resolvió el follow-up.
- La lógica es reutilizable para otras relaciones además de factura.

**Subtareas**
- Crear resolver central `resolve_followup_entity(...)`.
- Registrar candidatos y razón de selección.
- Cubrir con tests básicos.

**Prioridad**
Alta

**Estimación**
M

**Labels sugeridos**
- `memory`
- `agent`
- `backend`
- `high-priority`

---

## Epic 3 — Guardrails para follow-ups ambiguos

### Issue 5 — Detectar cambio reciente de tipo de entidad y bloquear resolución ciega

**Problema**
Cuando el usuario cambia de `sale.order` a `purchase.order`, un follow-up ambiguo no debería resolverse automáticamente sin validar el contexto.

**Objetivo**
Detectar cambios recientes de tipo de entidad y evitar errores silenciosos.

**Alcance**
- Detectar transiciones de tipo de entidad entre turnos recientes.
- Marcar conflictos de contexto.
- Reducir confianza del follow-up automático.

**Criterios de aceptación**
- Si hubo cambio reciente de venta a compra, el sistema no reutiliza automáticamente la entidad vieja.
- Los conflictos de contexto quedan visibles en métricas/logs.

**Subtareas**
- Agregar comparación de tipo de entidad reciente.
- Implementar `entity_conflict_detected`.
- Integrar con el resolver de follow-ups.

**Prioridad**
Alta

**Estimación**
S/M

**Labels sugeridos**
- `memory`
- `agent`
- `context`

---

### Issue 6 — Pedir aclaración cuando el follow-up sea ambiguo entre entidades recientes

**Problema**
Un follow-up corto como `tiene alguna factura?` puede referirse a más de una entidad reciente válida.

**Objetivo**
Pedir aclaración cuando el sistema no tenga confianza suficiente para resolver el follow-up de forma automática.

**Ejemplo esperado**
`¿Te refieres a la factura de la compra PO-I-10-00015 o a la venta DCN 0426-0056?`

**Alcance**
- Definir umbral de confianza para follow-ups.
- Construir respuesta de aclaración con entidades candidatas.
- Integrar en la ruta de memoria/follow-up.

**Criterios de aceptación**
- Los casos ambiguos no se resuelven silenciosamente.
- La aclaración menciona entidades concretas y entendibles.
- El sistema registra que la respuesta fue una aclaración.

**Subtareas**
- Diseñar score simple de confianza.
- Generar payload de aclaración.
- Ajustar UI para mostrar opciones si aplica.

**Prioridad**
Alta

**Estimación**
M

**Labels sugeridos**
- `backend`
- `agent`
- `ux`
- `high-priority`

---

## Epic 4 — Semántica correcta por relación

### Issue 7 — Resolver facturas según el tipo de documento origen

**Problema**
La relación `factura` no significa lo mismo para ventas y compras. Si no se valida semántica por tipo, el agente puede consultar el universo incorrecto.

**Objetivo**
Aplicar reglas distintas para facturas de venta y de compra.

**Reglas sugeridas**
- `sale.order` → `move_type in ('out_invoice', 'out_refund')`
- `purchase.order` → `move_type in ('in_invoice', 'in_refund')`

**Alcance**
- Ajustar resolutores relacionales de facturas.
- Agregar filtro de `move_type` según tipo de documento.
- Mantener respuesta fiel al origen consultado.

**Criterios de aceptación**
- Una compra no devuelve facturas de venta.
- Una venta no devuelve facturas de compra.
- Los logs muestran qué tipo de factura se consultó.

**Subtareas**
- Crear mapper `document_model -> invoice_move_types`.
- Actualizar dominio en consultas relacionales.
- Agregar tests para compra/venta.

**Prioridad**
Alta

**Estimación**
S/M

**Labels sugeridos**
- `backend`
- `agent`
- `domain-logic`

---

## Epic 5 — Observabilidad y regresión

### Issue 8 — Mejorar logs y métricas de selección de entidad

**Problema**
Hoy es difícil reconstruir por qué el agente eligió una entidad concreta en follow-ups complejos.

**Objetivo**
Hacer visible la lógica de selección de entidad en logs y métricas.

**Campos sugeridos**
- `entity_source_used`
- `entity_candidates`
- `entity_conflict_detected`
- `followup_confidence`
- `clarification_reason`
- `ui_context_overridden`

**Criterios de aceptación**
- Los logs muestran entidad elegida, entidad descartada y fuente.
- Las métricas reflejan cuándo hubo conflicto o aclaración.
- Se puede depurar el caso sin releer toda la conversación.

**Subtareas**
- Extender payload de métricas.
- Agregar logs estructurados por selección de entidad.
- Documentar campos nuevos.

**Prioridad**
Media/Alta

**Estimación**
S

**Labels sugeridos**
- `observability`
- `backend`
- `quality`

---

### Issue 9 — Crear tests de regresión para cambios de entidad multi-turno

**Problema**
Sin tests multi-turno, este tipo de bug puede reaparecer fácilmente en otra ruta.

**Objetivo**
Cubrir la familia de errores de resolución de entidad conversacional.

**Casos mínimos**
1. Venta → follow-up de factura de venta.
2. Compra explícita → productos → follow-up de factura de compra.
3. Venta → compra explícita → follow-up ambiguo.
4. Dos entidades recientes de distinto tipo → pedir aclaración.

**Criterios de aceptación**
- Existe una suite de regresión para multi-turno.
- El caso `PO-I-10-00015 -> tiene alguna factura?` queda cubierto.
- Las pruebas validan entidad elegida y dominio final.

**Subtareas**
- Armar fixtures o mocks de conversación.
- Validar `route_selected`, `domain_used` y `entity_source_used`.
- Integrar en CI si aplica.

**Prioridad**
Alta

**Estimación**
M

**Labels sugeridos**
- `tests`
- `backend`
- `quality`
- `high-priority`

---

## Epic 6 — UX de aclaración y confianza

### Issue 10 — Mostrar aclaraciones y origen de resolución de forma más clara en UI

**Problema**
Cuando el sistema duda entre dos entidades, la UI debe ayudar a resolverlo en vez de ocultar la ambigüedad.

**Objetivo**
Mejorar la experiencia de aclaración y la confianza del usuario.

**Alcance**
- Renderizar aclaraciones con opciones rápidas.
- Mostrar badges o microcopy útil cuando la respuesta venga de memoria o de contexto explícito.

**Criterios de aceptación**
- La UI muestra preguntas de aclaración cuando aplica.
- El usuario entiende mejor sobre qué documento respondió el copiloto.
- La ambigüedad deja de ser silenciosa.

**Subtareas**
- Definir payload de aclaración para frontend.
- Agregar estado visual para `Aclaración`.
- Mostrar contexto usado en respuestas relacionales.

**Prioridad**
Media

**Estimación**
M

**Labels sugeridos**
- `frontend`
- `ux`
- `agent`

---

## Orden recomendado de ejecución

### Sprint 1
1. Promover entidad explícita resuelta como entidad primaria
2. No depender ciegamente de `ui_active_model` cuando exista entidad explícita reciente
3. Introducir `last_explicit_entity` y separar fuentes de memoria
4. Resolver facturas según el tipo de documento origen

### Sprint 2
5. Definir prioridad formal para resolución de follow-ups
6. Detectar cambio reciente de tipo de entidad y bloquear resolución ciega
7. Mejorar logs y métricas de selección de entidad
8. Crear tests de regresión para cambios de entidad multi-turno

### Sprint 3
9. Pedir aclaración cuando el follow-up sea ambiguo entre entidades recientes
10. Mostrar aclaraciones y origen de resolución de forma más clara en UI

---

## Criterio de cierre global

Este roadmap se considera bien implementado cuando:
- una entidad explícita reciente siempre puede sobrescribir memoria vieja,
- el agente no mezcla compras y ventas en follow-ups relacionales,
- los casos ambiguos piden aclaración,
- los logs explican por qué se eligió una entidad,
- y el caso base observado queda cubierto por tests de regresión.
