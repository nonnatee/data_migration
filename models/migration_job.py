# -*- coding: utf-8 -*-

import hashlib
import json
import logging
import time
import traceback

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MigrationJob(models.Model):
    _name = 'migration.job'
    _description = 'Migration Job Run'
    _order = 'start_time desc, id desc'

    name = fields.Char(string='Job Reference', required=True, default=lambda self: _('New'))
    template_id = fields.Many2one('migration.template', string='Mapping Template', required=True, ondelete='cascade')
    connection_id = fields.Many2one(related='template_id.connection_id', string='Connection', store=True, readonly=True)
    target_model_name = fields.Char(related='template_id.target_model_name', store=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('done', 'Completed'),
        ('done_with_errors', 'Completed with Errors'),
        ('failed', 'Failed'),
    ], string='Status', default='draft', readonly=True, index=True)

    start_time = fields.Datetime(string='Start Time', readonly=True)
    end_time = fields.Datetime(string='End Time', readonly=True)
    duration_seconds = fields.Float(string='Duration (Sec)', compute='_compute_duration', store=True)
    records_per_sec = fields.Float(string='Throughput (Rec/Sec)', compute='_compute_duration', store=True)

    total_records = fields.Integer(string='Total Source Records', readonly=True)
    processed_records = fields.Integer(string='Processed Records', readonly=True)
    success_records = fields.Integer(string='Successfully Migrated', readonly=True)
    error_records = fields.Integer(string='Failed / Rejected Records', readonly=True)
    skipped_records = fields.Integer(string='Skipped Records', readonly=True)
    progress_percent = fields.Float(string='Progress (%)', compute='_compute_progress', store=True)

    log_ids = fields.One2many('migration.log', 'job_id', string='Execution Logs')
    summary_message = fields.Text(string='Execution Summary', readonly=True)

    @api.depends('start_time', 'end_time', 'processed_records')
    def _compute_duration(self):
        for job in self:
            if job.start_time and job.end_time:
                dur = (job.end_time - job.start_time).total_seconds()
                job.duration_seconds = round(dur, 2)
                job.records_per_sec = round(job.processed_records / dur, 2) if dur > 0 else 0.0
            else:
                job.duration_seconds = 0.0
                job.records_per_sec = 0.0

    @api.depends('total_records', 'processed_records')
    def _compute_progress(self):
        for job in self:
            if job.total_records > 0:
                job.progress_percent = round((job.processed_records / job.total_records) * 100.0, 2)
            else:
                job.progress_percent = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('migration.job') or _('JOB-%s') % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        return super().create(vals_list)

    # ------------------------------------------------------------
    # 6-STAGE ETL EXECUTION ENGINE WITH SPLIT TRANSFORM & MAPPING
    # ------------------------------------------------------------

    def action_run_migration(self):
        """Execute ETL migration job."""
        for job in self:
            job._execute_job()
        return True

    def _execute_job(self, limit=0, stage_name=False, step_name=False):
        self.ensure_one()
        start_ts = time.time()
        self.write({
            'state': 'in_progress',
            'start_time': fields.Datetime.now(),
            'end_time': False,
            'summary_message': False,
        })

        template = self.template_id
        target_model = template.target_model_name
        op_mode = template.operation_mode
        mapping_lines = template.mapping_line_ids
        validation_rules = template.validation_rule_ids.filtered(lambda r: r.active)
        pre_load_rules = validation_rules.filtered(lambda r: r.rule_timing == 'pre_load')
        post_load_rules = validation_rules.filtered(lambda r: r.rule_timing == 'post_load')
        key_lines = mapping_lines.filtered(lambda l: l.is_key_field)

        if not mapping_lines:
            raise UserError(_("Mapping template '%s' has no target field mappings configured.") % template.name)

        if target_model not in self.env:
            raise UserError(_("Target model '%s' does not exist in this Odoo system.") % target_model)

        # STAGE 2: EXTRACTION
        try:
            if template.extraction_id:
                records, columns = template.extraction_id.execute_extraction(limit=limit or None)
            else:
                records, columns = self.connection_id._fetch_raw_records(limit=limit or None)
        except Exception as e:
            self.write({
                'state': 'failed',
                'end_time': fields.Datetime.now(),
                'summary_message': _("Failed during Data Extraction stage: %s") % str(e),
            })
            self.env['migration.log'].create({
                'job_id': self.id,
                'stage_name': stage_name or 'Extraction',
                'step_name': step_name or self.name,
                'log_type': 'error',
                'message': _("Data Extraction Error: %s") % str(e),
                'error_traceback': traceback.format_exc(),
            })
            return

        total_count = len(records)
        self.write({'total_records': total_count})

        processed = 0
        success_cnt = 0
        error_cnt = 0
        skipped_cnt = 0

        # Context optimization bypasses
        ctx = dict(self.env.context)
        if template.bypass_tracking:
            ctx.update({'tracking_disable': True, 'mail_auto_subscribe_no_notify': True})
        if template.bypass_subscription:
            ctx.update({'mail_create_nosubscribe': True, 'mail_create_nolog': True})
        ctx.update({'defer_parent_store_computation': True, 'no_reset_password': True})

        target_obj = self.env[target_model].with_context(ctx)

        # STAGES 3, 4, 5: TRANSFORMATION -> VALIDATION -> MAPPING & LOADING
        for idx, row in enumerate(records):
            row_index = idx + 1
            source_key = self._extract_source_key(row, key_lines, row_index)
            row_checksum = hashlib.md5(json.dumps(row, sort_keys=True, default=str).encode('utf-8')).hexdigest()

            # Savepoint per record to isolate failures completely
            try:
                with self.env.cr.savepoint():
                    # 1. STAGE 3: DATA TRANSFORMATION (In-place cleansing & derived variables)
                    clean_row = template._apply_transformation_stage(row)

                    # 2. STAGE 4: VALIDATION (Evaluated on clean/derived record)
                    val_passed, val_err_msg, val_action = self._validate_rules(pre_load_rules, clean_row, row)
                    if not val_passed:
                        if val_action == 'warning':
                            self.env['migration.log'].create({
                                'job_id': self.id,
                                'stage_name': stage_name or 'Validation',
                                'step_name': step_name or self.name,
                                'row_number': row_index,
                                'source_key': source_key,
                                'log_type': 'warning',
                                'message': _("Pre-Load Validation Warning: %s") % val_err_msg,
                                'raw_data': json.dumps(row, default=str),
                                'transformed_data': json.dumps(clean_row, default=str),
                            })
                        elif val_action == 'reject_record':
                            error_cnt += 1
                            processed += 1
                            self.env['migration.log'].create({
                                'job_id': self.id,
                                'stage_name': stage_name or 'Validation',
                                'step_name': step_name or self.name,
                                'row_number': row_index,
                                'source_key': source_key,
                                'log_type': 'error',
                                'message': _("Pre-Load Validation Rejected Record: %s") % val_err_msg,
                                'raw_data': json.dumps(row, default=str),
                                'transformed_data': json.dumps(clean_row, default=str),
                            })
                            continue
                        elif val_action == 'abort_stage':
                            raise UserError(_("Validation Abort Triggered: %s") % val_err_msg)

                    # 3. STAGE 5: TARGET FIELD MAPPING & LOADING
                    target_vals = template._apply_mapping_stage(clean_row)

                    res_status, target_id, log_msg = self._load_single_record(
                        target_obj, template, mapping_lines, key_lines, target_vals, source_key, row_checksum, op_mode
                    )

                    # 4. Post-Load Verification
                    if target_id and post_load_rules:
                        target_rec = target_obj.browse(target_id)
                        post_passed, post_err_msg, post_action = self._validate_rules(
                            post_load_rules, target_rec.read()[0] if target_rec.exists() else {}, row
                        )
                        if not post_passed:
                            self.env['migration.log'].create({
                                'job_id': self.id,
                                'stage_name': stage_name or 'Verification',
                                'step_name': step_name or self.name,
                                'row_number': row_index,
                                'source_key': source_key,
                                'log_type': 'warning' if post_action == 'warning' else 'error',
                                'message': _("Post-Load Verification Issue: %s") % post_err_msg,
                                'target_record_id': target_id,
                            })

                    if res_status in ('created', 'updated'):
                        success_cnt += 1
                        self.env['migration.log'].create({
                            'job_id': self.id,
                            'stage_name': stage_name or 'Loading',
                            'step_name': step_name or self.name,
                            'row_number': row_index,
                            'source_key': source_key,
                            'log_type': 'success',
                            'message': log_msg,
                            'target_record_id': target_id,
                            'transformed_data': json.dumps(target_vals, default=str),
                        })
                    elif res_status == 'skipped':
                        skipped_cnt += 1
                        self.env['migration.log'].create({
                            'job_id': self.id,
                            'stage_name': stage_name or 'Loading',
                            'step_name': step_name or self.name,
                            'row_number': row_index,
                            'source_key': source_key,
                            'log_type': 'info',
                            'message': log_msg,
                            'target_record_id': target_id,
                        })

            except UserError as ue:
                err_str = str(ue)
                if err_str in ('__DROP_ROW_NULL__', '__DROP_ROW_FILTER__') or err_str.startswith('__DROP_ROW'):
                    skipped_cnt += 1
                    self.env['migration.log'].create({
                        'job_id': self.id,
                        'stage_name': stage_name or 'Transformation',
                        'step_name': step_name or self.name,
                        'row_number': row_index,
                        'source_key': source_key,
                        'log_type': 'info',
                        'message': _("Record skipped by transformation filter rule (%s).") % (
                            "Null Check" if "NULL" in err_str else "Condition Filter"
                        ),
                        'raw_data': json.dumps(row, default=str),
                    })
                else:
                    error_cnt += 1
                    _logger.warning("User error migrating row %s (key=%s): %s", row_index, source_key, ue)
                    self.env['migration.log'].create({
                        'job_id': self.id,
                        'stage_name': stage_name or 'Loading',
                        'step_name': step_name or self.name,
                        'row_number': row_index,
                        'source_key': source_key,
                        'log_type': 'error',
                        'message': str(ue),
                        'error_traceback': traceback.format_exc(),
                        'raw_data': json.dumps(row, default=str),
                    })
            except Exception as err:
                error_cnt += 1
                error_trace = traceback.format_exc()
                _logger.warning("Error migrating row %s (key=%s): %s", row_index, source_key, err)
                self.env['migration.log'].create({
                    'job_id': self.id,
                    'stage_name': stage_name or 'Loading',
                    'step_name': step_name or self.name,
                    'row_number': row_index,
                    'source_key': source_key,
                    'log_type': 'error',
                    'message': _("Row error: %s") % str(err),
                    'error_traceback': error_trace,
                    'raw_data': json.dumps(row, default=str),
                })

            processed += 1
            if processed % 100 == 0 or processed == total_count:
                self.write({
                    'processed_records': processed,
                    'success_records': success_cnt,
                    'error_records': error_cnt,
                    'skipped_records': skipped_cnt,
                })
                self.env.cr.commit()

        # STAGE 6: FINAL STATUS & METRICS
        final_state = 'done' if error_cnt == 0 else ('done_with_errors' if success_cnt > 0 else 'failed')
        end_dt = fields.Datetime.now()
        exec_duration = round(time.time() - start_ts, 2)
        summary = _("Completed ETL run in %s seconds. Total: %d, Success: %d, Errors: %d, Skipped: %d.") % (
            exec_duration, total_count, success_cnt, error_cnt, skipped_cnt
        )

        self.write({
            'state': final_state,
            'end_time': end_dt,
            'processed_records': processed,
            'success_records': success_cnt,
            'error_records': error_cnt,
            'skipped_records': skipped_cnt,
            'summary_message': summary,
        })

    def _extract_source_key(self, row, key_lines, row_index):
        if key_lines:
            key_vals = [str(row.get(l.source_field, '')).strip() for l in key_lines if row.get(l.source_field) is not None]
            if key_vals:
                return '-'.join(key_vals)
        for cand in ('id', 'code', 'ref', 'default_code', 'email'):
            if cand in row and str(row[cand]).strip():
                return str(row[cand]).strip()
        return f"ROW-{row_index}"

    def _validate_rules(self, rules, clean_record, raw_record):
        """Evaluates list of validation rules against clean_record and raw_record."""
        for rule in rules:
            target_f = rule.target_field_name or rule.source_field
            val = clean_record.get(target_f, clean_record.get(rule.source_field, raw_record.get(rule.source_field)))
            is_valid, err_msg = rule.evaluate_rule(val, clean_record)
            if not is_valid:
                return False, err_msg, rule.action_on_failure
        return True, False, 'none'

    def _load_single_record(self, target_obj, template, mapping_lines, key_lines, vals, source_key, row_checksum, op_mode):
        """Executes create/update/upsert or skip based on operation mode."""
        rec_map_obj = self.env['migration.record.map']
        existing_map = rec_map_obj.search([
            ('template_id', '=', template.id),
            ('source_key', '=', source_key)
        ], limit=1)

        existing_record = False
        if existing_map and existing_map.target_id:
            existing_record = target_obj.browse(existing_map.target_id).exists()

        if not existing_record and key_lines:
            domain = []
            for kl in key_lines:
                k_val = vals.get(kl.target_field_name)
                if k_val:
                    domain.append((kl.target_field_name, '=', k_val))
            if domain:
                existing_record = target_obj.search(domain, limit=1)

        if existing_record:
            if op_mode == 'create_only':
                return 'skipped', existing_record.id, _("Record exists (ID %s), skipped due to Create Only mode.") % existing_record.id
            elif op_mode == 'skip_existing':
                return 'skipped', existing_record.id, _("Skipped existing record (ID %s).") % existing_record.id

            # Check if checksum unchanged for incremental update
            if existing_map and existing_map.checksum == row_checksum:
                return 'skipped', existing_record.id, _("Skipped record (ID %s): Data checksum unchanged.") % existing_record.id

            existing_record.write(vals)
            target_id = existing_record.id

            if existing_map:
                existing_map.write({'checksum': row_checksum, 'last_migrated': fields.Datetime.now()})
            else:
                self._create_record_map(template, source_key, target_id, row_checksum)

            return 'updated', target_id, _("Updated existing record (ID %s).") % target_id

        else:
            if op_mode == 'update_only':
                return 'skipped', False, _("No matching record found for key '%s', skipped due to Update Only mode.") % source_key

            new_rec = target_obj.create(vals)
            target_id = new_rec.id

            xml_id = f"migrated_{template.target_model_name.replace('.', '_')}_{source_key.replace(' ', '_').replace('/', '_')}"
            self._create_xml_id(template.target_model_name, target_id, xml_id)
            self._create_record_map(template, source_key, target_id, row_checksum, xml_id)

            return 'created', target_id, _("Created new record (ID %s, XML ID %s).") % (target_id, xml_id)

    def _create_record_map(self, template, source_key, target_id, checksum, xml_id=False):
        self.env['migration.record.map'].create({
            'template_id': template.id,
            'source_key': source_key,
            'target_model': template.target_model_name,
            'target_id': target_id,
            'xml_id': xml_id,
            'checksum': checksum,
            'last_migrated': fields.Datetime.now(),
        })

    def _create_xml_id(self, model_name, target_id, xml_id):
        module = 'data_migration'
        self.env['ir.model.data'].create({
            'module': module,
            'name': xml_id,
            'model': model_name,
            'res_id': target_id,
            'noupdate': True,
        })
