import json
import logging
import os
from datetime import datetime, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

SCHEMA_TTL_SECONDS = int(os.getenv("AI_SCHEMA_TTL_SECONDS", "3600"))
SCHEMA_DEFAULT_MODELS = os.getenv("AI_SCHEMA_MODELS", "")


class AISchemaCache(models.Model):

    _name = "ai.schema.cache"
    _description = "AI Schema Cache"

    name = fields.Char(default="AI Schema Cache", required=True)
    schema_json = fields.Text()
    models_count = fields.Integer()
    updated_at = fields.Datetime()

    @api.model
    def _parse_models_filter(self, models_filter):
        if isinstance(models_filter, list):
            return [m for m in models_filter if isinstance(m, str) and m.strip()]
        if isinstance(models_filter, str):
            return [m.strip() for m in models_filter.split(",") if m.strip()]
        return []

    @api.model
    def _get_target_models(self, models_filter=None):
        models_filter = self._parse_models_filter(models_filter)
        if not models_filter and SCHEMA_DEFAULT_MODELS:
            models_filter = self._parse_models_filter(SCHEMA_DEFAULT_MODELS)
        if models_filter:
            return models_filter
        return None

    @api.model
    def _build_schema(self, models_filter=None):
        Model = self.env["ir.model"].sudo()
        Field = self.env["ir.model.fields"].sudo()

        target_models = self._get_target_models(models_filter)
        domain = [("model", "in", target_models)] if target_models else []
        models_records = Model.search(domain)

        schema = {}
        for model_rec in models_records:
            fields_domain = [("model", "=", model_rec.model)]
            fields_recs = Field.search(fields_domain)
            fields_map = {}
            for f in fields_recs:
                field_info = {
                    "type": f.ttype,
                    "relation": f.relation or None,
                    "required": bool(f.required),
                    "readonly": bool(f.readonly),
                    "store": bool(f.store),
                }
                if f.ttype == "selection" and f.selection:
                    try:
                        selection = f.selection
                        if isinstance(selection, (list, tuple)):
                            field_info["selection"] = [v[0] for v in selection if isinstance(v, (list, tuple)) and v]
                    except Exception:
                        pass
                fields_map[f.name] = field_info

            schema[model_rec.model] = {
                "name": model_rec.name,
                "fields": fields_map,
            }

        return schema

    @api.model
    def refresh_schema(self, models_filter=None):
        schema = self._build_schema(models_filter=models_filter)
        schema_json = json.dumps(schema, ensure_ascii=False)
        record = self.search([], limit=1)
        values = {
            "schema_json": schema_json,
            "models_count": len(schema),
            "updated_at": fields.Datetime.now(),
        }
        if record:
            record.write(values)
        else:
            values["name"] = "AI Schema Cache"
            record = self.create(values)
        _logger.info("AI schema cache updated models=%s", len(schema))
        return record

    @api.model
    def get_schema(self, force=False, models_filter=None):
        requested_models = self._get_target_models(models_filter)
        record = self.search([], limit=1)
        if force or not record or not record.updated_at:
            record = self.refresh_schema(models_filter=models_filter)
        else:
            ttl = timedelta(seconds=SCHEMA_TTL_SECONDS)
            if datetime.utcnow() - record.updated_at > ttl:
                record = self.refresh_schema(models_filter=models_filter)

        if not record or not record.schema_json:
            return {}

        try:
            schema = json.loads(record.schema_json)
            if not isinstance(schema, dict):
                return {}
            if not requested_models:
                return schema
            missing = [m for m in requested_models if m not in schema]
            if missing:
                record = self.refresh_schema(models_filter=requested_models)
                schema = json.loads(record.schema_json) if record and record.schema_json else {}
                if not isinstance(schema, dict):
                    return {}
            filtered = {}
            for model_name in requested_models:
                if model_name in schema:
                    filtered[model_name] = schema[model_name]
            return filtered
        except Exception:
            _logger.exception("AI schema cache JSON parse failed")
            return {}
