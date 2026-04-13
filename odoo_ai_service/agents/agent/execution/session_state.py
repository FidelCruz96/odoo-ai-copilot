from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionState:
    last_tool_sig: str | None = None
    repeated_tool_calls: int = 0
    last_partner_ids: list[int] = field(default_factory=list)
    last_partner_model: str | None = None
    last_ids_by_model_field: dict = field(default_factory=dict)
    used_tool_in_session: bool = False
    last_error_sig: str | None = None
    repeated_errors: int = 0
    total_errors: int = 0
