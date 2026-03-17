from odoo import models, fields


class AIChatUI(models.Model):

    _name = "ai.chat.ui"
    _description = "AI Chat UI"

    name = fields.Char(default="AI Chat UI")
