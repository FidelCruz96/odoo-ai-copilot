from __future__ import annotations

import json


def compress_tool_result(tool_name: str, result) -> str:
    MAX_ITEMS = 10

    if isinstance(result, list):
        truncated = result[:MAX_ITEMS]
        suffix = f"\n[...{len(result) - MAX_ITEMS} más omitidos]" if len(result) > MAX_ITEMS else ""

        if tool_name == "query_odoo_search":
            return f"IDs encontrados: {truncated}{suffix}"

        if tool_name == "query_odoo_read":
            cleaned = []
            for item in truncated:
                cleaned.append({
                    k: v for k, v in item.items()
                    if not k.startswith("__") and k != "write_uid"
                })
            return json.dumps(cleaned, ensure_ascii=False) + suffix

        if tool_name == "query_odoo_group":
            cleaned = []
            for item in truncated:
                cleaned.append({
                    k: v for k, v in item.items()
                    if k not in ("__domain", "__context", "__fold")
                })
            return json.dumps(cleaned, ensure_ascii=False) + suffix

    if isinstance(result, dict) and "error" in result:
        return f"ERROR: {result['error']}"

    if isinstance(result, dict) and tool_name == "get_schema":
        model_count = len(result.keys()) if isinstance(result, dict) else 0
        sample = list(result.keys())[:10]
        return json.dumps({"models": model_count, "sample": sample}, ensure_ascii=False)

    return str(result)[:500]
