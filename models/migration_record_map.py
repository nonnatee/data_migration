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
    target_display_name = fields.Char(string='Target Record Name', compute='_compute_target_display_name')
    xml_id = fields.Char(string='External ID (XML ID)', index=True)
    checksum = fields.Char(string='Data Checksum (MD5)')
    last_migrated = fields.Datetime(string='Last Migrated', default=fields.Datetime.now)

    _sql_constraints = [
        ('template_source_key_uniq', 'unique(template_id, source_key)', 'Source key mapping must be unique per template!'),
    ]

    def _compute_target_display_name(self):
        for rec in self:
            if rec.target_model and rec.target_id and rec.target_model in self.env:
                try:
                    target_rec = self.env[rec.target_model].browse(rec.target_id).exists()
                    rec.target_display_name = target_rec.display_name if target_rec else _('[Deleted Record %s]') % rec.target_id
                except Exception:
                    rec.target_display_name = f"ID: {rec.target_id}"
            else:
                rec.target_display_name = f"ID: {rec.target_id}"

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
