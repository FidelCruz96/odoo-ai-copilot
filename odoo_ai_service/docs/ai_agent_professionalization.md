# Profesionalizacion del agente IA

## Cambios aplicados

- Se agrego una capa de rutas canonicas para evitar strings nuevos dispersos.
- Se agrego tracing estructurado basico para eventos del agente.
- Se agregaron validadores estructurados para argumentos de tools sin nuevas dependencias.
- Se reforzo `execute_tool()` para bloquear argumentos invalidos antes de llamar a Odoo.
- Se separo el cliente OpenAI detras de una interfaz LLM compatible con el `call_llm()` existente.
- Se extrajo el ciclo `tool_guided` a `agents/agent/tool_loop.py`.
- Se documento la decision de no migrar a LangChain todavia.

## Siguiente nivel recomendado

1. Extraer builders de respuesta/UI hacia `response_builder.py`.
2. Extraer ejecucion deterministica hacia `deterministic_runner.py`.
3. Crear evaluaciones de agente con casos YAML o JSON.
4. Agregar trazas para rutas deterministicas y follow-ups.
5. Sincronizar automaticamente schema OpenAI tools con validadores internos para evitar drift.

## Criterio de calidad

El agente debe poder explicar por logs:

- que ruta eligio,
- que tool ejecuto,
- con que argumentos validados,
- que tipo/tamano de resultado obtuvo,
- que error ocurrio si fallo,
- y que contrato de respuesta devolvio.
