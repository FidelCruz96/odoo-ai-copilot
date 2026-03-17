from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = "res.config.settings"

    ai_chat_history_limit = fields.Integer(
        string="AI Chat History Limit",
        config_parameter="odoo_ai_assistant.ai_chat_history_limit",
        default=8,
    )
    ai_chat_use_server_history = fields.Boolean(
        string="Use Server Chat History",
        config_parameter="odoo_ai_assistant.ai_chat_use_server_history",
        default=True,
    )
