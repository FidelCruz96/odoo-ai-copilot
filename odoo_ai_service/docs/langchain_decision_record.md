# Decision tecnica: LangChain

## Estado

LangChain esta declarado en `requirements.txt`, pero el agente no lo usa en ejecucion.

El agente actual usa OpenAI SDK directo con tool calling y una orquestacion propia para memoria, rutas deterministicas, validaciones, metricas y payload UI.

## Decision actual

No migrar todo a LangChain en esta etapa.

## Motivos

- El flujo actual tiene reglas Odoo especificas que deben conservarse.
- Las rutas deterministicas reducen dependencia del LLM para preguntas frecuentes.
- La validacion de dominios, campos, IDs y semantica no la resuelve LangChain automaticamente.
- Una migracion completa agregaria abstraccion y riesgo sin resolver el principal problema actual: modularidad, tests y observabilidad.

## Donde podria entrar LangChain

LangChain tendria sentido como spike acotado para reemplazar solo el bloque `tool_guided`:

```txt
prompt builder -> LangChain AgentExecutor -> tools Odoo -> payload actual
```

Tambien podria ser util si el proyecto incorpora:

- RAG con documentacion interna.
- Multiples proveedores LLM.
- Tools externas no Odoo.
- Tracing con LangSmith.

## Recomendacion

Mantener OpenAI SDK directo por ahora, terminar modularizacion y evaluaciones, y luego comparar contra un spike con LangChain o LangGraph usando metricas de latencia, calidad, trazabilidad y control de errores.
