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
