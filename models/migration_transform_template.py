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

    def action_apply_to_line(self, line):
        """Applies preset steps to the specified mapping line."""
        self.ensure_one()
        if not line:
            return False

        line.transform_ids.unlink()

        TransformObj = self.env['migration.mapping.transform']
        for step in self.step_ids.sorted('sequence'):
            TransformObj.create({
                'line_id': line.id,
                'sequence': step.sequence,
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
        return True

    @api.model
    def create_preset_from_line(self, line, preset_name, category='general'):
        """Creates a reusable preset template from an existing mapping line's transform steps."""
        if not line or not line.transform_ids:
            raise UserError(_("Selected field mapping line has no transformation steps."))

        preset = self.create({
            'name': preset_name,
            'category': category,
            'description': _("Exported from field mapping: %s -> %s") % (line.source_field, line.target_field_name),
        })

        StepObj = self.env['migration.transform.template.step']
        for t in line.transform_ids.sorted('sequence'):
            StepObj.create({
                'template_id': preset.id,
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
                'slice_start': t.slice_start,
                'slice_end': t.slice_end,
                'slice_length': t.slice_length,
                'slice_mode': t.slice_mode,
                'split_delimiter': t.split_delimiter,
                'split_index': t.split_index,
                'case_when_json': t.case_when_json,
                'ai_prompt_template': t.ai_prompt_template,
            })

        return preset
