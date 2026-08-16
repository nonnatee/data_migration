# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class MigrationPlanRun(models.Model):
    _name = 'migration.plan.run'
    _description = 'Migration Plan Execution Run'
    _order = 'start_time desc, id desc'

    name = fields.Char(string='Run Reference', required=True, default=lambda self: _('New'), copy=False, readonly=True)
    plan_id = fields.Many2one('migration.plan', string='Migration Plan', required=True, ondelete='cascade')
    dry_run = fields.Boolean(string='Simulation Run (Dry-Run)', default=False, readonly=True)

    state = fields.Selection([
        ('running', 'In Progress'),
        ('done', 'Completed'),
        ('done_with_errors', 'Completed with Errors'),
        ('failed', 'Failed'),
        ('aborted', 'Aborted'),
    ], string='Status', default='running', readonly=True, index=True)

    start_time = fields.Datetime(string='Start Time', readonly=True)
    end_time = fields.Datetime(string='End Time', readonly=True)
    duration_seconds = fields.Float(string='Duration (Sec)', compute='_compute_duration', store=True)

    job_ids = fields.Many2many('migration.job', 'migration_plan_run_job_rel', 'run_id', 'job_id', string='Executed Jobs')
    
    total_jobs = fields.Integer(string='Total Jobs', compute='_compute_job_metrics')
    total_records = fields.Integer(string='Total Records', compute='_compute_job_metrics')
    success_records = fields.Integer(string='Success Records', compute='_compute_job_metrics')
    error_records = fields.Integer(string='Error Records', compute='_compute_job_metrics')
    summary = fields.Text(string='Execution Summary', readonly=True)

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for run in self:
            if run.start_time and run.end_time:
                run.duration_seconds = round((run.end_time - run.start_time).total_seconds(), 2)
            else:
                run.duration_seconds = 0.0

    @api.depends('job_ids.total_records', 'job_ids.success_records', 'job_ids.error_records')
    def _compute_job_metrics(self):
        for run in self:
            jobs = run.job_ids
            run.total_jobs = len(jobs)
            run.total_records = sum(jobs.mapped('total_records'))
            run.success_records = sum(jobs.mapped('success_records'))
            run.error_records = sum(jobs.mapped('error_records'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('migration.plan.run') or _('RUN-%s') % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        return super().create(vals_list)

    def action_view_jobs(self):
        """View individual jobs executed during this run."""
        self.ensure_one()
        return {
            'name': _('Executed Jobs (%s)') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'migration.job',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.job_ids.ids)],
        }

    def action_view_logs(self):
        """View all audit logs recorded during this plan run."""
        self.ensure_one()
        return {
            'name': _('Audit Logs (%s)') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'migration.log',
            'view_mode': 'list,form',
            'domain': [('job_id', 'in', self.job_ids.ids)],
        }
