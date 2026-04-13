tools = [
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": (
                "Obtiene el schema resumido de uno o más modelos Odoo. "
                "Úsala solo para confirmar campos válidos antes de consultar datos. "
                "Siempre debes enviar 'models'. "
                "No pidas schema global ni modelos irrelevantes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "models": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Lista de modelos Odoo a inspeccionar, por ejemplo "
                            "['sale.order'] o ['sale.order.line']"
                        ),
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Fuerza recarga del schema desde Odoo",
                    },
                },
                "required": ["models"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_odoo_search",
            "description": "Busca registros en Odoo y devuelve IDs. Úsala para listas o antes de leer campos con query_odoo_read.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "domain": {"type": "array", "items": {}},
                    "orderby": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["model"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_odoo_count",
            "description": "Cuenta registros en Odoo (search_count)",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "domain": {"type": "array", "items": {}},
                    "limit": {"type": "integer"},
                },
                "required": ["model"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_odoo_read",
            "description": "Lee campos de registros por IDs",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "ids": {"type": "array", "items": {"type": "integer"}},
                    "fields": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["model", "ids", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_odoo_group",
            "description": (
                "Agrupa y agrega datos con read_group. "
                "Úsala para top, rankings, sumas, promedios y totales. "
                "En 'fields' usa métricas agregadas como 'amount_total:sum'. "
                "En 'groupby' usa los campos por los que quieres agrupar. "
                "Para totales puros, 'groupby' puede ser una lista vacía []. "
                "En 'orderby' usa '__count desc' o el nombre del campo agregado, por ejemplo 'amount_total desc'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "domain": {"type": "array", "items": {}},
                    "fields": {"type": "array", "items": {"type": "string"}},
                    "groupby": {"type": "array", "items": {"type": "string"}},
                    "orderby": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["model", "groupby", "fields"],
                "additionalProperties": False,
            },
        },
    }
]
