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

    # Split Stages: Transformation Stage & Target Field Mapping Stage
    transform_line_ids = fields.One2many('migration.transformation.line', 'template_id', string='Transformation Stage Rules', copy=True)
    mapping_line_ids = fields.One2many('migration.mapping.line', 'template_id', string='Field Mapping Rules', copy=True)
    validation_rule_ids = fields.One2many('migration.validation.rule', 'template_id', string='Validation Rules', copy=True)
    job_ids = fields.One2many('migration.job', 'template_id', string='Execution History')

    transform_line_count = fields.Integer(string='Transformations Count', compute='_compute_stage_counts')
    mapping_line_count = fields.Integer(string='Mappings Count', compute='_compute_stage_counts')
    record_map_count = fields.Integer(string='Mapped Records Count', compute='_compute_stage_counts')
    validation_rule_count = fields.Integer(string='Validation Rules Count', compute='_compute_stage_counts')
    quality_score = fields.Float(string='Data Quality Score (%)', default=100.0, readonly=True)
    quality_report = fields.Text(string='Quality Audit Report', readonly=True)

    def _compute_stage_counts(self):
        for rec in self:
            rec.transform_line_count = len(rec.transform_line_ids)
            rec.mapping_line_count = len(rec.mapping_line_ids)
            rec.validation_rule_count = len(rec.validation_rule_ids)
            rec.record_map_count = self.env['migration.record.map'].search_count([('template_id', '=', rec.id)])

    def get_available_source_variables(self):
        """Returns list of all available variables (raw source columns + derived output variables)."""
        self.ensure_one()
        if self.extraction_id:
            raw_cols = self.extraction_id.get_extraction_columns()
        else:
            raw_cols = json.loads(self.connection_id.source_columns or '[]')
        derived_cols = [t.output_field for t in self.transform_line_ids if t.output_field]
        all_vars = list(dict.fromkeys(raw_cols + derived_cols))
        return all_vars

    # ------------------------------------------------------------
    # 1. TRANSFORMATION & MAPPING STAGE RUNNERS
    # ------------------------------------------------------------

    def _apply_transformation_stage(self, raw_row):
        """Executes all transformation stage rules sequentially on a raw row dictionary."""
        self.ensure_one()
        clean_dict = dict(raw_row)
        for tline in self.transform_line_ids.sorted('sequence'):
            if not tline.active:
                continue
            tline.apply_transformation(clean_dict)
        return clean_dict

    def _apply_mapping_stage(self, clean_row):
        """Maps clean record dictionary to target Odoo field values."""
        self.ensure_one()
        target_vals = {}
        for mline in self.mapping_line_ids.sorted('sequence'):
            val = mline.resolve_value(clean_row)
            if val is not False or mline.target_field_ttype == 'boolean':
                target_vals[mline.target_field_name] = val
        return target_vals

    # ------------------------------------------------------------
    # 2. AUTO-MAPPING & AI ASSISTANTS
    # ------------------------------------------------------------

    def action_auto_map_fields(self):
        """Standard heuristic matching of available source/derived variables to target model fields."""
        self.ensure_one()
        available_vars = self.get_available_source_variables()
        if not available_vars:
            self.connection_id.action_test_connection()
            available_vars = self.get_available_source_variables()

        if not available_vars:
            raise UserError(_("No source columns found in connection. Please test the connection first."))

        target_fields = self.env['ir.model.fields'].search([
            ('model_id', '=', self.target_model_id.id),
            ('store', '=', True),
            ('readonly', '=', False),
        ])

        field_map = {f.name.lower(): f for f in target_fields}
        field_label_map = {f.field_description.lower(): f for f in target_fields}

        existing_targets = set(self.mapping_line_ids.mapped('target_field_id.id'))
        created_count = 0

        for col in available_vars:
            col_clean = col.strip().lower().replace(' ', '_').replace('-', '_')
            match_field = field_map.get(col_clean) or field_label_map.get(col.strip().lower())

            if match_field and match_field.id not in existing_targets:
                self.env['migration.mapping.line'].create({
                    'template_id': self.id,
                    'source_field': col,
                    'target_field_id': match_field.id,
                    'is_key_field': match_field.name in ('id', 'code', 'ref', 'default_code', 'email', 'vat'),
                })
                existing_targets.add(match_field.id)
                created_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Auto-Mapping Completed'),
                'message': _('Auto-mapped %d field pairs from %d available variables.', created_count, len(available_vars)),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_ai_auto_map_fields(self):
        """Uses AI LLM to semantically match source variables to Odoo fields."""
        self.ensure_one()
        ai_config = self.env['migration.ai.config'].get_default_provider()
        if not ai_config:
            raise UserError(_("No AI Provider configured. Please configure an AI provider in AI Assistant Settings."))

        available_vars = self.get_available_source_variables()
        if not available_vars:
            raise UserError(_("No source variables available to map."))

        target_fields = self.env['ir.model.fields'].search([
            ('model_id', '=', self.target_model_id.id),
            ('store', '=', True),
            ('readonly', '=', False),
        ])

        fields_meta = [{'name': f.name, 'description': f.field_description, 'type': f.ttype} for f in target_fields[:120]]

        prompt = f"""
Given the source variables: {json.dumps(available_vars)}
And the target Odoo model '{self.target_model_name}' fields:
{json.dumps(fields_meta)}

Map each source variable to the most appropriate Odoo target field.
Return a JSON array of mapping objects with keys:
- "source_field": name of the source variable
- "target_field": name of the Odoo field
- "is_key_field": boolean (true if unique identifier)
"""
        res = ai_config.call_ai_completion(prompt, json_mode=True)
        mappings = res if isinstance(res, list) else (res.get('mappings') or res.get('items') or [])
        created_cnt = 0

        target_by_name = {f.name: f for f in target_fields}
        existing_targets = set(self.mapping_line_ids.mapped('target_field_id.id'))

        for m in mappings:
            src = m.get('source_field')
            tf_name = m.get('target_field')
            tf = target_by_name.get(tf_name)
            if src and tf and tf.id not in existing_targets:
                self.env['migration.mapping.line'].create({
                    'template_id': self.id,
                    'source_field': src,
                    'target_field_id': tf.id,
                    'is_key_field': bool(m.get('is_key_field', False)),
                })
                existing_targets.add(tf.id)
                created_cnt += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AI Auto-Mapping Completed'),
                'message': _('AI successfully mapped %d fields.', created_cnt),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_ai_suggest_validation_rules(self):
        """Uses AI to suggest data validation rules based on target model and schema."""
        self.ensure_one()
        ai_config = self.env['migration.ai.config'].get_default_provider()
        if not ai_config:
            raise UserError(_("No AI Provider configured."))

        mappings_summary = [{'source': m.source_field, 'target': m.target_field_name, 'type': m.target_field_ttype} for m in self.mapping_line_ids]

        prompt = f"""
Target Odoo Model: {self.target_model_name}
Field Mappings: {json.dumps(mappings_summary)}

Analyze this ETL setup and suggest 3 to 6 essential validation rules (e.g. mandatory checks, email regex, price range >= 0).
Output a JSON array of rule objects with keys:
- "name": Rule Title
- "source_field": Source column name
- "rule_type": One of ('mandatory', 'regex', 'numeric_range', 'value_in_set', 'foreign_key')
- "regex_pattern": string (if regex)
- "min_value": float (if numeric_range)
- "action_on_failure": One of ('warning', 'reject_record', 'abort_stage')
- "error_message": User-friendly error text
"""
        res = ai_config.call_ai_completion(prompt, json_mode=True)
        rules = res if isinstance(res, list) else (res.get('rules') or res.get('items') or [])
        created_cnt = 0

        for r in rules:
            src = r.get('source_field')
            rtype = r.get('rule_type', 'mandatory')
            if src:
                self.env['migration.validation.rule'].create({
                    'template_id': self.id,
                    'name': r.get('name', f"Check {src}"),
                    'source_field': src,
                    'rule_type': rtype if rtype in ('mandatory', 'regex', 'numeric_range', 'value_in_set', 'foreign_key') else 'mandatory',
                    'regex_pattern': r.get('regex_pattern', ''),
                    'min_value': float(r.get('min_value', 0.0)),
                    'action_on_failure': r.get('action_on_failure', 'reject_record'),
                    'error_message': r.get('error_message', f"Validation failed on {src}"),
                })
                created_cnt += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AI Validation Rules Created'),
                'message': _('AI suggested and generated %d validation rules.', created_cnt),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_audit_data_quality(self):
        """Audits source data quality, computing a 0-100% health score and report."""
        self.ensure_one()
        records, cols = self.connection_id._fetch_raw_records(limit=200)
        if not records:
            raise UserError(_("No records fetched from connection to audit."))

        total_rows = len(records)
        issues = []
        scores = []

        # 1. Null ratio audit
        for col in cols:
            null_count = sum(1 for r in records if r.get(col) is None or str(r.get(col)).strip() == '')
            null_pct = (null_count / total_rows) * 100.0
            if null_pct > 30.0:
                issues.append(f"Column '{col}' has {null_pct:.1f}% missing/null values.")
                scores.append(max(0, 100.0 - null_pct))
            else:
                scores.append(100.0)

        # 2. Key duplicates audit
        key_lines = self.mapping_line_ids.filtered(lambda l: l.is_key_field)
        if key_lines:
            keys = [str(r.get(key_lines[0].source_field, '')) for r in records if r.get(key_lines[0].source_field)]
            dups = len(keys) - len(set(keys))
            if dups > 0:
                issues.append(f"Key column '{key_lines[0].source_field}' contains {dups} duplicate values in sample batch.")
                scores.append(max(0, 100.0 - (dups / total_rows * 100.0)))

        overall_score = round(sum(scores) / len(scores), 1) if scores else 100.0
        report = f"Data Quality Audit for '{self.name}'\nSample Size: {total_rows} records\nOverall Health Score: {overall_score}%\n\n"
        if issues:
            report += "Detected Issues:\n" + "\n".join(f"• {i}" for i in issues)
        else:
            report += "All audited columns show high completeness and zero key collisions."

        self.write({
            'quality_score': overall_score,
            'quality_report': report,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Data Quality Audit Completed'),
                'message': _('Data Health Score: %s%%. See report tab for breakdown.', overall_score),
                'type': 'info',
                'sticky': False,
            }
        }

    # ------------------------------------------------------------
    # 3. INTERACTIVE VISUAL MAPPER DATA API
    # ------------------------------------------------------------

    def action_get_visual_mapping_data(self):
        """API endpoint providing schema, transformations, and mappings for Visual Mapper Widget."""
        self.ensure_one()
        raw_cols = json.loads(self.connection_id.source_columns or '[]')
        available_vars = self.get_available_source_variables()

        target_fields = self.env['ir.model.fields'].search([
            ('model_id', '=', self.target_model_id.id),
            ('store', '=', True),
            ('readonly', '=', False),
        ], order='field_description asc, name asc')

        target_fields_data = [{
            'id': f.id,
            'name': f.name,
            'field_description': f.field_description or f.name,
            'ttype': f.ttype,
            'relation': f.relation or '',
            'required': f.required,
        } for f in target_fields]

        transform_data = [{
            'id': t.id,
            'sequence': t.sequence,
            'name': t.name,
            'source_field': t.source_field,
            'output_field': t.output_field,
            'transform_category': t.transform_category,
            'cleansing_type': t.cleansing_type,
            'pad_char': t.pad_char,
            'pad_count': t.pad_count,
            'regex_pattern': t.regex_pattern,
            'regex_replace': t.regex_replace,
            'input_date_format': t.input_date_format,
            'output_date_format': t.output_date_format,
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
        } for t in self.transform_line_ids.sorted('sequence')]

        mapping_data = [{
            'id': m.id,
            'sequence': m.sequence,
            'source_field': m.source_field,
            'target_field_id': m.target_field_id.id,
            'target_field_name': m.target_field_name,
            'target_field_ttype': m.target_field_ttype,
            'default_value': m.default_value or '',
            'is_key_field': m.is_key_field,
            'lookup_strategy': m.lookup_strategy or 'field_search',
            'lookup_field_id': m.lookup_field_id.id if m.lookup_field_id else False,
            'lookup_domain': m.lookup_domain or '',
        } for m in self.mapping_line_ids.sorted('sequence')]

        presets = self.env['migration.transform.template'].search([])
        presets_data = [{
            'id': p.id,
            'name': p.name,
            'category': p.category,
            'step_count': p.step_count,
        } for p in presets]

        return {
            'template_id': self.id,
            'template_name': self.name,
            'connection_name': self.connection_id.name,
            'target_model_name': self.target_model_name,
            'raw_columns': raw_cols,
            'available_variables': available_vars,
            'target_fields': target_fields_data,
            'transformations': transform_data,
            'mappings': mapping_data,
            'transform_presets': presets_data,
        }

    def action_save_visual_mapping_data(self, transformations, mappings):
        """Saves transformations and mappings submitted from the OWL 3 Visual Mapper."""
        self.ensure_one()

        # 1. Update Transformations Stage
        self.transform_line_ids.unlink()
        for idx, t in enumerate(transformations):
            self.env['migration.transformation.line'].create({
                'template_id': self.id,
                'sequence': (idx + 1) * 10,
                'source_field': t.get('source_field'),
                'output_field': t.get('output_field') or t.get('source_field'),
                'transform_category': t.get('transform_category', 'cleansing'),
                'cleansing_type': t.get('cleansing_type', 'trim'),
                'pad_char': t.get('pad_char', '0'),
                'pad_count': t.get('pad_count', 10),
                'regex_pattern': t.get('regex_pattern', ''),
                'regex_replace': t.get('regex_replace', ''),
                'input_date_format': t.get('input_date_format', '%Y-%m-%d'),
                'output_date_format': t.get('output_date_format', '%Y-%m-%d'),
                'unit_type': t.get('unit_type', 'mass'),
                'source_unit': t.get('source_unit', 'kg'),
                'target_unit': t.get('target_unit', 'lb'),
                'custom_scale_ratio': t.get('custom_scale_ratio', 1.0),
                'target_type': t.get('target_type', 'string'),
                'value_mapping_json': t.get('value_mapping_json', '{}'),
                'python_code': t.get('python_code', ''),
                'default_fallback': t.get('default_fallback', ''),
                'math_op': t.get('math_op', 'add'),
                'math_operand': t.get('math_operand', 0.0),
                'math_round_precision': t.get('math_round_precision', 2),
                'slice_mode': t.get('slice_mode', 'slice'),
                'slice_start': t.get('slice_start', 0),
                'slice_end': t.get('slice_end', 10),
                'slice_length': t.get('slice_length', 5),
                'split_delimiter': t.get('split_delimiter', ','),
                'split_index': t.get('split_index', 0),
                'case_when_json': t.get('case_when_json', '[]'),
                'ai_prompt_template': t.get('ai_prompt_template', ''),
            })

        # 2. Update Target Field Mappings Stage
        self.mapping_line_ids.unlink()
        for idx, m in enumerate(mappings):
            tf_id = m.get('target_field_id')
            src = m.get('source_field')
            if tf_id and src:
                self.env['migration.mapping.line'].create({
                    'template_id': self.id,
                    'sequence': (idx + 1) * 10,
                    'source_field': src,
                    'target_field_id': int(tf_id),
                    'default_value': m.get('default_value', ''),
                    'is_key_field': bool(m.get('is_key_field', False)),
                    'lookup_strategy': m.get('lookup_strategy', 'field_search'),
                    'lookup_field_id': int(m.get('lookup_field_id')) if m.get('lookup_field_id') else False,
                    'lookup_domain': m.get('lookup_domain', ''),
                })

        return True

    def action_open_run_wizard(self):
        """Opens quick execution wizard for this template."""
        self.ensure_one()
        return {
            'name': _('Run Migration Job: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'migration.run.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_template_id': self.id,
            }
        }

    def action_view_record_mappings(self):
        self.ensure_one()
        return {
            'name': _('Cross-Reference Records: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'migration.record.map',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
            'context': {'default_template_id': self.id},
        }
