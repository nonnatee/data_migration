# -*- coding: utf-8 -*-

import json
import logging
import time
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MigrationExtraction(models.Model):
    _name = 'migration.extraction'
    _description = 'Data Extraction Query & Watermark Configuration'
    _order = 'name asc'

    name = fields.Char(string='Extraction Name', required=True)
    connection_id = fields.Many2one('migration.connection', string='Data Connection', required=True, ondelete='cascade')
    conn_type = fields.Selection(related='connection_id.conn_type', readonly=True)

    extraction_type = fields.Selection([
        ('full', 'Full Extraction (All Records)'),
        ('incremental_watermark', 'Incremental Extraction (Watermark / Delta)'),
        ('custom_query', 'Custom Filtered SQL / API Query'),
    ], string='Extraction Strategy', default='full', required=True)

    # Incremental Watermark Settings
    watermark_column = fields.Char(
        string='Watermark Source Column',
        placeholder='updated_at or write_date or id',
        help='Source field checked to extract only new/updated rows.'
    )
    last_watermark_value = fields.Char(string='Last Watermark Value', copy=False, help='Persisted state of the highest watermark value from last extraction run.')
    watermark_datatype = fields.Selection([
        ('datetime', 'Datetime / Timestamp (ISO 8601)'),
        ('date', 'Date (YYYY-MM-DD)'),
        ('integer', 'Integer (Auto-increment ID)'),
    ], string='Watermark Data Type', default='datetime')

    # Custom Query Override
    custom_query = fields.Text(
        string='Custom SQL / API Query',
        help='Custom SQL query or API request body. Use :watermark parameter if incremental extraction is enabled.'
    )
    chunk_size = fields.Integer(string='Extraction Batch Chunk Size', default=1000, help='Stream records in chunks of N.')
    max_records_limit = fields.Integer(string='Safety Max Records Limit', default=0, help='0 for unlimited; positive number to restrict maximum records extracted per run.')

    # Metadata & Statistics
    last_run_time = fields.Datetime(string='Last Extracted On', readonly=True)
    last_extracted_count = fields.Integer(string='Last Records Count', readonly=True)
    preview_data = fields.Text(string='Extraction Preview (JSON)', readonly=True)

    def action_test_extraction(self):
        """Tests the extraction query and populates preview data."""
        self.ensure_one()
        try:
            records, columns = self.execute_extraction(limit=10, update_watermark=False)
            self.write({
                'preview_data': json.dumps(records[:10], default=str),
                'last_extracted_count': len(records),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Extraction Successful'),
                    'message': _('Extracted %d sample records across %d columns.', len(records), len(columns)),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.exception("Extraction test failed for ID %s", self.id)
            raise UserError(_("Extraction test failed: %s") % str(e))

    def execute_extraction(self, limit=None, update_watermark=True):
        """Executes data extraction based on strategy and updates watermark state."""
        self.ensure_one()
        conn = self.connection_id
        effective_limit = limit or self.max_records_limit or None

        # Build effective query with watermark if incremental
        original_query = conn.db_query
        if self.extraction_type == 'incremental_watermark' and self.watermark_column:
            last_wm = self.last_watermark_value or '1970-01-01 00:00:00'
            if conn.conn_type == 'database_sql':
                base_q = self.custom_query or conn.db_query or "SELECT * FROM source_table"
                if 'WHERE' in base_q.upper():
                    conn.db_query = f"{base_q} AND {self.watermark_column} > '{last_wm}' ORDER BY {self.watermark_column} ASC"
                else:
                    conn.db_query = f"{base_q} WHERE {self.watermark_column} > '{last_wm}' ORDER BY {self.watermark_column} ASC"

        elif self.extraction_type == 'custom_query' and self.custom_query:
            if conn.conn_type == 'database_sql':
                conn.db_query = self.custom_query

        try:
            records, columns = conn._fetch_raw_records(limit=effective_limit)
        finally:
            # Restore connection query
            if conn.conn_type == 'database_sql':
                conn.db_query = original_query

        # In-memory filter for file/API incremental extraction if needed
        if self.extraction_type == 'incremental_watermark' and self.watermark_column and conn.conn_type != 'database_sql':
            last_wm = self.last_watermark_value
            if last_wm:
                records = [r for r in records if str(r.get(self.watermark_column, '')) > last_wm]

        # Update watermark from extracted batch
        if update_watermark and records and self.watermark_column:
            wm_values = [str(r.get(self.watermark_column, '')) for r in records if r.get(self.watermark_column) is not None]
            if wm_values:
                highest_wm = max(wm_values)
                self.write({
                    'last_watermark_value': highest_wm,
                    'last_run_time': fields.Datetime.now(),
                    'last_extracted_count': len(records),
                })
        elif update_watermark:
            self.write({
                'last_run_time': fields.Datetime.now(),
                'last_extracted_count': len(records),
            })

        return records, columns

    def action_reset_watermark(self):
        """Resets the stored watermark to start full extraction on next run."""
        self.ensure_one()
        self.write({'last_watermark_value': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Watermark Reset'),
                'message': _('Incremental watermark has been reset. Next run will extract all records.'),
                'type': 'info',
            }
        }
