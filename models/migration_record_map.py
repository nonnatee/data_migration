# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class MigrationRecordMap(models.Model):
    _name = 'migration.record.map'
    _description = 'Migration Record Cross-Reference Map'
    _order = 'last_migrated desc, id desc'

    template_id = fields.Many2one('migration.template', string='Template', required=True, ondelete='cascade')
    source_key = fields.Char(string='Source Key', required=True, index=True)
    target_model = fields.Char(string='Target Model', required=True, index=True)
    target_id = fields.Integer(string='Target Record ID', required=True, index=True)
    xml_id = fields.Char(string='External ID (XML ID)')
    checksum = fields.Char(string='Data Checksum (MD5)')
    last_migrated = fields.Datetime(string='Last Migrated', default=fields.Datetime.now)

    _sql_constraints = [
        ('template_source_key_uniq', 'unique(template_id, source_key)', 'Source key mapping must be unique per template!'),
    ]

    def action_open_target_record(self):
        """Open target record in standard Odoo form view."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.target_model,
            'res_id': self.target_id,
            'view_mode': 'form',
            'target': 'current',
        }
