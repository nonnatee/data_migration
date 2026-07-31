# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MigrationTemplate(models.Model):
    _name = 'migration.template'
    _description = 'Data Migration Mapping Template'
    _order = 'name asc'

    name = fields.Char(string='Template Name', required=True)
    connection_id = fields.Many2one('migration.connection', string='Data Connection', required=True, ondelete='cascade')
    target_model_id = fields.Many2one('ir.model', string='Target Odoo Model', required=True, ondelete='cascade')
    target_model_name = fields.Char(related='target_model_id.model', string='Model Name', store=True, readonly=True)

    operation_mode = fields.Selection([
        ('upsert', 'Upsert (Update or Create)'),
        ('create_only', 'Create New Records Only'),
        ('update_only', 'Update Existing Records Only'),
        ('skip_existing', 'Skip Existing Records'),
    ], string='Operation Mode', default='upsert', required=True)

    active = fields.Boolean(default=True)
    batch_size = fields.Integer(string='Batch Execution Size', default=500, help='Number of records processed per database savepoint transaction.')
    
    mapping_line_ids = fields.One2many('migration.mapping.line', 'template_id', string='Field Mapping Rules', copy=True)
    job_ids = fields.One2many('migration.job', 'template_id', string='Execution History')

    record_map_count = fields.Integer(string='Mapped Records Count', compute='_compute_record_map_count')

    def _compute_record_map_count(self):
        for rec in self:
            rec.record_map_count = self.env['migration.record.map'].search_count([('template_id', '=', rec.id)])

    def action_auto_map_fields(self):
        """Auto-match discovered source columns with target Odoo model field names/labels."""
        self.ensure_one()
        if not self.connection_id.source_columns:
            self.connection_id.action_test_connection()
        
        import json
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

    def action_get_visual_mapping_data(self):
        """Fetch visual diagram schema data for sources, targets, and active connections."""
        self.ensure_one()
        import json
        
        # 1. Source columns from connection
        source_cols = []
        if self.connection_id.source_columns:
            try:
                source_cols = json.loads(self.connection_id.source_columns)
            except Exception:
                source_cols = []
        
        # 2. Target fields from model
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

        # 3. Existing mapping lines
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
                    'input_date_format': t.input_date_format,
                    'output_date_format': t.output_date_format,
                    'tz_offset_hours': t.tz_offset_hours,
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

        # 4. Available transformation presets
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
        # mapping_data is list of mapping lines
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

            # Update transforms for this line
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
                    'input_date_format': t_item.get('input_date_format', '%Y-%m-%d'),
                    'output_date_format': t_item.get('output_date_format', '%Y-%m-%d'),
                    'tz_offset_hours': t_item.get('tz_offset_hours', 0.0),
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
                }

                if t_id and isinstance(t_id, int):
                    t_rec = TransformObj.browse(t_id)
                    t_rec.write(t_vals)
                    kept_t_ids.add(t_id)
                else:
                    t_rec = TransformObj.create(t_vals)
                    kept_t_ids.add(t_rec.id)

            # Unlink removed transforms
            removed_t = existing_t_ids - kept_t_ids
            if removed_t:
                TransformObj.browse(list(removed_t)).unlink()

        # Unlink removed lines
        removed_lines = existing_line_ids - kept_line_ids
        if removed_lines:
            LineObj.browse(list(removed_lines)).unlink()

        return True
