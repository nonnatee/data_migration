# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MigrationRunWizard(models.TransientModel):
    _name = 'migration.run.wizard'
    _description = 'Migration Quick Execution Wizard'

    template_id = fields.Many2one('migration.template', string='Mapping Template', required=True)
    connection_id = fields.Many2one(related='template_id.connection_id', string='Data Connection', readonly=True)
    
    override_file = fields.Binary(string='Override Source File', attachment=False, help='Optionally upload a new file to override the connection source for this single run.')
    file_name = fields.Char(string='File Name')

    def action_start_migration(self):
        """Create job record and run ETL migration."""
        self.ensure_one()
        if self.override_file and self.connection_id:
            self.connection_id.write({
                'source_type': 'upload',
                'file_binary': self.override_file,
                'file_name': self.file_name or 'override_import',
            })
            self.connection_id.action_test_connection()

        job = self.env['migration.job'].create({
            'template_id': self.template_id.id,
        })
        job.action_run_migration()

        return {
            'name': _('Migration Job Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'migration.job',
            'res_id': job.id,
            'view_mode': 'form',
            'target': 'current',
        }
