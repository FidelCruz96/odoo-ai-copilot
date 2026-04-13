# Odoo AI Copilot

Asistente conversacional híbrido para Odoo que permite consultar datos reales del ERP usando lenguaje natural.

A diferencia de un chatbot tradicional basado solo en LLM, este proyecto combina **rutas determinísticas, memoria contextual, validación semántica y tools seguras de solo lectura** para mejorar latencia, costo y confiabilidad al consultar ventas, facturas y compras.

## Qué resuelve

En Odoo, obtener información útil suele requerir navegar varios menús, aplicar filtros manuales o construir reportes específicos.

Este proyecto permite hacer preguntas como:

- `Top clientes por facturación`
- `Facturas pendientes`
- `Ventas del último mes`
- `¿Qué productos se vendieron en esa orden?`

y obtener respuestas basadas en datos reales del ERP.

## Enfoque

El agente sigue una estrategia híbrida:

1. intenta resolver aclaraciones pendientes
2. usa memoria de sesión para follow-ups
3. aplica intents y planner determinísticos
4. solo si hace falta, usa LLM con tool calling controlado

Esto reduce el uso innecesario del modelo y mejora la consistencia en consultas repetibles.

## Capacidades actuales

- Consultas de **ventas, facturas y compras**
- **Conteos, listados, rankings y agregaciones**
- **Follow-ups contextuales**
- **Aclaraciones para preguntas ambiguas**
- **Render determinístico** para listados/rankings críticos
- **Validación semántica y de schema**
- **Métricas de calidad** por respuesta

## Ejemplos

### Aclaración
**Usuario:** `facturas pendientes este mes`  
**Asistente:** `¿Quieres solo el total o quieres ver el detalle?`

### Follow-up
**Usuario:** `dime la mayor venta del último mes`  
**Asistente:** `¿Te refieres a la orden individual más alta o al total vendido del período?`  
**Usuario:** `la individual`  
**Usuario:** `¿qué productos se vendieron?`

### Consulta analítica
**Usuario:** `Top clientes por facturación`

## Arquitectura

- **Frontend Odoo** para interacción de usuario
- **FastAPI AI Service** como capa de orquestación
- **Agente híbrido** con memoria, aclaración, intents y planner
- **Tools seguras** para `search`, `read`, `read_group`, `search_count`
- **Odoo ORM** como única vía de acceso a datos

## Decisiones de diseño

- **Solo lectura:** se priorizó seguridad y confianza
- **Agente híbrido:** primero reglas, luego LLM
- **Semantic frame:** normaliza intención, modelo, filtros y rango temporal
- **Memoria estructurada:** entidad principal/secundaria para mejores follow-ups
- **Render determinístico:** evita respuestas narradas inconsistentes en rankings y listados

## Seguridad

- Sin acceso directo a base de datos
- Sin credenciales de Odoo expuestas al LLM
- Operaciones limitadas a lectura
- Tools controladas y validadas antes de consultar

## Stack

- Python
- FastAPI
- Odoo 18
- PostgreSQL
- Docker
- OpenAI API

## Limitaciones

- Solo lectura
- Algunas consultas ambiguas aún requieren aclaración
- Ciertas relaciones dependen del modelado específico de cada instancia de Odoo
- No todas las consultas complejas tienen todavía una ruta determinística dedicada

## Roadmap

- Más intents determinísticos
- Mejor render de negocio
- Más resolutores relacionales
- Métricas más finas de fidelidad
- Caching de resultados

## License

Apache 2.0