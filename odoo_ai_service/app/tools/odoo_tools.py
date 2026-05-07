from __future__ import annotations

from tools.odoo_get_tool import get_schema, query_odoo


def query_odoo_search(**kwargs):
    return query_odoo(operation="search", **kwargs)


def query_odoo_read(**kwargs):
    return query_odoo(operation="read", **kwargs)


def query_odoo_count(**kwargs):
    return query_odoo(operation="search_count", **kwargs)


def query_odoo_group(**kwargs):
    return query_odoo(operation="read_group", **kwargs)


__all__ = [
    "get_schema",
    "query_odoo_search",
    "query_odoo_read",
    "query_odoo_count",
    "query_odoo_group",
]
