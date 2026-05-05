from __future__ import annotations

import json
import os
from datetime import date, timedelta

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def load_prompt(name: str) -> str:
    path = os.path.join(PROMPTS_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip() + "\n"


def build_date_context_prompt() -> str:
    today = date.today()
    year = today.year
    month = today.month

    month_start = today.replace(day=1)
    month_end = (
        today.replace(month=month % 12 + 1, day=1) - timedelta(days=1)
        if month < 12 else today.replace(day=31)
    )

    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    last_year_start = today.replace(year=year - 1, month=1, day=1)
    last_year_end = today.replace(year=year - 1, month=12, day=31)

    last_month_year = year if month > 1 else year - 1
    last_month = month - 1 if month > 1 else 12
    last_month_start = today.replace(year=last_month_year, month=last_month, day=1)
    last_month_end = (
        today.replace(year=last_month_year, month=last_month % 12 + 1, day=1) - timedelta(days=1)
        if last_month < 12 else today.replace(year=last_month_year, month=last_month, day=31)
    )

    year_start = today.replace(month=1, day=1)
    year_end = today.replace(month=12, day=31)

    return (
        f"Hoy es {today}.\n"
        "Rangos útiles:\n"
        f"- hoy: {today}\n"
        f"- inicio_mes: {month_start}\n"
        f"- fin_mes: {month_end}\n"
        f"- inicio_año: {year_start}\n"
        f"- fin_año: {year_end}\n"
        f"- inicio_semana: {week_start}\n"
        f"- fin_semana: {week_end}\n"
        f"- año_pasado_inicio: {last_year_start}\n"
        f"- año_pasado_fin: {last_year_end}\n"
        f"- mes_pasado_inicio: {last_month_start}\n"
        f"- mes_pasado_fin: {last_month_end}\n"
    )


def family_prompt_path(family: str) -> str | None:
    mapping = {
        "ventas": "family_ventas.txt",
        "compras": "family_compras.txt",
        "facturacion": "family_facturacion.txt",
        "clientes": "family_clientes.txt",
        "productos": "family_productos.txt",
        "inventario": "family_inventario.txt",
    }
    return mapping.get(family)


def compress_context(context: dict | None) -> str | None:
    if not context:
        return None
    try:
        return json.dumps(context, ensure_ascii=False)
    except Exception:
        return str(context)
