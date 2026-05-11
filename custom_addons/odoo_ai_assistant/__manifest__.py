{
    "name": "AI Assistant",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "summary": "AI Assistant for Odoo",
    "author": "Fidel Cruz",
    "website": "",
    "license": "LGPL-3",
    "depends": ['base', 'web', 'account', 'purchase', 'stock', 'sale'],
    "data": [
        "security/ir.model.access.csv",
        "security/ai_chat_rules.xml",
        "views/chat_view.xml",
        "views/settings_view.xml",
        "views/chat_context_buttons.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "odoo_ai_assistant/static/src/js/chat.js",
            "odoo_ai_assistant/static/src/css/chat.css"
        ]
    },
    "installable": True,
}
