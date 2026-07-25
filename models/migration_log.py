# -*- coding: utf-8 -*-

from odoo import fields, models


class MigrationLog(models.Model):
    _name = 'migration.log'
    _description = 'Migration Job Log Entry'
    _order = 'id desc'

    job_id = fields.Many2one('migration.job', string='Migration Job', required=True, ondelete='cascade')
    template_id = fields.Many2one(related='job_id.template_id', store=True, readonly=True)

    log_type = fields.Selection([
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], string='Log Level', default='info', required=True, index=True)

    row_number = fields.Integer(string='Row #')
    source_key = fields.Char(string='Source Key / ID')
    message = fields.Text(string='Message')
    error_traceback = fields.Text(string='Error Traceback')
    raw_data = fields.Text(string='Raw Source Data (JSON)')
    target_record_id = fields.Integer(string='Target Odoo Record ID')
