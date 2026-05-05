# Arquitectura del agente IA

## Flujo actual

El endpoint `POST /ask` llama a `ask_agent()`. El agente resuelve la solicitud en este orden:

1. Inicializa `request_id`, metricas, memoria y contexto UI.
2. Resuelve aclaraciones pendientes o detecta si necesita una nueva aclaracion.
3. Intenta resolver follow-ups desde memoria antes de llamar al LLM.
4. Ejecuta rutas deterministicas para intenciones conocidas.
5. Si lo anterior no alcanza, arma mensajes para el LLM y usa tool calling.
6. Valida argumentos de tools contra schema, dominio y reglas semanticas.
7. Ejecuta tools contra Odoo.
8. Comprime resultados, actualiza memoria y devuelve el payload de UI.

## Capas principales

- `main.py`: entrada HTTP FastAPI.
- `agents/agent/assistant_agent.py`: orquestacion principal del agente.
- `agents/agent/prompt_builder.py`: carga de prompts y contexto temporal/funcional.
- `agents/agent/tool_loop.py`: ciclo LLM/tool calling, validacion de tool calls y reinyeccion de resultados.
- `agents/agent/tool_schemas.py`: validacion estructurada de argumentos de tools.
- `agents/agent/execution/tool_executor.py`: despacho de tools hacia Odoo.
- `tools/tool_definitions.py`: schema OpenAI tool calling.
- `tools/odoo_get_tool.py`: cliente HTTP hacia endpoints Odoo.
- `llm/base.py`: contrato de cliente LLM.
- `llm/openai_client.py`: implementacion OpenAI.
- `llm/llm_client.py`: compatibilidad con `call_llm()`.

## Rutas del agente

Las rutas canonicas estan en `agents/agent/routes.py`:

- `clarification_required`
- `memory_followup_entity`
- `memory_followup_related`
- `deterministic`
- `tool_guided`
- `fallback_explanatory`

## Riesgos tecnicos actuales

- `assistant_agent.py` aun concentra logica de rutas, UI y ejecucion deterministica.
- Las reglas de negocio siguen cerca de la orquestacion principal.
- La observabilidad mejora con eventos estructurados, pero falta trazabilidad de todos los pasos deterministas.
- El contrato de tools ya tiene validacion estructurada, pero los schemas OpenAI y los validadores internos deben mantenerse sincronizados.
