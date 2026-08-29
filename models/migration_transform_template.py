# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MigrationTransformTemplate(models.Model):
    _name = 'migration.transform.template'
    _description = 'Reusable Data Transformation Preset'
    _order = 'name asc'

    name = fields.Char(string='Preset Name', required=True)
    description = fields.Text(string='Description')
    category = fields.Selection([
        ('general', 'General Transformation'),
        ('cleansing', 'Data Cleansing & Sanitization'),
        ('formatting', 'Text & Date Formatting'),
        ('math', 'Math & Arithmetic Calculations'),
        ('unit', 'Unit Conversion'),
        ('type', 'Type Casting'),
        ('ai', 'AI NLP Pipeline'),
    ], string='Preset Category', default='general', required=True)

    active = fields.Boolean(default=True)
    step_ids = fields.One2many('migration.transform.template.step', 'template_id', string='Transformation Steps', copy=True)
    step_count = fields.Integer(string='Steps Count', compute='_compute_step_count')

    @api.depends('step_ids')
    def _compute_step_count(self):
        for rec in self:
            rec.step_count = len(rec.step_ids)

    def action_apply_to_template(self, template, source_field, output_field=None):
        """Applies preset steps as transformation lines directly to a migration.template."""
        self.ensure_one()
        if not template or not source_field:
            return False
        out_f = output_field or source_field
        TransformLine = self.env['migration.transformation.line']
        created_lines = self.env['migration.transformation.line']
        for step in self.step_ids.sorted('sequence'):
            line = TransformLine.create({
                'template_id': template.id,
                'sequence': (len(template.transform_line_ids) + 1) * 10,
                'source_field': source_field,
                'output_field': out_f,
                'apply_filter': step.apply_filter,
                'filter_field': step.filter_field or source_field,
                'filter_operator': step.filter_operator,
                'filter_value': step.filter_value,
                'filter_action': step.filter_action,
                'transform_category': step.transform_category,
                'cleansing_type': step.cleansing_type,
                'pad_char': step.pad_char,
                'pad_count': step.pad_count,
                'regex_pattern': step.regex_pattern,
                'regex_replace': step.regex_replace,
                'regex_group_index': step.regex_group_index,
                'input_date_format': step.input_date_format,
                'output_date_format': step.output_date_format,
                'tz_offset_hours': step.tz_offset_hours,
                'date_math_days': step.date_math_days,
                'unit_type': step.unit_type,
                'source_unit': step.source_unit,
                'target_unit': step.target_unit,
                'custom_scale_ratio': step.custom_scale_ratio,
                'target_type': step.target_type,
                'value_mapping_json': step.value_mapping_json,
                'python_code': step.python_code,
                'default_fallback': step.default_fallback,
                'math_op': step.math_op,
                'math_operand': step.math_operand,
                'math_round_precision': step.math_round_precision,
                'slice_start': step.slice_start,
                'slice_end': step.slice_end,
                'slice_length': step.slice_length,
                'slice_mode': step.slice_mode,
                'split_delimiter': step.split_delimiter,
                'split_index': step.split_index,
                'case_when_json': step.case_when_json,
                'ai_prompt_template': step.ai_prompt_template,
            })
            created_lines |= line
        return created_lines
