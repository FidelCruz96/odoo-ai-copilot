from odoo import models, fields

class AIChat(models.Model):

    _name = "ai.chat"
    _description = "AI Chat History"

    user_id = fields.Many2one("res.users")

    question = fields.Text()

    answer = fields.Text()

    create_date = fields.Datetime()