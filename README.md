# Odoo AI Copilot

## Introducción

AI Copilot que permite consultar datos del ERP Odoo usando lenguaje natural.

En lugar de navegar múltiples menús o reportes, los usuarios pueden simplemente preguntar:

"Top clientes por facturación"

"Ventas del último mes"

"Facturas pendientes"

El sistema interpreta la pregunta, consulta el ERP usando herramientas controladas y devuelve una respuesta basada en los datos reales del sistema.

## Demo
**Ejemplo de consulta:**

*Usuario pregunta:*
> Encuentra clientes con más facturación

**Respuesta del asistente::**
1. JOSEPH CAMPOS ABOGADOS S.A.C – 2809  
2. CENTRO EDUCATIVO PARTICULAR SAN AGUSTIN – 1664  
3. COLEGIO MARKHAM – 1500

El asistente obtiene los datos directamente del ERP usando el ORM de Odoo.

## Problema

Los sistemas ERP como Odoo contienen grandes volúmenes de datos, pero obtener información suele requerir:

- navegar múltiples menús

- aplicar filtros manuales

- generar reportes específicos

Para muchos usuarios de negocio, acceder a insights rápidos puede ser difícil o lento.

## Solución

Odoo AI Copilot permite consultar el ERP mediante lenguaje natural.

El sistema utiliza un agente basado en LLM que:

- interpreta la intención del usuario

- selecciona la herramienta adecuada

- consulta el ERP mediante el ORM

- devuelve una respuesta clara basada en los datos

El agente no tiene acceso directo a la base de datos, sino que opera mediante herramientas controladas.

## Arquitectura
```
Usuario
   ↓
Odoo Controller
   ↓
AI Service (FastAPI)
   ↓
LLM Agent
   ↓
Tools
   ↓
Odoo ORM
```

**Arquitectura desacoplada:**

- Odoo maneja la interfaz del usuario

- FastAPI gestiona la lógica del agente

- El LLM decide qué herramientas utilizar

- Las tools ejecutan consultas seguras al ERP

## Tecnologías

**Backend:**

- Python
- FastAPI
- Docker
- PostgreSQL

**ERP:**

- Odoo V18

**AI:**

- OpenAI API
- GPT-4o mini

## Diseño del agente

El agente interactúa con el ERP mediante herramientas especializadas.

### Tools disponibles:

### `query_odoo_search`
Busca registros y devuelve IDs.


### `query_odoo_read`
Lee campos específicos de registros.


### `query_odoo_group`
Realiza agregaciones usando `read_group`.

Esto permite que el LLM consulte el ERP sin ejecutar código arbitrario ni acceder directamente a la base de datos.

## Seguridad

El sistema implementa varias restricciones:

- Acceso limitado a operaciones de lectura
- Uso obligatorio de herramientas controladas
- El LLM no recibe credenciales del ERP
- No existe acceso directo a la base de datos
- Las llamadas al LLM se realizan desde el AI Service, nunca desde el navegador.
- Se recomienda rotación de API keys y uso de secretos en el entorno de despliegue.

Las operaciones permitidas son:
- search
- read
- read_group

Esto reduce riesgos de seguridad en el uso de IA dentro de sistemas empresariales.

## Performance

Optimización implementada:

- Separación de tools para reducir ambigüedad
- Uso de `read_group` para agregaciones
- Reducción de datasets enviados al LLM

Resultados:

| Versión | Tokens promedio |
|-------|-------|
| Inicial | ~5000 |
| Optimizada | ~831 |

Reducción aproximada: **83%**

## Instalación
1. Configura las variables de entorno (ver sección abajo).
2. Levanta los servicios:
   ```bash
   docker compose up -d --build
   ```
3. En Odoo:
   - Actualiza la lista de Apps.
   - Instala el módulo **AI Assistant** (`odoo_ai_assistant`) en la base deseada.

## Configuración
El proyecto se apoya en `.env` (en la raíz) y en `config/odoo.conf`.

### Variables de entorno principales
Configura al menos estas variables en `.env`:
- `OPENAI_API_KEY` (obligatorio)
- `ODOO_BASE_URL` (ej. `http://web:8069`)
- `ODOO_DB` (ej. `communitas`)

Variables comunes ya usadas por `docker-compose.yaml`:
- `ODOO_VERSION`, `ODOO_PORT`, `ODOO_CONTAINER_NAME`
- `PG_VERSION`, `PG_PORT`, `PG_CONTAINER_NAME`, `PG_USER`, `PG_PASSWORD`
- `ODOO_SERVER`, `ODOO_DATA`, `CUSTOM_ADDONS`, `ENTERPRISE_ADDONS`

Puedes ajustar límites de tokens y logging con estas variables:
- `LLM_MODEL` (default: `gpt-4o-mini`)
- `LLM_MAX_INPUT_TOKENS` (default: `80000`)
- `LLM_MAX_COMPLETION_TOKENS` (default: `512`)
- `LLM_MAX_MESSAGE_CHARS` (default: `24000`)
- `LLM_MAX_TOOL_CHARS` (default: `12000`)
- `LLM_TOKEN_CHAR_RATIO` (default: `4.0`)
- `LLM_LOG_TOKEN_USAGE` (default: `true`)

## Guía rápida de uso
1. Abre Odoo en tu navegador (puerto definido por `ODOO_PORT`).
2. Entra al menú del módulo **AI Assistant**.
3. Escribe una consulta, por ejemplo:
   - “Lista los clientes”
   - “Top clientes por facturación”
   - “Ventas del último mes”
4. El asistente devolverá el resultado usando datos del ERP.

## Cómo funciona
1. El usuario hace una pregunta en Odoo.
2. El controller de Odoo envía la pregunta al **AI Service**.
3. El LLM decide si necesita datos y llama una herramienta.
4. La herramienta consulta Odoo vía `/ai/get_data`.
5. El LLM genera la respuesta final con los datos obtenidos.


## Limitaciones
- Solo lectura (no crea ni modifica registros).
- Requiere que el módulo `odoo_ai_assistant` esté instalado.
- Campos incorrectos generan errores (“Invalid field”).
- Consultas temporales dependen de campos correctos (`date_order`, `invoice_date`).

## Estructura del proyecto
```
.
├── addons/
│   └── custom_addons/odoo_ai_assistant/
├── odoo_ai_service/
│   ├── agents/
│   ├── llm/
│   ├── tools/
│   └── main.py
├── config/
├── data/
├── db/
└── docker-compose.yaml
```

## Troubleshooting
- **404 en `/ai/get_data`**  
  Verifica que el módulo `odoo_ai_assistant` esté instalado y reinicia Odoo.

- **Error de “Invalid field”**  
  El campo no existe en ese modelo. Ajusta el dominio o usa el campo correcto (ej. `date_order` en `sale.order`).

- **Permisos insuficientes**  
  Asegura que el usuario tenga acceso al modelo y que el controller use `sudo()` cuando corresponda.

- **Base de datos incorrecta**  
  Verifica `ODOO_DB` en `.env` y que la BD exista en PostgreSQL.

- **Rate limit (429)**  
  Reduce tokens de entrada (`LLM_MAX_INPUT_TOKENS`), limita resultados o usa agregaciones.

- **El LLM no usa la tool correcta**  
  Revisa el prompt del agente y agrega ejemplos específicos para esa consulta.


## Roadmap
Mejoras futuras:
- Schema discovery de modelos Odoo
- Soporte para consultas temporales
- Caching de resultados
- Integración MCP (Model Context Protocol)

## License
Licensed under the Apache License 2.0. See `LICENSE`.
