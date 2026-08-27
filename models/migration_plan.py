# -*- coding: utf-8 -*-

import logging
import time
import traceback
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MigrationPlan(models.Model):
    _name = 'migration.plan'
    _description = 'Multi-Stage Data Migration Plan'
    _order = 'sequence asc, id desc'

    name = fields.Char(string='Plan Name', required=True)
    code = fields.Char(string='Reference Code', required=True, default=lambda self: _('New'), copy=False, readonly=True)
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Html(string='Description & Objectives')
    active = fields.Boolean(string='Active', default=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'In Progress'),
        ('paused', 'Paused'),
        ('done', 'Completed'),
        ('done_with_errors', 'Completed with Errors'),
        ('failed', 'Failed'),
    ], string='Status', default='draft', readonly=True, index=True, copy=False)

    default_error_policy = fields.Selection([
        ('abort_plan', 'Abort Entire Plan'),
        ('abort_stage', 'Abort Current Stage & Continue'),
        ('continue_with_warning', 'Continue Step-by-Step with Warnings'),
    ], string='Default Error Policy', default='abort_stage', required=True,
       help='Action to take when a step or record encounters an unexpected error.')

    stage_ids = fields.One2many('migration.plan.stage', 'plan_id', string='Migration Stages', copy=True)
    run_ids = fields.One2many('migration.plan.run', 'plan_id', string='Execution Runs')

    stage_count = fields.Integer(string='Stages Count', compute='_compute_metrics')
    step_count = fields.Integer(string='Total Steps', compute='_compute_metrics')
    total_records = fields.Integer(string='Total Records', compute='_compute_metrics')
    processed_records = fields.Integer(string='Processed Records', compute='_compute_metrics')
    success_records = fields.Integer(string='Success Records', compute='_compute_metrics')
    error_records = fields.Integer(string='Failed Records', compute='_compute_metrics')
    progress_percent = fields.Float(string='Overall Progress (%)', compute='_compute_metrics')
    last_run_id = fields.Many2one('migration.plan.run', string='Last Run', compute='_compute_last_run', store=True)
    record_map_count = fields.Integer(string='Cross-Reference Records', compute='_compute_record_map_count')

    @api.depends('stage_ids.step_ids.total_records', 'stage_ids.step_ids.processed_records',
                 'stage_ids.step_ids.success_records', 'stage_ids.step_ids.error_records')
    def _compute_metrics(self):
        for plan in self:
            stages = plan.stage_ids
            steps = stages.mapped('step_ids')
            plan.stage_count = len(stages)
            plan.step_count = len(steps)
            total = sum(steps.mapped('total_records'))
            processed = sum(steps.mapped('processed_records'))
            success = sum(steps.mapped('success_records'))
            errors = sum(steps.mapped('error_records'))

            plan.total_records = total
            plan.processed_records = processed
            plan.success_records = success
            plan.error_records = errors
            plan.progress_percent = round((processed / total * 100.0), 2) if total > 0 else 0.0

    @api.depends('run_ids')
    def _compute_last_run(self):
        for plan in self:
            plan.last_run_id = plan.run_ids.sorted('id', reverse=True)[:1]

    def _compute_record_map_count(self):
        for plan in self:
            templates = plan.stage_ids.mapped('step_ids.template_id')
            if templates:
                plan.record_map_count = self.env['migration.record.map'].search_count([('template_id', 'in', templates.ids)])
            else:
                plan.record_map_count = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('migration.plan') or _('PLAN-%s') % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        return super().create(vals_list)

    # ------------------------------------------------------------
    # PRE-FLIGHT VALIDATION ENGINE
    # ------------------------------------------------------------

    def action_preflight_check(self):
        """Validates all connections, target models, templates, and mapping rules in the plan."""
        self.ensure_one()
        issues = []
        warnings = []
        valid_steps = 0

        if not self.stage_ids:
            issues.append(_("Plan has no stages defined."))

        for stage in self.stage_ids.sorted('sequence'):
            if not stage.step_ids:
                warnings.append(_("Stage '%s' contains no migration steps.") % stage.name)
                continue

            for step in stage.step_ids.sorted('sequence'):
                template = step.template_id
                if not template:
                    issues.append(_("Step '%s' in Stage '%s' is missing a migration template.") % (step.name, stage.name))
                    continue

                if not template.active:
                    warnings.append(_("Template '%s' in Step '%s' is archived/inactive.") % (template.name, step.name))

                # Check Connection
                conn = template.connection_id
                if not conn:
                    issues.append(_("Template '%s' has no connection configured.") % template.name)
                elif conn.state != 'connected':
                    warnings.append(_("Connection '%s' for template '%s' is not in Connected state.") % (conn.name, template.name))

                # Check Target Model
                if not template.target_model_id:
                    issues.append(_("Template '%s' has no target Odoo model configured.") % template.name)
                else:
                    model_name = template.target_model_name
                    if model_name not in self.env:
                        issues.append(_("Target model '%s' does not exist in this Odoo instance.") % model_name)

                # Check Mapping Lines
                if not template.mapping_line_ids:
                    issues.append(_("Template '%s' has no field mapping rules defined.") % template.name)
                else:
                    key_fields = template.mapping_line_ids.filtered(lambda l: l.is_key_field)
                    if not key_fields and template.operation_mode in ('upsert', 'update_only'):
                        warnings.append(_("Template '%s' uses '%s' mode but has no key match fields defined.") % (template.name, template.operation_mode))

                valid_steps += 1

        title = _("Pre-Flight Check Passed") if not issues else _("Pre-Flight Issues Detected")
        msg_type = 'success' if not issues and not warnings else ('warning' if not issues else 'danger')
        
        details = []
        if issues:
            details.append("❌ Issues:\n" + "\n".join(f"• {i}" for i in issues))
        if warnings:
            details.append("⚠️ Warnings:\n" + "\n".join(f"• {w}" for w in warnings))
        if not issues and not warnings:
            details.append(_("All %d step(s) across %d stage(s) are valid and ready for execution.") % (valid_steps, len(self.stage_ids)))

        message = "\n\n".join(details)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': msg_type,
                'sticky': bool(issues or warnings),
            }
        }

    # ------------------------------------------------------------
    # EXECUTION ENGINE & RUN WIZARD
    # ------------------------------------------------------------

    def action_open_run_wizard(self):
        """Open the multi-stage plan execution wizard modal."""
        self.ensure_one()
        return {
            'name': _('Execute Migration Plan: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'migration.plan.run.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_plan_id': self.id,
                'default_mode': 'full_plan',
            }
        }

    def execute_plan(self, dry_run=False, stage_id=False, step_id=False, limit=0, error_policy_override=False):
        """Main orchestrator for running multi-stage plans with savepoints and error isolation."""
        self.ensure_one()
        start_ts = time.time()

        run_vals = {
            'plan_id': self.id,
            'dry_run': dry_run,
            'state': 'running',
            'start_time': fields.Datetime.now(),
        }
        run = self.env['migration.plan.run'].create(run_vals)

        self.write({'state': 'running'})

        stages_to_run = self.stage_ids.sorted('sequence')
        if stage_id:
            stages_to_run = stages_to_run.filtered(lambda s: s.id == stage_id)

        plan_aborted = False
        total_steps_executed = 0
        total_errors = 0
        total_success = 0
        job_ids = []

        try:
            for stage in stages_to_run:
                if plan_aborted:
                    break

                stage.write({'state': 'running'})
                steps_to_run = stage.step_ids.sorted('sequence')
                if step_id:
                    steps_to_run = steps_to_run.filtered(lambda st: st.id == step_id)

                stage_error_count = 0
                stage_success_count = 0

                for step in steps_to_run:
                    if plan_aborted:
                        step.write({'state': 'skipped'})
                        continue

                    step.write({'state': 'running'})
                    policy = error_policy_override or step.error_policy or stage.error_policy or self.default_error_policy
                    effective_limit = limit or step.sample_limit or 0

                    step_job = False
                    try:
                        # Savepoint per step execution to guarantee atomicity or simulation rollback
                        with self.env.cr.savepoint():
                            step_job = step._execute_step(run=run, dry_run=dry_run, limit=effective_limit)
                            if step_job:
                                job_ids.append(step_job.id)

                            if dry_run:
                                # In simulation mode, rollback database changes made in savepoint
                                raise UserError("__DRY_RUN_SIMULATION_ROLLBACK__")

                    except UserError as ue:
                        if str(ue) == "__DRY_RUN_SIMULATION_ROLLBACK__":
                            _logger.info("Dry run simulation completed for step %s. Database state rolled back.", step.name)
                        else:
                            stage_error_count += 1
                            total_errors += 1
                            step.write({'state': 'failed'})
                            _logger.error("Error executing step %s: %s", step.name, ue)
                            if policy == 'abort_plan':
                                plan_aborted = True
                                break
                            elif policy == 'abort_stage':
                                break
                    except Exception as ex:
                        stage_error_count += 1
                        total_errors += 1
                        step.write({'state': 'failed'})
                        _logger.error("Unexpected error on step %s: %s\n%s", step.name, ex, traceback.format_exc())
                        if policy == 'abort_plan':
                            plan_aborted = True
                            break
                        elif policy == 'abort_stage':
                            break

                    if step_job:
                        total_success += step_job.success_records
                        total_errors += step_job.error_records
                        if step_job.state in ('done', 'draft') and step_job.error_records == 0:
                            step.write({'state': 'done'})
                        elif step_job.state == 'done_with_errors' or step_job.error_records > 0:
                            step.write({'state': 'done_with_errors'})
                        else:
                            step.write({'state': 'failed'})

                    total_steps_executed += 1

                # Update Stage Final State
                if stage_error_count > 0:
                    stage.write({'state': 'done_with_errors' if stage_success_count > 0 else 'failed'})
                else:
                    stage.write({'state': 'done'})

        except Exception as e:
            _logger.error("Fatal failure in migration plan execution: %s", e)
            plan_aborted = True
            total_errors += 1

        end_dt = fields.Datetime.now()
        duration = round(time.time() - start_ts, 2)

        if plan_aborted:
            final_plan_state = 'failed'
        elif total_errors > 0:
            final_plan_state = 'done_with_errors'
        else:
            final_plan_state = 'done'

        self.write({'state': final_plan_state})
        
        run.write({
            'state': final_plan_state,
            'end_time': end_dt,
            'job_ids': [(6, 0, job_ids)],
            'summary': _("Plan executed in %s s. Steps: %d, Success: %d, Errors: %d. Mode: %s") % (
                duration, total_steps_executed, total_success, total_errors, _('Dry-Run Simulation') if dry_run else _('Live Execution')
            ),
        })

        return run

    def action_pause_plan(self):
        """Pause currently running plan."""
        self.write({'state': 'paused'})

    def action_resume_plan(self):
        """Resume plan execution."""
        return self.action_open_run_wizard()

    def action_reset_draft(self):
        """Reset plan, stages, and steps back to draft state."""
        self.write({'state': 'draft'})
        for stage in self.stage_ids:
            stage.write({'state': 'draft'})
            for step in stage.step_ids:
                step.write({
                    'state': 'draft',
                    'total_records': 0,
                    'processed_records': 0,
                    'success_records': 0,
                    'error_records': 0,
                })

    def action_view_runs(self):
        """View execution runs for this plan."""
        self.ensure_one()
        return {
            'name': _('Execution Runs: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'migration.plan.run',
            'view_mode': 'list,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }

    def action_view_record_maps(self):
        """View record maps created by templates under this plan."""
        self.ensure_one()
        template_ids = self.stage_ids.mapped('step_ids.template_id').ids
        return {
            'name': _('Cross-Reference Maps: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'migration.record.map',
            'view_mode': 'list,form',
            'domain': [('template_id', 'in', template_ids)],
        }

    def action_open_console(self):
        """Open the interactive OWL 3 Live Execution Console."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'action_migration_plan_console',
            'target': 'main',
            'params': {
                'plan_id': self.id,
                'plan_name': self.name,
            },
        }
