# Backlog inicial de issues — Odoo AI Copilot

Este documento contiene una plantilla de issues lista para copiar y pegar en GitHub.

---

## 1) Formalizar los modos de respuesta del agente

**Título**

Formalizar los modos de respuesta del agente

**Problema**

Actualmente el agente puede responder por distintas rutas, pero no siempre queda explícito si la respuesta fue determinística, guiada por tools, una aclaración o un fallback. Eso dificulta el debugging, la trazabilidad y el renderizado correcto en frontend.

**Objetivo**

Definir una clasificación clara de modos de respuesta para que el backend, frontend y logs hablen el mismo idioma.

**Alcance**

- Crear enum o constantes para modos de respuesta
- Clasificar cada salida del agente en un modo formal
- Exponer `answer_mode` en la respuesta
- Registrar el modo en logs

**Modos sugeridos**

- `deterministic`
- `tool_guided`
- `clarification_required`
- `fallback_explanatory`

**Criterios de aceptación**

- Toda respuesta del backend incluye `answer_mode`
- Las consultas simples de negocio no caen al LLM innecesariamente
- El log muestra qué ruta se eligió
- El frontend puede distinguir el tipo de respuesta

**Fuera de alcance**

- Rediseño completo de UI
- Nuevos tools
- Nuevos casos de negocio

**Labels sugeridos**

- `backend`
- `agent`
- `high-priority`

**Prioridad**

Alta

**Estimación**

M

---

## 2) Estandarizar el contrato de respuesta entre backend y frontend

**Título**

Estandarizar el contrato de respuesta entre backend y frontend

**Problema**

La UI no debería depender de texto libre para inferir si una respuesta es una tabla, una aclaración o un error. Eso vuelve frágil el render y hace difícil evolucionar el producto.

**Objetivo**

Definir una estructura de respuesta estable y reutilizable.

**Alcance**

- Crear schema de salida común
- Tipar respuestas normales, aclaraciones y errores
- Incluir metadata útil para render y debugging

**Estructura sugerida**

- `answer`
- `answer_mode`
- `answer_type`
- `needs_clarification`
- `clarification_options`
- `actions`
- `metadata`

**Criterios de aceptación**

- Todas las respuestas cumplen el mismo contrato
- El frontend puede renderizar resumen, tabla, error o aclaración
- Los errores tienen formato consistente
- La metadata básica está disponible

**Fuera de alcance**

- Streaming
- Exportaciones complejas
- Dashboard de métricas

**Labels sugeridos**

- `backend`
- `frontend`
- `api`
- `high-priority`

**Prioridad**

Alta

**Estimación**

M

---

## 3) Reducir el uso del LLM en consultas de negocio determinísticas

**Título**

Reducir el uso del LLM en consultas de negocio determinísticas

**Problema**

Consultas como conteos, agrupaciones y filtros exactos no deberían depender de razonamiento libre del modelo. Eso sube costo, latencia y riesgo de respuestas poco confiables.

**Objetivo**

Forzar que los casos de negocio estructurados se resuelvan por tools determinísticas.

**Alcance**

- Identificar intents frecuentes
- Mapear cada intent a la tool correcta
- Reducir o bloquear uso del LLM donde no aporta valor
- Medir mejora en tokens y latencia

**Criterios de aceptación**

- Top clientes usa `read_group`
- Conteos usan `count`
- Búsquedas exactas usan `search/read`
- Se reduce el uso de tokens en consultas repetibles

**Fuera de alcance**

- Resúmenes narrativos
- Explicaciones de negocio complejas
- Soporte multimodal

**Labels sugeridos**

- `backend`
- `agent`
- `performance`

**Prioridad**

Alta

**Estimación**

M

---

## 4) Implementar allowlist de modelos y campos permitidos

**Título**

Implementar allowlist de modelos y campos permitidos

**Problema**

Un copiloto conectado a Odoo no debería tener libertad abierta sobre todos los modelos y campos. Eso aumenta el riesgo funcional y de exposición de datos.

**Objetivo**

Definir una política explícita de acceso para el agente.

**Alcance**

- Crear allowlist por modelo
- Crear allowlist por campos
- Crear denylist de campos sensibles
- Integrar validación en tools

**Criterios de aceptación**

- Solo se consultan modelos autorizados
- Campos sensibles quedan bloqueados
- Consultas inválidas fallan de forma controlada
- Existe configuración base centralizada

**Fuera de alcance**

- Control fino por rol funcional
- Escritura asistida
- Auditoría histórica avanzada

**Labels sugeridos**

- `security`
- `backend`
- `high-priority`

**Prioridad**

Alta

**Estimación**

M

---

## 5) Asegurar el scope por usuario, compañía y contexto activo

**Título**

Asegurar el scope por usuario, compañía y contexto activo

**Problema**

Si el contexto no se propaga bien desde Odoo al servicio IA, el agente puede consultar o responder con datos fuera del alcance correcto.

**Objetivo**

Garantizar que cada request lleve y respete su contexto real.

**Alcance**

- Revisar payload enviado desde Odoo
- Propagar `user_id`, `company_id`, `allowed_company_ids`
- Propagar `active_model` y `active_id`
- Validar aplicación del scope en tools

**Criterios de aceptación**

- Cada request incluye contexto suficiente
- Las consultas respetan multi-company
- Las respuestas se generan con el documento/contexto correcto
- Hay tests de scope mínimo

**Fuera de alcance**

- Gestión avanzada de delegación de permisos
- Compartición entre usuarios
- Escenarios multi-tenant complejos

**Labels sugeridos**

- `security`
- `backend`
- `context`
- `high-priority`

**Prioridad**

Alta

**Estimación**

M

---

## 6) Endurecer la comunicación entre Odoo y FastAPI

**Título**

Endurecer la comunicación entre Odoo y FastAPI

**Problema**

Si los endpoints internos no validan bien autenticación, payload y timeouts, el sistema queda frágil y difícil de operar.

**Objetivo**

Volver más segura y robusta la comunicación entre Odoo y el servicio IA.

**Alcance**

- Validar token interno
- Tipar payload de entrada
- Definir timeouts
- Normalizar errores HTTP y funcionales

**Criterios de aceptación**

- El endpoint valida autenticación interna
- El payload se valida por schema
- Los errores devuelven estructura consistente
- Los timeouts son configurables por entorno

**Fuera de alcance**

- API pública
- Rotación automática de secretos
- Rate limiting distribuido

**Labels sugeridos**

- `security`
- `backend`
- `api`

**Prioridad**

Alta

**Estimación**

S/M

---

## 7) Separar memoria en contexto activo, memoria corta y preferencias

**Título**

Separar memoria en contexto activo, memoria corta y preferencias

**Problema**

Guardar todo en una sola memoria termina mezclando contexto de pantalla, historial conversacional y preferencias persistentes.

**Objetivo**

Dividir la memoria en capas con responsabilidades claras.

**Alcance**

- Diseñar 3 capas de memoria
- Adaptar `memory_store` / `session_memory`
- Definir qué guarda cada capa
- Documentar reglas de uso

**Capas sugeridas**

- contexto activo
- memoria conversacional corta
- preferencias persistentes

**Criterios de aceptación**

- Cada capa tiene propósito definido
- Los follow-ups usan la capa correcta
- No se arrastra información irrelevante
- La estructura queda documentada

**Fuera de alcance**

- Memoria semántica avanzada
- Recuperación por embeddings
- Personalización multiusuario sofisticada

**Labels sugeridos**

- `memory`
- `backend`
- `agent`

**Prioridad**

Alta

**Estimación**

M

---

## 8) Implementar TTL y reglas de reinicio de memoria

**Título**

Implementar TTL y reglas de reinicio de memoria

**Problema**

La memoria conversacional puede volverse obsoleta y causar respuestas equivocadas si no expira o no se reinicia al cambiar contexto.

**Objetivo**

Definir cuándo la memoria sigue siendo válida y cuándo debe descartarse.

**Alcance**

- Agregar TTL a memoria corta
- Reiniciar memoria ante cambio de compañía
- Reiniciar o recalcular ante cambio de documento o módulo
- Registrar eventos de reset

**Criterios de aceptación**

- La memoria conversacional expira
- Los cambios de contexto reinician lo necesario
- Los logs registran reinicios relevantes
- Se reducen follow-ups inconsistentes

**Fuera de alcance**

- UI de gestión de memoria
- Persistencia de largo plazo
- Sincronización entre dispositivos

**Labels sugeridos**

- `memory`
- `backend`
- `context`

**Prioridad**

Alta

**Estimación**

S/M

---

## 9) Mejorar la resolución de follow-ups relacionales

**Título**

Mejorar la resolución de follow-ups relacionales

**Problema**

Preguntas como “y de ese cliente”, “solo las vencidas” o “del mes pasado” pueden fallar si la entidad previa o el filtro implícito no se resuelve bien.

**Objetivo**

Hacer que los follow-ups sean más predecibles y seguros.

**Alcance**

- Revisar extracción de última entidad
- Revisar composición de filtros adicionales
- Detectar ambigüedad
- Pedir aclaración cuando corresponda

**Criterios de aceptación**

- El agente reconoce mejor la entidad previa
- No mezcla cliente, documento o período sin validación
- Los casos ambiguos disparan aclaración
- Existe set de pruebas de follow-up

**Fuera de alcance**

- Resumen multi-turn avanzado
- Memoria semántica compleja
- Coreference resolution sofisticado

**Labels sugeridos**

- `memory`
- `agent`
- `tests`

**Prioridad**

Media/Alta

**Estimación**

M

---

## 10) Implementar logging estructurado por request

**Título**

Implementar logging estructurado por request

**Problema**

Sin logs consistentes es difícil entender por qué el agente respondió algo, qué tools usó o dónde falló.

**Objetivo**

Poder reconstruir cada request de manera confiable.

**Alcance**

- Generar `request_id`
- Estandarizar logs JSON
- Registrar ruta, tools, latencia y error
- Incorporar contexto mínimo útil

**Campos sugeridos**

- `request_id`
- `session_id`
- `user_id`
- `company_id`
- `question`
- `route_selected`
- `tools_used`
- `latency_total_ms`
- `tokens_input`
- `tokens_output`
- `success`
- `error_code`

**Criterios de aceptación**

- Cada request queda identificado
- Se puede rastrear la ruta tomada
- Los errores quedan clasificados
- La latencia total queda registrada

**Fuera de alcance**

- Dashboard visual
- Alertas automáticas
- Observabilidad distribuida completa

**Labels sugeridos**

- `observability`
- `backend`
- `high-priority`

**Prioridad**

Alta

**Estimación**

S/M

---

## 11) Crear benchmark funcional del copiloto

**Título**

Crear benchmark funcional del copiloto

**Problema**

Hoy es difícil medir si el agente realmente mejora o si un cambio rompe casos importantes.

**Objetivo**

Definir un set de preguntas reales para evaluación repetible.

**Alcance**

- Crear carpeta `evals/` o similar
- Definir al menos 20 consultas reales
- Asociar modo esperado y tool esperada
- Guardar baseline inicial

**Criterios de aceptación**

- Existe set de benchmark versionado
- Cada consulta tiene resultado esperado a nivel de comportamiento
- Se puede comparar antes/después de cambios importantes
- Se registran métricas mínimas

**Fuera de alcance**

- Evaluación automática con LLM judge
- Benchmarks externos
- Evaluación multimodal

**Labels sugeridos**

- `tests`
- `observability`
- `quality`

**Prioridad**

Alta

**Estimación**

M

---

## 12) Agregar tests unitarios e integración para componentes críticos

**Título**

Agregar tests unitarios e integración para componentes críticos

**Problema**

El proyecto depende demasiado de pruebas manuales, lo que hace fácil introducir regresiones.

**Objetivo**

Cubrir los componentes más sensibles del copiloto.

**Alcance**

- Tests de normalización de args
- Tests de validación de schema
- Tests de memoria
- Tests de clasificación de modo
- Tests de follow-up
- Tests de scope multi-company

**Criterios de aceptación**

- Existe suite mínima ejecutable
- Los casos críticos quedan cubiertos
- Las regresiones básicas se detectan automáticamente
- Hay documentación mínima para correr tests

**Fuera de alcance**

- Cobertura total
- Tests E2E completos del frontend
- Stress testing

**Labels sugeridos**

- `tests`
- `backend`
- `quality`

**Prioridad**

Alta

**Estimación**

M/L

---

## 13) Adaptar el frontend a respuestas estructuradas

**Título**

Adaptar el frontend a respuestas estructuradas

**Problema**

La UI actual depende demasiado de texto plano y eso limita la experiencia del copiloto.

**Objetivo**

Permitir que la interfaz renderice distintos tipos de respuesta de forma consistente.

**Alcance**

- Soporte para resumen
- Soporte para tabla
- Soporte para aclaración
- Soporte para error
- Soporte para confirmación

**Criterios de aceptación**

- El frontend procesa `answer_type`
- Las aclaraciones se renderizan como opciones rápidas
- Las tablas se muestran de forma legible
- Los errores se presentan de manera útil

**Fuera de alcance**

- Rediseño visual completo
- Streaming
- Side panel avanzado

**Labels sugeridos**

- `frontend`
- `ux`
- `chat`

**Prioridad**

Media/Alta

**Estimación**

M

---

## 14) Mostrar contexto activo y tipo de respuesta en la interfaz

**Título**

Mostrar contexto activo y tipo de respuesta en la interfaz

**Problema**

El usuario necesita entender sobre qué documento, cliente o módulo está respondiendo el copiloto.

**Objetivo**

Subir la confianza visual del sistema mostrando contexto y badges.

**Alcance**

- Mostrar contexto activo en el header
- Mostrar badge de tipo de respuesta
- Mostrar metadata mínima relevante

**Criterios de aceptación**

- El usuario ve contexto activo en pantalla
- El usuario puede distinguir si es consulta, aclaración o resumen
- La UI transmite mejor confianza y control

**Fuera de alcance**

- Historial lateral completo
- Analytics de uso en UI
- Configuración personalizada del usuario

**Labels sugeridos**

- `frontend`
- `ux`

**Prioridad**

Media

**Estimación**

S/M

---

## 15) Agregar acciones rápidas contextuales en las respuestas

**Título**

Agregar acciones rápidas contextuales en las respuestas

**Problema**

El copiloto pierde valor si responde bien pero no ayuda al usuario a actuar.

**Objetivo**

Convertir la respuesta en un siguiente paso útil dentro de Odoo.

**Alcance**

- Definir acciones según tipo de resultado
- Renderizar botones o chips
- Conectar acciones con flujo real de Odoo

**Ejemplos**

- Ver detalle
- Abrir productos
- Ver movimientos
- Exportar CSV
- Abrir pedido
- Ver cliente

**Criterios de aceptación**

- Las acciones dependen del contexto y del resultado
- No son botones genéricos sin uso real
- Mejoran el flujo de trabajo del usuario

**Fuera de alcance**

- Acciones de escritura críticas
- Automatizaciones complejas
- Flujos multi-paso grandes

**Labels sugeridos**

- `frontend`
- `ux`
- `product`

**Prioridad**

Media

**Estimación**

M

---

## 16) Mejorar README técnico y de producto

**Título**

Mejorar README técnico y de producto

**Problema**

El README actual puede no reflejar con claridad el problema que resuelve el proyecto, su arquitectura y los límites reales del sistema.

**Objetivo**

Explicar mejor el problema, la solución, la arquitectura y los casos de uso.

**Alcance**

- Mejorar introducción del proyecto
- Documentar arquitectura
- Documentar flujo de decisión del agente
- Agregar casos de uso reales
- Agregar límites y consideraciones

**Criterios de aceptación**

- README más claro y orientado a producto
- Arquitectura entendible por terceros
- Casos de uso visibles
- Setup básico bien explicado

**Labels sugeridos**

- `documentation`
- `product`

**Prioridad**

Media

**Estimación**

S

---

## 17) Documentar variables de entorno y configuración

**Título**

Documentar variables de entorno y configuración

**Problema**

La configuración del sistema puede volverse difícil de reproducir si no están claras las variables necesarias y sus valores esperados.

**Objetivo**

Reducir fricción para setup y despliegue.

**Alcance**

- Listar variables necesarias
- Explicar propósito de cada variable
- Documentar defaults seguros
- Separar configuración dev/prod cuando aplique

**Criterios de aceptación**

- Existe sección clara de configuración
- El setup básico puede reproducirse sin adivinar variables
- Queda claro qué variables son sensibles

**Labels sugeridos**

- `documentation`
- `devops`

**Prioridad**

Media

**Estimación**

S

---

## 18) Crear demo guiada por casos de uso

**Título**

Crear demo guiada por casos de uso

**Problema**

Sin una demo guiada, el valor del copiloto puede perderse ante stakeholders, clientes o reclutadores.

**Objetivo**

Tener una demo limpia para portafolio, stakeholders o clientes.

**Alcance**

- Definir 3 a 5 flujos demo
- Preparar datos de ejemplo
- Documentar pasos de demostración
- Destacar valor de negocio y decisiones técnicas

**Criterios de aceptación**

- Existe demo reproducible
- Los flujos cubren inventario, ventas y/o facturación
- La demo muestra contexto, respuesta y acción

**Labels sugeridos**

- `product`
- `demo`

**Prioridad**

Media

**Estimación**

S/M

---

## Orden recomendado de ejecución

### Sprint 1
- 1) Formalizar los modos de respuesta del agente
- 2) Estandarizar el contrato de respuesta entre backend y frontend
- 4) Implementar allowlist de modelos y campos permitidos
- 5) Asegurar el scope por usuario, compañía y contexto activo

### Sprint 2
- 6) Endurecer la comunicación entre Odoo y FastAPI
- 7) Separar memoria en contexto activo, memoria corta y preferencias
- 8) Implementar TTL y reglas de reinicio de memoria
- 10) Implementar logging estructurado por request

### Sprint 3
- 3) Reducir el uso del LLM en consultas de negocio determinísticas
- 9) Mejorar la resolución de follow-ups relacionales
- 11) Crear benchmark funcional del copiloto
- 12) Agregar tests unitarios e integración para componentes críticos

### Sprint 4
- 13) Adaptar el frontend a respuestas estructuradas
- 14) Mostrar contexto activo y tipo de respuesta en la interfaz
- 15) Agregar acciones rápidas contextuales en las respuestas
- 16) Mejorar README técnico y de producto

---

## Labels recomendados

- `backend`
- `frontend`
- `agent`
- `memory`
- `security`
- `context`
- `tests`
- `observability`
- `ux`
- `product`
- `documentation`
- `api`
- `performance`
- `high-priority`
