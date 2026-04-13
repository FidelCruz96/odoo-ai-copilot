import json

from odoo import fields, models


class AIChatSessionMemory(models.Model):
    _name = "ai.chat.session.memory"
    _description = "AI Chat Session Memory"

    user_id = fields.Many2one("res.users", required=True, index=True, ondelete="cascade")
    session_key = fields.Char(required=True, index=True)
    memory_json = fields.Text(default="{}")

    _sql_constraints = [
        ("ai_chat_session_memory_unique", "unique(user_id, session_key)", "La memoria de sesion ya existe."),
    ]

    def get_memory_payload(self):
        self.ensure_one()
        try:
            payload = json.loads(self.memory_json or "{}")
        except Exception:
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def get_or_create_for_user_session(self, user_id, session_key):
        session_key = (session_key or "").strip()
        if not user_id or not session_key:
            return self.browse()
        record = self.search(
            [("user_id", "=", user_id), ("session_key", "=", session_key)],
            limit=1,
        )
        if record:
            return record
        return self.create({
            "user_id": user_id,
            "session_key": session_key,
            "memory_json": "{}",
        })

    def get_memory_for_user_session(self, user_id, session_key):
        record = self.get_or_create_for_user_session(user_id, session_key)
        return record.get_memory_payload() if record else {}

    def save_memory_for_user_session(self, user_id, session_key, memory):
        record = self.get_or_create_for_user_session(user_id, session_key)
        if not record:
            return self.browse()
        payload = memory if isinstance(memory, dict) else {}
        record.write({
            "memory_json": json.dumps(payload, ensure_ascii=False),
        })
        return record
