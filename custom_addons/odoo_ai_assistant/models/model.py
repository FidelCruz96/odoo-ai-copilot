from odoo import fields, models

class AIChat(models.Model):

    _name = "ai.chat"
    _description = "AI Chat History"

    user_id = fields.Many2one("res.users")
    session_key = fields.Char(index=True)
    question = fields.Text()
    answer = fields.Text()
    create_date = fields.Datetime()
