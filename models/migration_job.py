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

    total_records = fields.Integer(string='Total Source Records', readonly=True)
    processed_records = fields.Integer(string='Processed Records', readonly=True)
    success_records = fields.Integer(string='Successfully Migrated', readonly=True)
    error_records = fields.Integer(string='Failed Records', readonly=True)
    progress_percent = fields.Float(string='Progress (%)', compute='_compute_progress', store=True)

    log_ids = fields.One2many('migration.log', 'job_id', string='Execution Logs')
    summary_message = fields.Text(string='Execution Summary', readonly=True)

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for job in self:
            if job.start_time and job.end_time:
                job.duration_seconds = (job.end_time - job.start_time).total_seconds()
            else:
                job.duration_seconds = 0.0

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
    # ETL EXECUTION ENGINE WITH SAVEPOINT ERROR ISOLATION
    # ------------------------------------------------------------

    def action_run_migration(self):
        """Execute ETL migration job."""
        for job in self:
            job._execute_job()
        return True

    def _execute_job(self):
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
        key_lines = mapping_lines.filtered(lambda l: l.is_key_field)

        if not mapping_lines:
            raise UserError(_("Mapping template has no field mapping rules defined."))

        # Step 1: Fetch source data rows
        try:
            records, columns = self.connection_id._fetch_raw_records()
        except Exception as e:
            self.write({
                'state': 'failed',
                'end_time': fields.Datetime.now(),
                'summary_message': _("Failed to fetch source records: %s") % str(e),
            })
            self.env['migration.log'].create({
                'job_id': self.id,
                'log_type': 'error',
                'message': _("Fetch error: %s") % str(e),
                'error_traceback': traceback.format_exc(),
            })
            return

        total_count = len(records)
        self.write({'total_records': total_count})

        processed = 0
        success_cnt = 0
        error_cnt = 0

        target_obj = self.env[target_model]

        # Step 2: Loop rows with savepoint protection
        for idx, row in enumerate(records):
            row_index = idx + 1
            source_key = self._extract_source_key(row, key_lines, row_index)
            row_checksum = hashlib.md5(json.dumps(row, sort_keys=True, default=str).encode('utf-8')).hexdigest()

            # Savepoint per record to isolate failures
            try:
                with self.env.cr.savepoint():
                    res_status, target_id, log_msg = self._process_single_record(
                        target_obj, template, mapping_lines, key_lines, row, source_key, row_checksum, op_mode
                    )

                    if res_status in ('created', 'updated'):
                        success_cnt += 1
                        self.env['migration.log'].create({
                            'job_id': self.id,
                            'row_number': row_index,
                            'source_key': source_key,
                            'log_type': 'info',
                            'message': log_msg,
                            'target_record_id': target_id,
                        })
                    elif res_status == 'skipped':
                        success_cnt += 1
                        self.env['migration.log'].create({
                            'job_id': self.id,
                            'row_number': row_index,
                            'source_key': source_key,
                            'log_type': 'warning',
                            'message': log_msg,
                            'target_record_id': target_id,
                        })

            except Exception as err:
                error_cnt += 1
                error_trace = traceback.format_exc()
                _logger.warning("Error migrating row %s (key=%s): %s", row_index, source_key, err)
                self.env['migration.log'].create({
                    'job_id': self.id,
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
                })
                self.env.cr.commit()

        # Step 3: Finalize status
        final_state = 'done' if error_cnt == 0 else ('done_with_errors' if success_cnt > 0 else 'failed')
        end_dt = fields.Datetime.now()
        exec_duration = round(time.time() - start_ts, 2)
        summary = _("Completed ETL run in %s seconds. Total: %s, Success: %s, Errors: %s.") % (
            exec_duration, total_count, success_cnt, error_cnt
        )

        self.write({
            'state': final_state,
            'end_time': end_dt,
            'processed_records': processed,
            'success_records': success_cnt,
            'error_records': error_cnt,
            'summary_message': summary,
        })

    def _extract_source_key(self, row, key_lines, row_index):
        """Constructs string source key from row data."""
        if key_lines:
            key_vals = [str(row.get(l.source_field, '')).strip() for l in key_lines]
            return '-'.join(key_vals)
        elif 'id' in row:
            return str(row['id'])
        elif 'code' in row:
            return str(row['code'])
        return f"ROW-{row_index}"

    def _process_single_record(self, target_obj, template, mapping_lines, key_lines, row, source_key, row_checksum, op_mode):
        """Builds field dictionary and executes create/update/upsert or skip."""
        vals = {}
        for line in mapping_lines:
            raw_val = row.get(line.source_field)
            converted_val = line.convert_value(raw_val, row)
            if converted_val is not False or line.target_field_ttype == 'boolean':
                vals[line.target_field_name] = converted_val

        # Find existing target record using migration.record.map or key fields
        rec_map_obj = self.env['migration.record.map']
        existing_map = rec_map_obj.search([
            ('template_id', '=', template.id),
            ('source_key', '=', source_key)
        ], limit=1)

        existing_record = False
        if existing_map:
            existing_record = target_obj.browse(existing_map.target_id).exists()

        if not existing_record and key_lines:
            domain = []
            for kl in key_lines:
                k_val = vals.get(kl.target_field_name)
                if k_val:
                    domain.append((kl.target_field_name, '=', k_val))
            if domain:
                existing_record = target_obj.search(domain, limit=1)

        # Handle Operation Modes
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

            # Update or create record map
            if existing_map:
                existing_map.write({'checksum': row_checksum, 'last_migrated': fields.Datetime.now()})
            else:
                self._create_record_map(template, source_key, target_id, row_checksum)

            return 'updated', target_id, _("Updated existing record (ID %s).") % target_id

        else:
            if op_mode == 'update_only':
                return 'skipped', False, _("No matching record found for key '%s', skipped due to Update Only mode.") % source_key

            # Create new Odoo record
            new_rec = target_obj.create(vals)
            target_id = new_rec.id

            # Create XML ID (ir.model.data) & migration map entry
            xml_id = f"migrated_{template.target_model_name.replace('.', '_')}_{source_key.replace(' ', '_')}"
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
