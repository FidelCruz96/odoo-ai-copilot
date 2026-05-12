import json

from odoo import fields, models


class AIToolAuditLog(models.Model):
    _name = "ai.tool.audit.log"
    _description = "AI Tool Audit Log"
    _order = "create_date desc"

    trace_id = fields.Char(index=True)
    session_id = fields.Char(index=True)
    db_name = fields.Char(index=True)
    user_id = fields.Many2one("res.users", index=True, ondelete="set null")
    route = fields.Char(index=True)
    intent = fields.Char(index=True)
    domain = fields.Char(index=True)
    tool_name = fields.Char(required=True, index=True)
    model_name = fields.Char(index=True)
    operation = fields.Char(index=True)
    domain_filter = fields.Text(default="[]")
    fields_json = fields.Text(default="[]")
    limit = fields.Integer()
    success = fields.Boolean(default=False, index=True)
    error_type = fields.Char(index=True)
    latency_ms = fields.Float()
    result_count = fields.Integer()
    result_sample = fields.Text(default="null")

    def _to_json_text(self, payload):
        return json.dumps(payload, ensure_ascii=False, default=str)
