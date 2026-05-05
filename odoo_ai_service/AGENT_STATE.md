# Estado Actual del Agente

## Objetivo

Este documento describe el estado real actual del agente de `odoo_ai_service` a partir del código, la configuración y los logs observados. No describe solo la arquitectura ideal, sino la implementación efectiva hoy.

## Resumen Ejecutivo

El agente ya no es solo un wrapper simple del LLM. Actualmente combina:

- memoria estructurada por sesión
- resolución de follow-ups directos
- resolución de follow-ups relacionales
- capa de aclaración para consultas ambiguas
- validación semántica y de schema
- tools controladas para consultar Odoo

Esto ya lo acerca a un agente híbrido serio. Sin embargo, todavía hay áreas donde depende demasiado del LLM para consultas que deberían resolverse de forma determinística, y la cobertura de tests aún parece limitada.

## Estructura Real Relevante

### AI Service

- `odoo_ai_service/main.py`
  Entry point FastAPI.

- `odoo_ai_service/agents/assistant_agent.py`
  Wrapper que exporta `ask_agent`.

- `odoo_ai_service/agents/agent/assistant_agent.py`
  Núcleo real del agente.

- `odoo_ai_service/agents/agent/reference_resolver.py`
  Resolución de follow-ups por entidad y follow-ups relacionales.

- `odoo_ai_service/agents/agent/clarification_resolver.py`
  Detección y resolución de aclaraciones pendientes.

- `odoo_ai_service/agents/agent/memory_store.py`
  Lectura y escritura lógica de memoria estructurada.

- `odoo_ai_service/agents/agent/execution/tool_executor.py`
  Ejecutor de tools.

- `odoo_ai_service/tools/odoo_get_tool.py`
  Cliente HTTP hacia Odoo para `search`, `read`, `read_group`, `schema`.

- `odoo_ai_service/tools/tool_definitions.py`
  Definiciones de tools expuestas al LLM.

- `odoo_ai_service/agents/agent/intents/intent_matcher.py`
  Detección de intención.

- `odoo_ai_service/agents/agent/intents/intent_catalog.py`
  Catálogo de intenciones.

- `odoo_ai_service/agents/agent/metrics/telemetry.py`
  Cálculo de métricas y warnings.

### Módulo Odoo

- `custom_addons/odoo_ai_assistant/controllers/chat_controller.py`
  Controller que recibe la consulta del frontend y llama al AI service.

- `custom_addons/odoo_ai_assistant/models/model.py`
  Historial textual de chat en `ai.chat`.

- `custom_addons/odoo_ai_assistant/models/session_memory.py`
  Persistencia de memoria estructurada por sesión.

- `custom_addons/odoo_ai_assistant/static/src/js/chat.js`
  Frontend del chat, historial local y `chat_session_key`.

- `custom_addons/odoo_ai_assistant/__manifest__.py`
  Manifest del módulo.

## Flujo Real de una Consulta

### Flujo general

1. El usuario escribe una pregunta en Odoo.
2. El frontend envía:
   - `question`
   - `chat_session_key`
   - historial corto local
3. El controller de Odoo:
   - identifica usuario
   - recupera memoria estructurada de sesión
   - recupera historial de servidor
   - arma el payload
4. Odoo llama a `odoo_ai_service /ask`.
5. El AI service ejecuta `ask_agent(...)`.
6. El agente intenta, en este orden:
   - resolver aclaración pendiente
   - pedir nueva aclaración si hace falta
   - resolver follow-up por memoria
   - resolver follow-up relacional
   - ejecutar ruta determinística
   - usar LLM + tools
7. Devuelve:
   - `answer`
   - `memory`
8. Odoo persiste memoria actualizada y guarda historial textual.

### Flujo de follow-up exitoso

Ejemplo observado:

1. Se identifica una venta concreta.
2. Se guarda `last_entity = sale.order / id / display_name`.
3. El usuario pregunta `que productos se vendieron?`
4. El agente detecta follow-up relacional.
5. Hace:
   - `query_odoo_search` sobre `sale.order.line` con `order_id = id`
   - `query_odoo_read` sobre esas líneas
6. Responde sin pasar por el LLM.

## Estado de la Memoria

### Qué memoria existe hoy

La memoria estructurada existe y ya se usa en producción del flujo.

No vive en RAM del AI service como fuente principal. Vive persistida en Odoo.

### Identificación de sesión

La sesión se identifica mediante:

- `user_id`
- `chat_session_key`

`chat_session_key` se genera en el frontend y se guarda en `localStorage`.

### Persistencia

La memoria se guarda en el modelo:

- `ai.chat.session.memory`

con unicidad lógica por:

- `user_id + session_key`

### Qué guarda hoy

Memoria mínima:

- `last_entity`
- `pending_clarification`

`last_entity` suele incluir:

- `model`
- `id`
- `display_name`
- `fields`
- `source_query`

### Qué implica esto

Ventajas:

- el AI service puede seguir siendo casi stateless
- la memoria sobrevive entre requests
- la memoria no se mezcla entre usuarios
- la memoria puede separarse por sesión

Riesgos:

- hoy la memoria está centrada en una sola entidad principal
- múltiples entidades paralelas aún no están bien modeladas
- cambios de tema pueden generar ambigüedad

## Cómo se Resuelven los Follow-ups

### 1. Follow-up por entidad

Casos como:

- `cuál fue esa venta`
- `muéstramela`
- `esa factura`

El agente reutiliza el `id` de `last_entity` y hace `query_odoo_read`.

### 2. Follow-up relacional

Casos como:

- `qué productos se vendieron`
- `tiene facturas`

Se resuelven con un registry declarativo en `reference_resolver.py` basado en:

- modelo fuente
- intención relacional
- plan de búsqueda
- plan de lectura

Relaciones hoy implementadas:

- `sale.order -> sale.order.line` para productos
- `purchase.order -> purchase.order.line` para productos
- `sale.order -> account.move` para facturas
- `purchase.order -> account.move` para facturas

### 3. Aclaraciones

Casos ambiguos como:

- `mayor venta`
- `mayor compra`

El sistema pide precisión antes de consultar.

Ejemplo:

- `¿Te refieres a la orden de venta individual más alta o al total vendido del período?`

Luego guarda una aclaración pendiente en memoria y espera la respuesta del usuario.

## Qué Ya Funciona

Según código y logs observados:

- aclaraciones básicas para `mayor venta` y `mayor compra`
- follow-up por entidad concreta
- follow-up relacional de productos
- follow-up relacional de facturas
- recuperación de cliente de una venta, aunque aún vía LLM en algunos casos
- memoria por sesión persistida en Odoo
- bypass del LLM con `memory_hit` real en varios casos
- validación de schema antes de algunas consultas
- métricas útiles por consulta

## Qué Todavía No Está Sólido

### Dependencia residual del LLM

Aunque ya hay más lógica determinística, todavía existen casos donde:

- una aclaración resuelta termina en una consulta interpretada otra vez por el LLM
- preguntas simples como `cual es el cliente de esta venta?` aún pasan por LLM en lugar de ir directo por memoria

### Ambigüedad residual

La memoria actual usa principalmente `last_entity`. Eso funciona bien para continuidad simple, pero puede fallar cuando:

- hay cambio de tema
- hay varias entidades recientes
- el usuario usa referencias menos claras

### Relaciones dependientes del cliente

La relación entre documentos puede no ser igual en todas las bases Odoo. Por ejemplo:

- facturas relacionadas por `invoice_origin`

Eso funciona en varios casos, pero no necesariamente en todos.

### Testing insuficiente

No se ve aún una suite amplia cubriendo:

- follow-ups
- aclaraciones
- regresiones semánticas
- ids string vs int
- fechas `datetime`

## Logs y Lectura Operativa

### Casos que muestran madurez real

Consultas como:

- `que productos se vendieron?`
- `tiene facturas?`

ya se resuelven con:

- `memory_hit: true`
- `followup_resolved: true`
- `followup_bypassed_llm: true`
- `iterations: 0`

Esto es una mejora clara frente al comportamiento anterior.

### Casos que aún cuestan demasiado

Consultas aclaradas como:

- `la venta individual`

pueden terminar bien, pero con:

- varias iteraciones
- muchos tokens
- latencia mayor

Eso indica que la aclaración ya funciona como mecanismo conversacional, pero la resolución posterior aún no es completamente determinística.

## Seguridad

### Endpoints relevantes

Odoo expone al menos:

- `/ai_assistant/ask`
- `/ai_assistant/ask_http`
- `/ai/get_data`
- `/ai/schema`

### Controles observados

- operaciones limitadas a lectura
- uso de tools controladas
- validación de domains
- validación de schema
- validación semántica parcial
- token interno opcional mediante `ODOO_AI_TOKEN`

### Riesgos actuales

- uso de `sudo()` en el lado Odoo
- falta de una política más fuerte de allowlist por modelo/campo para escenarios más sensibles
- algunas consultas aún dependen demasiado de interpretación del LLM

## Testing y Madurez

### Estado actual

Existe base de testing, por ejemplo:

- `odoo_ai_service/tests/test_metrics.py`

Pero todavía no parece haber cobertura amplia para la parte más delicada del agente.

### Qué faltaría cubrir

- aclaraciones pendientes y resueltas
- follow-up por memoria
- follow-up relacional
- edge cases de fechas
- edge cases de ids
- regresiones semánticas que ya aparecieron en logs

## Escalabilidad

### Puntos positivos

- separación razonable entre Odoo y AI service
- memoria persistida fuera del proceso del agente
- follow-ups resueltos por código en lugar de texto libre
- registry declarativo para relaciones

### Límites actuales

- la memoria sigue centrada en una sola entidad principal
- las aclaraciones todavía pueden terminar en interpretaciones LLM costosas
- el registry relacional escala manualmente, no por introspección automática

## Deuda Técnica Más Importante

1. Falta de más rutas determinísticas para consultas top/ranking ambiguas.
2. Cobertura de tests insuficiente para bugs ya detectados.
3. Dependencia todavía alta del LLM para algunos casos donde ya hay suficiente contexto estructurado.
4. Modelo de memoria todavía limitado a `last_entity`.

## Prioridad Recomendada

### Prioridad 1

Agregar intenciones determinísticas para:

- orden de venta individual más alta
- orden de compra individual más alta
- total vendido del período
- total comprado del período

### Prioridad 2

Agregar bypass por memoria para atributos directos:

- cliente
- proveedor
- fecha
- estado
- monto

### Prioridad 3

Ampliar tests de regresión para:

- `datetime` exacto
- ids string vs int
- aclaración que no debe repetirse
- follow-up relacional

### Prioridad 4

Revisar política de seguridad y exposición por modelos/campos.

## Evaluación General

Hoy el agente está en un punto intermedio bastante bueno.

No es solo un prototipo conversacional. Ya tiene:

- memoria estructurada
- aclaraciones
- follow-ups útiles
- validación de consultas
- telemetría

Lo que le falta para verse realmente sólido y maduro no es "más inteligencia", sino:

- más rutas determinísticas
- más cobertura de tests
- mejor política de seguridad
- mejor manejo de múltiples contextos

## Archivos de Referencia

### Servicio

- `odoo_ai_service/main.py`
- `odoo_ai_service/agents/assistant_agent.py`
- `odoo_ai_service/agents/agent/assistant_agent.py`
- `odoo_ai_service/agents/agent/reference_resolver.py`
- `odoo_ai_service/agents/agent/clarification_resolver.py`
- `odoo_ai_service/agents/agent/memory_store.py`
- `odoo_ai_service/agents/agent/execution/tool_executor.py`
- `odoo_ai_service/tools/odoo_get_tool.py`
- `odoo_ai_service/tools/tool_definitions.py`
- `odoo_ai_service/agents/agent/intents/intent_matcher.py`
- `odoo_ai_service/agents/agent/intents/intent_catalog.py`
- `odoo_ai_service/agents/agent/metrics/telemetry.py`

### Odoo

- `custom_addons/odoo_ai_assistant/controllers/chat_controller.py`
- `custom_addons/odoo_ai_assistant/models/model.py`
- `custom_addons/odoo_ai_assistant/models/session_memory.py`
- `custom_addons/odoo_ai_assistant/static/src/js/chat.js`
- `custom_addons/odoo_ai_assistant/__manifest__.py`

### Infra

- `docker-compose.yaml`
- `.env`

