# -*- coding: utf-8 -*-

import json
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MigrationMappingLine(models.Model):
    _name = 'migration.mapping.line'
    _description = 'Field Mapping Rule'
    _order = 'sequence asc, id asc'

    sequence = fields.Integer(default=10)
    template_id = fields.Many2one('migration.template', string='Template', required=True, ondelete='cascade')
    target_model_name = fields.Char(related='template_id.target_model_name', store=True, readonly=True)

    source_field = fields.Char(string='Source Column / Key', required=True, help='Source CSV column header, JSON key, or DB field name.')
    target_field_id = fields.Many2one(
        'ir.model.fields',
        string='Target Odoo Field',
        required=True,
        ondelete='cascade',
        domain="[('model_id', '=', parent.target_model_id)]"
    )
    target_field_name = fields.Char(related='target_field_id.name', store=True, readonly=True)
    target_field_ttype = fields.Selection(related='target_field_id.ttype', store=True, readonly=True)
    relation_model = fields.Char(related='target_field_id.relation', readonly=True)

    is_key_field = fields.Boolean(
        string='Unique Match Key',
        help='Mark as key field to identify existing Odoo records during Update and Upsert operations.'
    )

    transform_type = fields.Selection([
        ('direct', 'Direct Mapping'),
        ('default', 'Static Default Value'),
        ('value_map', 'Value Translation Table (JSON Dictionary)'),
        ('python_expr', 'Python Expression Snippet'),
    ], string='Transformation Type', default='direct', required=True)

    default_value = fields.Char(string='Default Fallback Value')
    value_mapping_json = fields.Text(
        string='Value Mapping (JSON)',
        default='{"raw_val_1": "target_val_1"}',
        help='JSON dictionary mapping source cell values to target values.'
    )
    python_code = fields.Text(
        string='Python Expression',
        default='value.strip().title() if value else default',
        help='Available variables: value, record (dict), env, default, re, datetime, math'
    )

    transform_ids = fields.One2many(
        'migration.mapping.transform',
        'line_id',
        string='Transformation Pipeline',
        copy=True
    )

    # Relational Lookup Configuration (For Many2one / Many2many)
    lookup_strategy = fields.Selection([
        ('xml_id', 'Search by XML ID (External ID)'),
        ('field_search', 'Search Target Relation by Field'),
        ('domain_expr', 'Search Target Relation by Domain'),
        ('auto_create', 'Search and Auto-Create if Missing'),
        ('record_map', 'Cross-Reference Record Map (Prior Stages)'),
    ], string='Relational Lookup Strategy', default='field_search')
    
    lookup_field_id = fields.Many2one(
        'ir.model.fields',
        string='Lookup Matching Field',
        domain="[('model', '=', relation_model)]",
        help='Field on target relation model to match against source value (e.g. name, code, email, ref).'
    )
    lookup_domain = fields.Char(string='Lookup Domain Expression', help='e.g. [("company_id", "=", env.company.id)]')

    # ------------------------------------------------------------
    # VALUE CONVERSION ENGINE
    # ------------------------------------------------------------

    def convert_value(self, raw_value, source_record):
        """Converts raw source value to Odoo target field value according to mapping configuration."""
        self.ensure_one()
        val = raw_value

        # Step 1: Multi-Step Pipeline Transformations
        if self.transform_ids:
            for step in self.transform_ids.sorted('sequence'):
                val = step.apply_transform(val, record_ctx=source_record)
        else:
            # Fallback legacy direct conversion
            if self.transform_type == 'default':
                val = self.default_value
            elif self.transform_type == 'value_map' and self.value_mapping_json:
                try:
                    dict_map = json.loads(self.value_mapping_json or '{}')
                    val = dict_map.get(str(val), dict_map.get(val, self.default_value or val))
                except Exception as e:
                    _logger.warning("Failed to parse value_mapping_json on line ID %s: %s", self.id, e)
            elif self.transform_type == 'python_expr' and self.python_code:
                import datetime
                import math
                import re
                eval_ctx = {
                    'value': raw_value,
                    'record': source_record,
                    'env': self.env,
                    'default': self.default_value,
                    're': re,
                    'datetime': datetime,
                    'math': math,
                    'json': json,
                }
                try:
                    val = eval(self.python_code, eval_ctx)
                except Exception as e:
                    _logger.error("Python mapping expression error on line ID %s: %s", self.id, e)
                    raise UserError(_("Error executing Python expression for field '%s': %s") % (self.target_field_name, str(e)))

        # Fallback if empty
        if (val is None or val == '') and self.default_value:
            val = self.default_value

        if val is None or val == '':
            return False

        # Step 2: Handle Relational Fields & Data Types
        ttype = self.target_field_ttype
        if ttype == 'many2one':
            return self._resolve_many2one(val)
        elif ttype in ('many2many', 'one2many'):
            return self._resolve_many2many(val)
        elif ttype == 'boolean':
            if isinstance(val, bool):
                return val
            return str(val).lower() in ('true', '1', 'yes', 't', 'y', 'on', 'active')
        elif ttype in ('integer', 'monetary'):
            try:
                return int(float(str(val).strip()))
            except (ValueError, TypeError):
                return 0
        elif ttype == 'float':
            try:
                return float(str(val).strip())
            except (ValueError, TypeError):
                return 0.0

        return val

    def action_test_pipeline(self, sample_value):
        """Returns step-by-step transformation traces for frontend live sample preview."""
        self.ensure_one()
        current_val = sample_value
        traces = []
        
        if self.transform_ids:
            for idx, step in enumerate(self.transform_ids.sorted('sequence'), 1):
                prev_val = current_val
                try:
                    current_val = step.apply_transform(current_val, record_ctx={})
                    status = 'ok'
                    err = False
                except Exception as e:
                    status = 'error'
                    err = str(e)

                traces.append({
                    'step': idx,
                    'name': step.name or f"Step {idx}",
                    'category': step.transform_category,
                    'input': prev_val,
                    'output': current_val,
                    'status': status,
                    'error': err,
                })
        else:
            traces.append({
                'step': 1,
                'name': 'Direct Mapping',
                'category': 'direct',
                'input': sample_value,
                'output': sample_value,
                'status': 'ok',
                'error': False,
            })

        return {
            'input': sample_value,
            'final_output': current_val,
            'traces': traces,
        }

    def action_apply_preset(self, preset_id):
        """Applies transformation preset template steps to this line."""
        self.ensure_one()
        preset = self.env['migration.transform.template'].browse(preset_id)
        if preset and preset.exists():
            return preset.action_apply_to_line(self)
        return False

    def action_save_as_preset(self, preset_name):
        """Saves current line transformation steps into a new reusable preset template."""
        self.ensure_one()
        return self.env['migration.transform.template'].create_preset_from_line(self, preset_name)

    def _resolve_from_record_map(self, val):
        """Resolves target record ID from migration.record.map cross-references."""
        rel_model = self.relation_model
        if not rel_model or not val:
            return False
        key = str(val).strip()
        rec_map = self.env['migration.record.map'].search([
            ('target_model', '=', rel_model),
            ('source_key', '=', key),
        ], order='id desc', limit=1)
        if rec_map and rec_map.target_id:
            target_rec = self.env[rel_model].browse(rec_map.target_id).exists()
            return target_rec.id if target_rec else False
        return False

    def _resolve_many2one(self, val):
        """Resolves Many2one target record ID."""
        rel_model = self.relation_model
        if not rel_model or not val:
            return False

        rel_obj = self.env[rel_model]

        if self.lookup_strategy == 'record_map':
            return self._resolve_from_record_map(val)

        elif self.lookup_strategy == 'xml_id':
            xml_id = str(val).strip()
            if '.' not in xml_id:
                xml_id = f"__import__.{xml_id}"
            rec = self.env.ref(xml_id, raise_if_not_found=False)
            return rec.id if rec else False

        elif self.lookup_strategy in ('field_search', 'auto_create'):
            match_field = self.lookup_field_id.name if self.lookup_field_id else 'name'
            rec = rel_obj.search([(match_field, '=', val)], limit=1)
            if rec:
                return rec.id
            elif self.lookup_strategy == 'auto_create':
                new_rec = rel_obj.create({match_field: val})
                return new_rec.id
            return False

        elif self.lookup_strategy == 'domain_expr':
            domain = eval(self.lookup_domain or '[]')
            rec = rel_obj.search(domain, limit=1)
            return rec.id if rec else False

        return False

    def _resolve_many2many(self, val):
        """Resolves Many2many record IDs list formatted as ORM command list [(6, 0, [ids])]."""
        rel_model = self.relation_model
        if not rel_model or not val:
            return False

        rel_obj = self.env[rel_model]
        items = [i.strip() for i in str(val).split(',')] if isinstance(val, str) else ([val] if not isinstance(val, list) else val)
        ids = []

        match_field = self.lookup_field_id.name if self.lookup_field_id else 'name'

        for item in items:
            if not item:
                continue
            if self.lookup_strategy == 'record_map':
                rec_id = self._resolve_from_record_map(item)
                if rec_id:
                    ids.append(rec_id)
            elif self.lookup_strategy == 'xml_id':
                xml_id = str(item).strip()
                if '.' not in xml_id:
                    xml_id = f"__import__.{xml_id}"
                rec = self.env.ref(xml_id, raise_if_not_found=False)
                if rec:
                    ids.append(rec.id)
            else:
                rec = rel_obj.search([(match_field, '=', item)], limit=1)
                if rec:
                    ids.append(rec.id)
                elif self.lookup_strategy == 'auto_create':
                    new_rec = rel_obj.create({match_field: item})
                    ids.append(new_rec.id)

        return [(6, 0, ids)] if ids else False
