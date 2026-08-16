# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MigrationPlanStage(models.Model):
    _name = 'migration.plan.stage'
    _description = 'Migration Plan Stage'
    _order = 'sequence asc, id asc'

    plan_id = fields.Many2one('migration.plan', string='Migration Plan', required=True, ondelete='cascade')
    name = fields.Char(string='Stage Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Text(string='Stage Description')

    error_policy = fields.Selection([
        ('abort_plan', 'Abort Entire Plan'),
        ('abort_stage', 'Abort Current Stage & Continue'),
        ('continue_with_warning', 'Continue Step-by-Step with Warnings'),
    ], string='Stage Error Policy', help='Leave empty to inherit from Plan default.')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'In Progress'),
        ('done', 'Completed'),
        ('done_with_errors', 'Completed with Errors'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ], string='Status', default='draft', readonly=True, index=True, copy=False)

    step_ids = fields.One2many('migration.plan.step', 'stage_id', string='Steps', copy=True)

    step_count = fields.Integer(string='Steps Count', compute='_compute_metrics')
    total_records = fields.Integer(string='Total Records', compute='_compute_metrics')
    processed_records = fields.Integer(string='Processed Records', compute='_compute_metrics')
    success_records = fields.Integer(string='Success Records', compute='_compute_metrics')
    error_records = fields.Integer(string='Failed Records', compute='_compute_metrics')
    progress_percent = fields.Float(string='Progress (%)', compute='_compute_metrics')

    @api.depends('step_ids.total_records', 'step_ids.processed_records', 'step_ids.success_records', 'step_ids.error_records')
    def _compute_metrics(self):
        for stage in self:
            steps = stage.step_ids
            stage.step_count = len(steps)
            total = sum(steps.mapped('total_records'))
            processed = sum(steps.mapped('processed_records'))
            success = sum(steps.mapped('success_records'))
            errors = sum(steps.mapped('error_records'))

            stage.total_records = total
            stage.processed_records = processed
            stage.success_records = success
            stage.error_records = errors
            stage.progress_percent = round((processed / total * 100.0), 2) if total > 0 else 0.0

    def action_execute_stage(self):
        """Execute this stage via the plan runner."""
        self.ensure_one()
        return self.plan_id.execute_plan(stage_id=self.id)
