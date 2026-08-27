# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MigrationPlanStep(models.Model):
    _name = 'migration.plan.step'
    _description = 'Migration Plan Step'
    _order = 'sequence asc, id asc'

    stage_id = fields.Many2one('migration.plan.stage', string='Stage', required=True, ondelete='cascade')
    plan_id = fields.Many2one(related='stage_id.plan_id', string='Plan', store=True, readonly=True)
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Step Name', compute='_compute_name', store=True, readonly=False)

    template_id = fields.Many2one('migration.template', string='Mapping Template', required=True, ondelete='restrict')
    target_model_name = fields.Char(related='template_id.target_model_name', string='Target Model', store=True, readonly=True)
    connection_id = fields.Many2one(related='template_id.connection_id', string='Connection', readonly=True)

    error_policy = fields.Selection([
        ('abort_plan', 'Abort Entire Plan'),
        ('abort_stage', 'Abort Current Stage & Continue'),
        ('continue_with_warning', 'Continue Step-by-Step with Warnings'),
    ], string='Step Error Policy', help='Leave empty to inherit from Stage/Plan default.')

    sample_limit = fields.Integer(string='Record Limit', default=0, help='0 for unlimited; positive number to limit processed rows during test.')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'In Progress'),
        ('done', 'Completed'),
        ('done_with_errors', 'Completed with Errors'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ], string='Status', default='draft', readonly=True, index=True, copy=False)

    last_job_id = fields.Many2one('migration.job', string='Last Executed Job', readonly=True, copy=False)
    total_records = fields.Integer(string='Total Records', default=0)
    processed_records = fields.Integer(string='Processed Records', default=0)
    success_records = fields.Integer(string='Success Records', default=0)
    error_records = fields.Integer(string='Failed Records', default=0)
    progress_percent = fields.Float(string='Progress (%)', compute='_compute_progress', store=True)

    @api.depends('template_id', 'name')
    def _compute_name(self):
        for step in self:
            if not step.name and step.template_id:
                step.name = step.template_id.name

    @api.depends('total_records', 'processed_records')
    def _compute_progress(self):
        for step in self:
            if step.total_records > 0:
                step.progress_percent = round((step.processed_records / step.total_records) * 100.0, 2)
            else:
                step.progress_percent = 0.0

    def _execute_step(self, run=False, dry_run=False, limit=0):
        """Executes this step by creating and running a migration.job."""
        self.ensure_one()
        template = self.template_id
        if not template:
            raise UserError(_("Step '%s' has no mapping template configured.") % self.name)

        job = self.env['migration.job'].create({
            'template_id': template.id,
        })

        # Execute Job
        effective_limit = limit or self.sample_limit or 0
        job._execute_job(limit=effective_limit, stage_name=self.stage_id.name, step_name=self.name)

        # Update step metrics
        self.write({
            'last_job_id': job.id,
            'total_records': job.total_records,
            'processed_records': job.processed_records,
            'success_records': job.success_records,
            'error_records': job.error_records,
        })

        return job

    def action_execute_step(self):
        """Execute this single step via plan runner."""
        self.ensure_one()
        return self.plan_id.execute_plan(stage_id=self.stage_id.id, step_id=self.id)
