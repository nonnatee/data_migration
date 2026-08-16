# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MigrationPlanRunWizard(models.TransientModel):
    _name = 'migration.plan.run.wizard'
    _description = 'Multi-Stage Migration Plan Execution Wizard'

    plan_id = fields.Many2one('migration.plan', string='Migration Plan', required=True, ondelete='cascade')
    mode = fields.Selection([
        ('full_plan', 'Execute Full Plan (All Stages)'),
        ('single_stage', 'Execute Single Stage Only'),
        ('from_failed_step', 'Resume / Execute Specific Step Only'),
    ], string='Execution Mode', default='full_plan', required=True)

    stage_id = fields.Many2one('migration.plan.stage', string='Select Stage', domain="[('plan_id', '=', plan_id)]")
    step_id = fields.Many2one('migration.plan.step', string='Select Step', domain="[('plan_id', '=', plan_id)]")

    dry_run = fields.Boolean(
        string='Dry-Run Simulation Mode (No DB Writes)',
        default=False,
        help='Runs complete data extraction, cleansing pipelines, and relational lookups in a rolled-back transaction to identify mapping errors without modifying your database.'
    )
    sample_limit = fields.Integer(
        string='Sample Record Limit (0 = All)',
        default=0,
        help='Cap number of source rows processed per step for rapid test verification.'
    )
    error_policy_override = fields.Selection([
        ('abort_plan', 'Abort Entire Plan on Error'),
        ('abort_stage', 'Abort Current Stage & Continue'),
        ('continue_with_warning', 'Continue Step-by-Step with Warnings'),
    ], string='Error Policy Override', help='Leave empty to use configured stage/step defaults.')

    @api.onchange('mode')
    def _onchange_mode(self):
        if self.mode == 'full_plan':
            self.stage_id = False
            self.step_id = False
        elif self.mode == 'single_stage' and not self.stage_id:
            first_stage = self.plan_id.stage_ids.sorted('sequence')[:1]
            if first_stage:
                self.stage_id = first_stage.id
        elif self.mode == 'from_failed_step' and not self.step_id:
            failed_step = self.plan_id.stage_ids.mapped('step_ids').filtered(lambda s: s.state in ('failed', 'done_with_errors'))[:1]
            if failed_step:
                self.step_id = failed_step.id

    def action_start_execution(self):
        """Launches multi-stage plan execution and displays the run results."""
        self.ensure_one()
        plan = self.plan_id
        if not plan:
            raise UserError(_("No migration plan selected."))

        stage_id = self.stage_id.id if self.mode == 'single_stage' else False
        step_id = self.step_id.id if self.mode == 'from_failed_step' else False

        if self.mode == 'single_stage' and not stage_id:
            raise UserError(_("Please select a stage to execute."))
        if self.mode == 'from_failed_step' and not step_id:
            raise UserError(_("Please select a step to execute."))

        run = plan.execute_plan(
            dry_run=self.dry_run,
            stage_id=stage_id,
            step_id=step_id,
            limit=self.sample_limit,
            error_policy_override=self.error_policy_override,
        )

        return {
            'name': _('Plan Execution Run: %s') % run.name,
            'type': 'ir.actions.act_window',
            'res_model': 'migration.plan.run',
            'res_id': run.id,
            'view_mode': 'form',
            'target': 'current',
        }
