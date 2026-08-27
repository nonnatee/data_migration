# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class MigrationLog(models.Model):
    _name = 'migration.log'
    _description = 'Migration Job Log Entry'
    _order = 'id desc'

    job_id = fields.Many2one('migration.job', string='Migration Job', required=True, ondelete='cascade')
    template_id = fields.Many2one(related='job_id.template_id', store=True, readonly=True)
    target_model_name = fields.Char(related='job_id.target_model_name', store=True, readonly=True)

    log_type = fields.Selection([
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('debug', 'Debug'),
    ], string='Log Level', default='info', required=True, index=True)

    stage_name = fields.Char(string='Stage')
    step_name = fields.Char(string='Step')
    row_number = fields.Integer(string='Row #', index=True)
    source_key = fields.Char(string='Source Key / ID', index=True)
    message = fields.Text(string='Message')
    error_traceback = fields.Text(string='Error Traceback')
    raw_data = fields.Text(string='Raw Source Data (JSON)')
    transformed_data = fields.Text(string='Transformed Field Values (JSON)')
    target_record_id = fields.Integer(string='Target Odoo Record ID')
    ai_resolution_suggestion = fields.Text(string='AI Error Resolution Suggestion')

    def action_ask_ai_for_resolution(self):
        """Ask AI to analyze this error log and suggest a fix for field mappings/data."""
        self.ensure_one()
        if self.log_type != 'error' or not self.error_traceback:
            return False

        ai_config = self.env['migration.ai.config'].get_default_provider()
        if not ai_config:
            raise UserError(_("No AI provider configured."))

        prompt = f"""
An ETL Data Migration error occurred when loading data into Odoo model '{self.target_model_name}':
Row Number: {self.row_number}
Source Key: {self.source_key}
Error Message: {self.message}
Traceback:
{self.error_traceback}

Raw Source Data:
{self.raw_data}

Transformed Target Values:
{self.transformed_data}

Please analyze this error and provide:
1. Root cause explanation in plain English.
2. Recommended fix in field mappings, transformation rules, or source data cleansing.
"""
        res = ai_config.call_ai_completion(prompt, json_mode=False)
        self.write({'ai_resolution_suggestion': str(res)})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AI Resolution Advice Generated'),
                'message': _('AI suggested fix has been attached to this log entry.'),
                'type': 'info',
            }
        }
