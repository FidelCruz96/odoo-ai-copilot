tools = [
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": "Obtiene el schema de modelos/campos desde Odoo",
            "parameters": {
                "type": "object",
                "properties": {
                    "force": {"type": "boolean"},
                    "models": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_odoo_search",
            "description": "Busca registros en Odoo y devuelve IDs",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "domain": {"type": "array", "items": {}},
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
            "description": "Agrupa y agrega datos con read_group",
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
            },
        },
    },
]
