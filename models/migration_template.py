# -*- coding: utf-8 -*-

import json
import logging
import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MigrationTemplate(models.Model):
    _name = 'migration.template'
    _description = 'Data Migration Mapping Template'
    _order = 'name asc'

    name = fields.Char(string='Template Name', required=True)
    connection_id = fields.Many2one('migration.connection', string='Data Connection', required=True, ondelete='cascade')
    extraction_id = fields.Many2one('migration.extraction', string='Extraction Query / Watermark', ondelete='set null')
    target_model_id = fields.Many2one('ir.model', string='Target Odoo Model', required=True, ondelete='cascade')
    target_model_name = fields.Char(related='target_model_id.model', string='Model Name', store=True, readonly=True)

    operation_mode = fields.Selection([
        ('upsert', 'Upsert (Update Existing or Create New)'),
        ('create_only', 'Create New Records Only'),
        ('update_only', 'Update Existing Records Only'),
        ('skip_existing', 'Skip Existing Records (Insert New Only)'),
    ], string='Operation Mode', default='upsert', required=True)

    active = fields.Boolean(default=True)
    batch_size = fields.Integer(string='Batch Savepoint Size', default=500,
                               help='Number of records processed per database savepoint transaction.')

    # Performance / Context Bypasses
    bypass_tracking = fields.Boolean(string='Disable Chatter Tracking', default=True,
                                     help='Bypasses mail.thread chatter tracking for faster bulk insertion.')
    bypass_subscription = fields.Boolean(string='Disable Auto-Followers', default=True,
                                         help='Prevents subscribing default followers during mass creation.')

    # Mapping & Validation Lines
    mapping_line_ids = fields.One2many('migration.mapping.line', 'template_id', string='Field Mapping Rules', copy=True)
    validation_rule_ids = fields.One2many('migration.validation.rule', 'template_id', string='Validation Rules', copy=True)
    job_ids = fields.One2many('migration.job', 'template_id', string='Execution History')

    record_map_count = fields.Integer(string='Mapped Records Count', compute='_compute_record_map_count')
    validation_rule_count = fields.Integer(string='Validation Rules Count', compute='_compute_validation_rule_count')
    quality_score = fields.Float(string='Data Quality Score (%)', default=100.0, readonly=True)
    quality_report = fields.Text(string='Quality Audit Report', readonly=True)

    def _compute_record_map_count(self):
        for rec in self:
            rec.record_map_count = self.env['migration.record.map'].search_count([('template_id', '=', rec.id)])

    def _compute_validation_rule_count(self):
        for rec in self:
            rec.validation_rule_count = len(rec.validation_rule_ids)

    # ------------------------------------------------------------
    # 1. AUTO MAPPING (HEURISTIC + AI)
    # ------------------------------------------------------------

    def action_auto_map_fields(self):
        """Standard heuristic matching of source columns to target model fields."""
        self.ensure_one()
        if not self.connection_id.source_columns:
            self.connection_id.action_test_connection()

        source_cols = json.loads(self.connection_id.source_columns or '[]')
        if not source_cols:
            raise UserError(_("No source columns found in connection. Please test the connection first."))

        target_fields = self.env['ir.model.fields'].search([
            ('model_id', '=', self.target_model_id.id),
            ('store', '=', True),
            ('readonly', '=', False),
        ])

        field_map = {f.name.lower(): f for f in target_fields}
        field_label_map = {f.field_description.lower(): f for f in target_fields}

        existing_sources = set(self.mapping_line_ids.mapped('source_field'))
        created_count = 0

        for col in source_cols:
            if col in existing_sources:
                continue
            col_clean = col.strip().lower().replace(' ', '_').replace('-', '_')
            match_field = field_map.get(col_clean) or field_label_map.get(col.strip().lower())

            if match_field:
                self.env['migration.mapping.line'].create({
                    'template_id': self.id,
                    'source_field': col,
                    'target_field_id': match_field.id,
                    'transform_type': 'direct',
                    'is_key_field': match_field.name in ('id', 'code', 'ref', 'default_code', 'email', 'vat'),
                })
                created_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Auto Mapping Complete'),
                'message': _('Auto-mapped %s fields matching model %s.', created_count, self.target_model_name),
                'type': 'success',
            }
        }

    def action_ai_auto_map_fields(self):
        """AI-powered semantic mapping of source columns to target Odoo fields."""
        self.ensure_one()
        ai_config = self.env['migration.ai.config'].get_default_provider()
        if not ai_config:
            raise UserError(_("No active AI provider configured. Please configure an AI Provider under ETL Setup -> AI Assistant."))

        if not self.connection_id.source_columns:
            self.connection_id.action_test_connection()

        source_cols = json.loads(self.connection_id.source_columns or '[]')
        preview_data = json.loads(self.connection_id.preview_data or '[]')[:3]

        target_fields = self.env['ir.model.fields'].search([
            ('model_id', '=', self.target_model_id.id),
            ('store', '=', True),
            ('readonly', '=', False),
        ])

        target_fields_info = [
            {'name': f.name, 'description': f.field_description, 'type': f.ttype, 'required': f.required, 'relation': f.relation or ''}
            for f in target_fields
        ]

        prompt = f"""
Given the following source columns and sample preview data from a legacy database:
Source Columns: {json.dumps(source_cols)}
Sample Rows: {json.dumps(preview_data, default=str)}

Target Odoo 19 Model: '{self.target_model_name}'
Available Target Fields:
{json.dumps(target_fields_info, indent=2)}

Task:
Map each source column to the most semantically accurate target field.
Return a JSON array of objects with the structure:
[
  {{
    "source_field": "SourceColName",
    "target_field_name": "target_odoo_field_name",
    "is_key_field": true/false,
    "confidence": 0.95,
    "reason": "Brief rationale"
  }}
]
Only include valid mappings where target_field_name exists in the available target fields list.
"""
        sys_prompt = "You are an AI ERP Data Architect specializing in Odoo database schemas. Return pure JSON array."
        try:
            mappings = ai_config.call_ai_completion(prompt, system_prompt=sys_prompt, json_mode=True)
            if isinstance(mappings, dict) and 'mappings' in mappings:
                mappings = mappings['mappings']

            if not isinstance(mappings, list):
                raise UserError(_("AI did not return a valid list of mappings."))

            target_field_by_name = {f.name: f for f in target_fields}
            existing_sources = set(self.mapping_line_ids.mapped('source_field'))
            created_count = 0

            for m in mappings:
                s_col = m.get('source_field')
                t_name = m.get('target_field_name')
                if s_col in existing_sources or not s_col or not t_name:
                    continue

                t_field = target_field_by_name.get(t_name)
                if t_field:
                    self.env['migration.mapping.line'].create({
                        'template_id': self.id,
                        'source_field': s_col,
                        'target_field_id': t_field.id,
                        'is_key_field': bool(m.get('is_key_field', False)),
                        'transform_type': 'direct',
                    })
                    created_count += 1

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('AI Auto-Mapping Complete'),
                    'message': _('AI created %d smart field mappings with high confidence for model %s.', created_count, self.target_model_name),
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.exception("AI Auto-Mapping failed on template %s", self.id)
            raise UserError(_("AI Auto-Mapping failed: %s") % str(e))

    # ------------------------------------------------------------
    # 2. AI VALIDATION RULE SUGGESTER
    # ------------------------------------------------------------

    def action_ai_suggest_validation_rules(self):
        """AI analyzes target model constraints and source schema to suggest validation rules."""
        self.ensure_one()
        ai_config = self.env['migration.ai.config'].get_default_provider()
        if not ai_config:
            raise UserError(_("No active AI provider configured."))

        mappings = [{'source': l.source_field, 'target': l.target_field_name, 'type': l.target_field_ttype} for l in self.mapping_line_ids]
        prompt = f"""
Model: {self.target_model_name}
Field Mappings: {json.dumps(mappings)}

Suggest pre-load data validation rules (e.g. required/not-null checks for critical fields, email regex, positive pricing, phone format, foreign key existence).
Return a JSON array with structure:
[
  {{
    "name": "Non-empty Name",
    "source_field": "name",
    "rule_type": "mandatory|regex|numeric_range|value_in_set|foreign_key",
    "regex_pattern": "",
    "min_value": 0.0,
    "max_value": 0.0,
    "action_on_failure": "reject_record",
    "error_message": "Custom error description"
  }}
]
"""
        try:
            suggested_rules = ai_config.call_ai_completion(prompt, json_mode=True)
            if isinstance(suggested_rules, dict) and 'rules' in suggested_rules:
                suggested_rules = suggested_rules['rules']

            if not isinstance(suggested_rules, list):
                raise UserError(_("AI did not return a valid list of validation rules."))

            created_cnt = 0
            for r in suggested_rules:
                self.env['migration.validation.rule'].create({
                    'template_id': self.id,
                    'name': r.get('name', 'Validation Rule'),
                    'source_field': r.get('source_field', ''),
                    'rule_type': r.get('rule_type', 'mandatory') if r.get('rule_type') in ('mandatory', 'regex', 'numeric_range', 'value_in_set', 'foreign_key') else 'mandatory',
                    'regex_pattern': r.get('regex_pattern', ''),
                    'min_value': float(r.get('min_value', 0.0)),
                    'max_value': float(r.get('max_value', 999999.0)),
                    'action_on_failure': r.get('action_on_failure', 'reject_record'),
                    'error_message': r.get('error_message', ''),
                })
                created_cnt += 1

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('AI Validation Rules Created'),
                    'message': _('Created %d validation rules automatically.', created_cnt),
                    'type': 'success',
                }
            }
        except Exception as e:
            raise UserError(_("AI Rule Suggester failed: %s") % str(e))

    # ------------------------------------------------------------
    # 3. AI DATA QUALITY AUDIT & ANOMALY DETECTION
    # ------------------------------------------------------------

    def action_audit_data_quality(self):
        """Scans extracted source data to evaluate quality health score and detect anomalies."""
        self.ensure_one()
        records, columns = self.connection_id._fetch_raw_records(limit=100)
        if not records:
            raise UserError(_("No data found in connection to audit."))

        total_cells = len(records) * len(columns)
        null_cells = 0
        duplicate_keys = 0
        key_fields = self.mapping_line_ids.filtered(lambda l: l.is_key_field).mapped('source_field')

        seen_keys = set()
        for r in records:
            for c in columns:
                if r.get(c) is None or str(r.get(c)).strip() == '':
                    null_cells += 1
            if key_fields:
                key_val = '-'.join(str(r.get(k, '')).strip() for k in key_fields)
                if key_val in seen_keys:
                    duplicate_keys += 1
                seen_keys.add(key_val)

        completeness_ratio = (total_cells - null_cells) / total_cells if total_cells > 0 else 1.0
        dup_penalty = (duplicate_keys / len(records)) if records else 0.0
        score = max(0.0, round((completeness_ratio - dup_penalty) * 100.0, 1))

        report_lines = [
            f"📊 Data Quality Audit Summary for {self.name}",
            f"• Sample Inspected: {len(records)} rows across {len(columns)} columns",
            f"• Completeness Rate: {round(completeness_ratio * 100.0, 1)}% ({null_cells} empty cells)",
            f"• Key Uniqueness: {len(records) - duplicate_keys}/{len(records)} unique ({duplicate_keys} duplicates detected)",
            f"• Overall Health Score: {score}%",
        ]

        self.write({
            'quality_score': score,
            'quality_report': "\n".join(report_lines),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Data Quality Audit: %s%%') % score,
                'message': _("Sample audit complete. Completeness: %s%%, Duplicates: %d.") % (round(completeness_ratio * 100.0, 1), duplicate_keys),
                'type': 'success' if score >= 80 else 'warning',
            }
        }

    # ------------------------------------------------------------
    # 4. VISUAL MAPPER SCHEMA DATA
    # ------------------------------------------------------------

    def action_get_visual_mapping_data(self):
        """Fetch visual diagram schema data for sources, targets, and active connections."""
        self.ensure_one()
        source_cols = []
        if self.connection_id.source_columns:
            try:
                source_cols = json.loads(self.connection_id.source_columns)
            except Exception:
                source_cols = []

        target_fields = []
        if self.target_model_id:
            fields_rec = self.env['ir.model.fields'].search([
                ('model_id', '=', self.target_model_id.id),
                ('store', '=', True),
                ('readonly', '=', False),
            ], order='name asc')
            for f in fields_rec:
                target_fields.append({
                    'id': f.id,
                    'name': f.name,
                    'field_description': f.field_description,
                    'ttype': f.ttype,
                    'relation': f.relation or '',
                    'required': f.required,
                })

        lines = []
        for l in self.mapping_line_ids:
            transforms = []
            for t in l.transform_ids.sorted('sequence'):
                transforms.append({
                    'id': t.id,
                    'sequence': t.sequence,
                    'transform_category': t.transform_category,
                    'cleansing_type': t.cleansing_type,
                    'pad_char': t.pad_char,
                    'pad_count': t.pad_count,
                    'regex_pattern': t.regex_pattern,
                    'regex_replace': t.regex_replace,
                    'regex_group_index': t.regex_group_index,
                    'input_date_format': t.input_date_format,
                    'output_date_format': t.output_date_format,
                    'tz_offset_hours': t.tz_offset_hours,
                    'date_math_days': t.date_math_days,
                    'unit_type': t.unit_type,
                    'source_unit': t.source_unit,
                    'target_unit': t.target_unit,
                    'custom_scale_ratio': t.custom_scale_ratio,
                    'target_type': t.target_type,
                    'value_mapping_json': t.value_mapping_json,
                    'python_code': t.python_code,
                    'default_fallback': t.default_fallback,
                    'math_op': t.math_op,
                    'math_operand': t.math_operand,
                    'math_round_precision': t.math_round_precision,
                    'slice_mode': t.slice_mode,
                    'slice_start': t.slice_start,
                    'slice_end': t.slice_end,
                    'slice_length': t.slice_length,
                    'split_delimiter': t.split_delimiter,
                    'split_index': t.split_index,
                    'case_when_json': t.case_when_json,
                    'ai_prompt_template': t.ai_prompt_template,
                    'name': t.name,
                })

            lines.append({
                'id': l.id,
                'source_field': l.source_field,
                'target_field_id': l.target_field_id.id,
                'target_field_name': l.target_field_name,
                'target_field_ttype': l.target_field_ttype,
                'is_key_field': l.is_key_field,
                'transform_type': l.transform_type,
                'default_value': l.default_value,
                'lookup_strategy': l.lookup_strategy,
                'lookup_field_id': l.lookup_field_id.id if l.lookup_field_id else False,
                'transforms': transforms,
            })

        presets = []
        preset_recs = self.env['migration.transform.template'].search([('active', '=', True)])
        for p in preset_recs:
            presets.append({
                'id': p.id,
                'name': p.name,
                'category': p.category,
                'description': p.description or '',
                'step_count': p.step_count,
            })

        return {
            'template_id': self.id,
            'template_name': self.name,
            'connection_name': self.connection_id.name,
            'target_model_name': self.target_model_name,
            'source_columns': source_cols,
            'target_fields': target_fields,
            'mapping_lines': lines,
            'transform_presets': presets,
        }

    def action_save_visual_mapping(self, mapping_data):
        """Saves updated mappings and transformation steps from visual diagram interface."""
        self.ensure_one()
        LineObj = self.env['migration.mapping.line']
        TransformObj = self.env['migration.mapping.transform']

        existing_line_ids = set(self.mapping_line_ids.ids)
        kept_line_ids = set()

        for item in mapping_data:
            line_id = item.get('id')
            line_vals = {
                'template_id': self.id,
                'source_field': item.get('source_field'),
                'target_field_id': item.get('target_field_id'),
                'is_key_field': item.get('is_key_field', False),
                'transform_type': item.get('transform_type', 'direct'),
                'default_value': item.get('default_value', ''),
                'lookup_strategy': item.get('lookup_strategy', 'field_search'),
                'lookup_field_id': item.get('lookup_field_id', False),
            }

            if line_id and isinstance(line_id, int):
                line_rec = LineObj.browse(line_id)
                line_rec.write(line_vals)
                kept_line_ids.add(line_id)
            else:
                line_rec = LineObj.create(line_vals)
                kept_line_ids.add(line_rec.id)

            transforms_data = item.get('transforms', [])
            existing_t_ids = set(line_rec.transform_ids.ids)
            kept_t_ids = set()

            for seq, t_item in enumerate(transforms_data, 1):
                t_id = t_item.get('id')
                t_vals = {
                    'line_id': line_rec.id,
                    'sequence': seq * 10,
                    'transform_category': t_item.get('transform_category', 'cleansing'),
                    'cleansing_type': t_item.get('cleansing_type', 'trim'),
                    'pad_char': t_item.get('pad_char', '0'),
                    'pad_count': t_item.get('pad_count', 10),
                    'regex_pattern': t_item.get('regex_pattern', ''),
                    'regex_replace': t_item.get('regex_replace', ''),
                    'regex_group_index': t_item.get('regex_group_index', 1),
                    'input_date_format': t_item.get('input_date_format', '%Y-%m-%d'),
                    'output_date_format': t_item.get('output_date_format', '%Y-%m-%d'),
                    'tz_offset_hours': t_item.get('tz_offset_hours', 0.0),
                    'date_math_days': t_item.get('date_math_days', 0),
                    'unit_type': t_item.get('unit_type', 'mass'),
                    'source_unit': t_item.get('source_unit', 'kg'),
                    'target_unit': t_item.get('target_unit', 'lb'),
                    'custom_scale_ratio': t_item.get('custom_scale_ratio', 1.0),
                    'target_type': t_item.get('target_type', 'string'),
                    'value_mapping_json': t_item.get('value_mapping_json', '{}'),
                    'python_code': t_item.get('python_code', ''),
                    'default_fallback': t_item.get('default_fallback', ''),
                    'math_op': t_item.get('math_op', 'add'),
                    'math_operand': t_item.get('math_operand', 0.0),
                    'math_round_precision': t_item.get('math_round_precision', 2),
                    'slice_mode': t_item.get('slice_mode', 'slice'),
                    'slice_start': t_item.get('slice_start', 0),
                    'slice_end': t_item.get('slice_end', 10),
                    'slice_length': t_item.get('slice_length', 5),
                    'split_delimiter': t_item.get('split_delimiter', ','),
                    'split_index': t_item.get('split_index', 0),
                    'case_when_json': t_item.get('case_when_json', '[]'),
                    'ai_prompt_template': t_item.get('ai_prompt_template', ''),
                }

                if t_id and isinstance(t_id, int):
                    t_rec = TransformObj.browse(t_id)
                    t_rec.write(t_vals)
                    kept_t_ids.add(t_id)
                else:
                    t_rec = TransformObj.create(t_vals)
                    kept_t_ids.add(t_rec.id)

            removed_t = existing_t_ids - kept_t_ids
            if removed_t:
                TransformObj.browse(list(removed_t)).unlink()

        removed_lines = existing_line_ids - kept_line_ids
        if removed_lines:
            LineObj.browse(list(removed_lines)).unlink()

        return True

    def action_view_record_mappings(self):
        """View persistent cross-reference mapping records for this template."""
        self.ensure_one()
        return {
            'name': _('Mapped Records (%s)') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'migration.record.map',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
            'context': {'default_template_id': self.id},
        }

    def action_open_run_wizard(self):
        """Open Migration Run Wizard."""
        self.ensure_one()
        return {
            'name': _('Execute Migration Job'),
            'type': 'ir.actions.act_window',
            'res_model': 'migration.run.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_template_id': self.id,
                'default_connection_id': self.connection_id.id,
            }
        }
