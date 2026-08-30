# -*- coding: utf-8 -*-

import json
import logging
import re
import time
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Dangerous SQL keywords forbidden in extraction queries
FORBIDDEN_SQL_PATTERNS = [
    r'\bDROP\b',
    r'\bDELETE\b',
    r'\bUPDATE\b',
    r'\bINSERT\b',
    r'\bTRUNCATE\b',
    r'\bALTER\b',
    r'\bCREATE\b',
    r'\bGRANT\b',
    r'\bREVOKE\b',
    r'\bEXEC\b',
    r'\bEXECUTE\b',
    r'\bSHUTDOWN\b',
]


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
    last_watermark_value = fields.Char(
        string='Last Watermark Value',
        copy=False,
        help='Persisted state of the highest watermark value from last extraction run.'
    )
    watermark_datatype = fields.Selection([
        ('datetime', 'Datetime / Timestamp (ISO 8601)'),
        ('date', 'Date (YYYY-MM-DD)'),
        ('integer', 'Integer (Auto-increment ID)'),
    ], string='Watermark Data Type', default='datetime')

    # Visual Query Builder State
    use_visual_builder = fields.Boolean(string='Use Visual Field Selector', default=True)
    selected_table = fields.Char(string='Selected Source Table/Entity', default='source_table')
    selected_fields_json = fields.Text(
        string='Visual Selected Fields (JSON)',
        default='[]',
        help='JSON array of field projection configs: [{"field": "id", "alias": "partner_id", "cast": "integer", "selected": true}]'
    )
    where_clauses_json = fields.Text(
        string='Visual WHERE Filters (JSON)',
        default='[]',
        help='JSON array of filter conditions: [{"field": "active", "operator": "=", "value": "1", "conjunction": "AND"}]'
    )
    sort_clauses_json = fields.Text(
        string='Visual Sorting Rules (JSON)',
        default='[]',
        help='JSON array of sort orders: [{"field": "id", "direction": "ASC"}]'
    )

    # Custom & Compiled Queries
    custom_query = fields.Text(
        string='Custom SQL / API Query',
        help='Custom SQL query or API request body. Use :watermark parameter if incremental extraction is enabled.'
    )
    compiled_query = fields.Text(
        string='Compiled Extraction Query',
        compute='_compute_compiled_query',
        store=True,
        help='Final executable SQL / API query compiled from visual builder settings or custom query.'
    )

    # Execution Limits & Batching
    chunk_size = fields.Integer(string='Extraction Batch Chunk Size', default=1000, help='Stream records in chunks of N.')
    max_records_limit = fields.Integer(
        string='Safety Max Records Limit',
        default=0,
        help='0 for unlimited; positive number to restrict maximum records extracted per run.'
    )

    # AI Insights & Advisory
    ai_optimization_notes = fields.Text(string='AI Optimization & Index Recommendations', readonly=True)
    ai_explanation = fields.Text(string='AI Query Explanation & Data Profile', readonly=True)

    # Metadata & Statistics
    last_run_time = fields.Datetime(string='Last Extracted On', readonly=True)
    last_extracted_count = fields.Integer(string='Last Records Count', readonly=True)
    latency_ms = fields.Float(string='Extraction Latency (ms)', readonly=True)
    preview_data = fields.Text(string='Extraction Preview (JSON)', readonly=True)

    # ------------------------------------------------------------
    # 1. QUERY COMPILATION & SAFETY VALIDATION
    # ------------------------------------------------------------

    def _validate_query_safety(self, query):
        """Ensures that SQL query does not contain destructive statements."""
        if not query:
            return
        # Normalize comments and check tokens
        cleaned = re.sub(r'--.*?$|/\*.*?\*/', '', query, flags=re.MULTILINE | re.DOTALL)
        for pattern in FORBIDDEN_SQL_PATTERNS:
            if re.search(pattern, cleaned, re.IGNORECASE):
                keyword = pattern.replace(r'\b', '')
                raise UserError(
                    _("Security Violation: Prohibited '%s' statement detected in extraction query. Only read-only queries (SELECT) are permitted.") % keyword
                )

    @api.depends('use_visual_builder', 'extraction_type', 'selected_table', 'selected_fields_json', 'where_clauses_json', 'sort_clauses_json', 'custom_query', 'watermark_column')
    def _compute_compiled_query(self):
        for rec in self:
            rec.compiled_query = rec.compile_query_from_visual()

    def compile_query_from_visual(self):
        """Compiles visual builder settings or custom query into an executable SQL / API query string."""
        self.ensure_one()
        conn_type = self.conn_type or 'database_sql'

        # If not using visual builder or strategy is custom_query, return custom_query or connection query
        if not self.use_visual_builder and self.extraction_type == 'custom_query':
            q = self.custom_query or (self.connection_id and self.connection_id.db_query) or "SELECT * FROM source_table"
            self._validate_query_safety(q)
            return q

        # Visual Builder SQL generation
        table_name = self.selected_table or 'source_table'
        selected_fields = json.loads(self.selected_fields_json or '[]')
        where_clauses = json.loads(self.where_clauses_json or '[]')
        sort_clauses = json.loads(self.sort_clauses_json or '[]')

        # 1. SELECT Projections
        projections = []
        active_fields = [f for f in selected_fields if f.get('selected', True)]
        if active_fields:
            for f in active_fields:
                col = f.get('field', '').strip()
                alias = f.get('alias', '').strip()
                cast_type = f.get('cast', '').strip()

                if not col:
                    continue

                expr = col
                if cast_type and cast_type not in ('none', 'default'):
                    expr = f"CAST({col} AS {cast_type})"

                if alias and alias != col:
                    projections.append(f"{expr} AS {alias}")
                else:
                    projections.append(expr)
        else:
            projections.append("*")

        select_clause = ", ".join(projections) if projections else "*"

        # 2. WHERE Conditions
        where_parts = []
        for idx, clause in enumerate(where_clauses):
            field = clause.get('field', '').strip()
            op = clause.get('operator', '=').strip().upper()
            val = clause.get('value', '').strip()
            conj = clause.get('conjunction', 'AND').strip().upper()

            if not field:
                continue

            if op in ('IS NULL', 'IS NOT NULL'):
                cond_str = f"{field} {op}"
            elif op == 'IN':
                cond_str = f"{field} IN ({val})"
            elif op == 'LIKE' or op == 'ILIKE':
                cond_str = f"{field} {op} '{val}'"
            elif val.lower() == ':watermark':
                cond_str = f"{field} > :watermark"
            elif val.replace('.', '', 1).isdigit() or val.lower() in ('true', 'false'):
                cond_str = f"{field} {op} {val}"
            else:
                cond_str = f"{field} {op} '{val}'"

            if idx > 0 and where_parts:
                where_parts.append(f"{conj} {cond_str}")
            else:
                where_parts.append(cond_str)

        # 3. ORDER BY Sorting
        order_parts = []
        for s in sort_clauses:
            sfield = s.get('field', '').strip()
            sdir = s.get('direction', 'ASC').strip().upper()
            if sfield:
                order_parts.append(f"{sfield} {sdir}")

        # Assemble Full SQL
        query_sql = f"SELECT {select_clause}\nFROM {table_name}"
        if where_parts:
            query_sql += f"\nWHERE {' '.join(where_parts)}"
        if order_parts:
            query_sql += f"\nORDER BY {', '.join(order_parts)}"

        self._validate_query_safety(query_sql)
        return query_sql

    def get_extraction_columns(self):
        """Returns the list of column names produced by this extraction query for downstream templates."""
        self.ensure_one()
        selected_fields = json.loads(self.selected_fields_json or '[]')
        active_fields = [f for f in selected_fields if f.get('selected', True)]
        if active_fields:
            cols = []
            for f in active_fields:
                alias = f.get('alias', '').strip()
                field = f.get('field', '').strip()
                cols.append(alias or field)
            return [c for c in cols if c]

        # Fallback to connection discovered columns
        if self.connection_id and self.connection_id.source_columns:
            return json.loads(self.connection_id.source_columns)
        return []

    # ------------------------------------------------------------
    # 2. EXECUTION & PREVIEW ENGINE
    # ------------------------------------------------------------

    def action_test_extraction(self):
        """Tests the extraction query and populates preview data."""
        self.ensure_one()
        start_ts = time.time()
        try:
            records, columns = self.execute_extraction(limit=10, update_watermark=False)
            duration_ms = round((time.time() - start_ts) * 1000.0, 2)
            self.write({
                'preview_data': json.dumps(records[:10], default=str),
                'last_extracted_count': len(records),
                'latency_ms': duration_ms,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Extraction Successful'),
                    'message': _('Extracted %d sample records across %d columns in %s ms.', len(records), len(columns), duration_ms),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.exception("Extraction test failed for ID %s", self.id)
            raise UserError(_("Extraction test failed: %s") % str(e))

    def run_preview_extraction(self, limit=10):
        """RPC helper to execute sample extraction for the Visual Builder sandbox."""
        self.ensure_one()
        start_ts = time.time()
        try:
            records, columns = self.execute_extraction(limit=limit, update_watermark=False)
            duration_ms = round((time.time() - start_ts) * 1000.0, 2)
            self.write({
                'preview_data': json.dumps(records[:limit], default=str),
                'last_extracted_count': len(records),
                'latency_ms': duration_ms,
            })
            return {
                'success': True,
                'records': records[:limit],
                'columns': columns,
                'total_extracted': len(records),
                'latency_ms': duration_ms,
            }
        except Exception as e:
            _logger.exception("Preview extraction failed for ID %s", self.id)
            return {
                'success': False,
                'error': str(e),
                'records': [],
                'columns': [],
                'total_extracted': 0,
                'latency_ms': 0.0,
            }

    def _apply_in_memory_projections_and_filters(self, records, columns):
        """Applies field selection, aliasing, type casting, WHERE filtering, and ORDER BY sorting to records in-memory."""
        if not records:
            # Even if records is empty, compute the projected columns
            selected_fields = json.loads(self.selected_fields_json or '[]')
            active_fields = [f for f in selected_fields if f.get('selected', True)]
            if active_fields:
                projected_columns = []
                for f in active_fields:
                    field_name = f.get('field', '').strip()
                    alias = f.get('alias', '').strip() or field_name
                    if alias and alias not in projected_columns:
                        projected_columns.append(alias)
                return records, projected_columns
            return records, columns

        selected_fields = json.loads(self.selected_fields_json or '[]')
        where_clauses = json.loads(self.where_clauses_json or '[]')
        sort_clauses = json.loads(self.sort_clauses_json or '[]')

        # 1. Apply WHERE Filtering
        if where_clauses:
            filtered_records = []
            for row in records:
                keep = True
                for idx, clause in enumerate(where_clauses):
                    c_field = clause.get('field', '').strip()
                    c_op = clause.get('operator', '=').strip().upper()
                    c_val = str(clause.get('value', '')).strip()
                    c_conj = clause.get('conjunction', 'AND').strip().upper()

                    if not c_field:
                        continue

                    cell_val = row.get(c_field)
                    cell_str = str(cell_val) if cell_val is not None else ''

                    match = False
                    if c_op == '=':
                        match = cell_str.lower() == c_val.lower()
                    elif c_op == '!=':
                        match = cell_str.lower() != c_val.lower()
                    elif c_op == '>':
                        try:
                            match = float(cell_str) > float(c_val)
                        except (ValueError, TypeError):
                            match = cell_str > c_val
                    elif c_op == '<':
                        try:
                            match = float(cell_str) < float(c_val)
                        except (ValueError, TypeError):
                            match = cell_str < c_val
                    elif c_op == '>=':
                        try:
                            match = float(cell_str) >= float(c_val)
                        except (ValueError, TypeError):
                            match = cell_str >= c_val
                    elif c_op == '<=':
                        try:
                            match = float(cell_str) <= float(c_val)
                        except (ValueError, TypeError):
                            match = cell_str <= c_val
                    elif c_op in ('LIKE', 'ILIKE', 'CONTAINS'):
                        match = c_val.lower() in cell_str.lower()
                    elif c_op == 'NOT LIKE':
                        match = c_val.lower() not in cell_str.lower()
                    elif c_op == 'IS NULL':
                        match = cell_val is None or cell_str == ''
                    elif c_op == 'IS NOT NULL':
                        match = cell_val is not None and cell_str != ''
                    elif c_op == 'IN':
                        in_vals = [v.strip().lower() for v in c_val.split(',')]
                        match = cell_str.lower() in in_vals
                    elif c_op == 'NOT IN':
                        in_vals = [v.strip().lower() for v in c_val.split(',')]
                        match = cell_str.lower() not in in_vals
                    else:
                        match = True

                    if idx == 0:
                        keep = match
                    else:
                        if c_conj == 'OR':
                            keep = keep or match
                        else:
                            keep = keep and match

                if keep:
                    filtered_records.append(row)
            records = filtered_records

        # 2. Apply ORDER BY Sorting
        if sort_clauses:
            for s in reversed(sort_clauses):
                sfield = s.get('field', '').strip()
                sdir = s.get('direction', 'ASC').strip().upper()
                if sfield:
                    reverse = (sdir == 'DESC')
                    records.sort(
                        key=lambda r: (r.get(sfield) is None, r.get(sfield) if r.get(sfield) is not None else ''),
                        reverse=reverse
                    )

        # 3. Apply Field Projections (Selection, Aliases, Type Casting)
        if selected_fields:
            active_fields = [f for f in selected_fields if f.get('selected', True)]
            if active_fields:
                projected_columns = []
                for f in active_fields:
                    field_name = f.get('field', '').strip()
                    alias = f.get('alias', '').strip() or field_name
                    if alias and alias not in projected_columns:
                        projected_columns.append(alias)

                projected_records = []
                for row in records:
                    new_row = {}
                    for f in active_fields:
                        src_col = f.get('field', '').strip()
                        out_col = f.get('alias', '').strip() or src_col
                        cast_type = f.get('cast', '').strip().lower()

                        val = row.get(src_col)

                        # Optional type casting
                        if cast_type in ('int', 'integer') and val is not None and val != '':
                            try:
                                val = int(float(str(val).strip()))
                            except (ValueError, TypeError):
                                pass
                        elif cast_type in ('float', 'decimal', 'numeric') and val is not None and val != '':
                            try:
                                val = float(str(val).strip())
                            except (ValueError, TypeError):
                                pass
                        elif cast_type in ('varchar', 'text', 'string') and val is not None:
                            val = str(val)
                        elif cast_type == 'boolean' and val is not None and val != '':
                            val = str(val).strip().lower() in ('1', 'true', 'yes', 't', 'y')

                        new_row[out_col] = val
                    projected_records.append(new_row)

                return projected_records, projected_columns

        return records, columns

    def execute_extraction(self, limit=None, update_watermark=True):
        """Executes data extraction based on strategy, compiled query, and updates watermark state."""
        self.ensure_one()
        conn = self.connection_id
        effective_limit = limit or self.max_records_limit or None

        # Build effective query string
        effective_query = self.compiled_query or self.custom_query or conn.db_query or "SELECT * FROM source_table"
        self._validate_query_safety(effective_query)

        # Handle incremental watermark parameter / clause
        if self.extraction_type == 'incremental_watermark' and self.watermark_column:
            last_wm = self.last_watermark_value or ('1970-01-01 00:00:00' if self.watermark_datatype != 'integer' else '0')
            if ':watermark' in effective_query:
                if self.watermark_datatype == 'integer':
                    effective_query = effective_query.replace(':watermark', str(last_wm))
                else:
                    effective_query = effective_query.replace(':watermark', f"'{last_wm}'")
            elif conn.conn_type == 'database_sql':
                wm_clause = f"{self.watermark_column} > '{last_wm}'" if self.watermark_datatype != 'integer' else f"{self.watermark_column} > {last_wm}"
                if 'WHERE' in effective_query.upper():
                    effective_query = f"{effective_query} AND {wm_clause}"
                else:
                    effective_query = f"{effective_query} WHERE {wm_clause}"

                if 'ORDER BY' not in effective_query.upper():
                    effective_query = f"{effective_query} ORDER BY {self.watermark_column} ASC"

        # Temporarily set connection db_query for execution
        original_query = conn.db_query
        try:
            if conn.conn_type == 'database_sql':
                conn.db_query = effective_query
                fetch_limit = effective_limit
            else:
                where_clauses = json.loads(self.where_clauses_json or '[]')
                fetch_limit = (effective_limit * 10) if (effective_limit and where_clauses) else (effective_limit if not where_clauses else None)
            records, columns = conn._fetch_raw_records(limit=fetch_limit)
        finally:
            if conn.conn_type == 'database_sql':
                conn.db_query = original_query

        # In-memory filter for non-SQL sources when incremental watermark is enabled
        if self.extraction_type == 'incremental_watermark' and self.watermark_column and conn.conn_type != 'database_sql':
            last_wm = self.last_watermark_value
            if last_wm:
                if self.watermark_datatype == 'integer':
                    try:
                        int_wm = int(last_wm)
                        records = [r for r in records if r.get(self.watermark_column) is not None and int(r.get(self.watermark_column, 0)) > int_wm]
                    except (ValueError, TypeError):
                        records = [r for r in records if str(r.get(self.watermark_column, '')) > str(last_wm)]
                else:
                    records = [r for r in records if str(r.get(self.watermark_column, '')) > str(last_wm)]

        # In-memory projection, filtering, aliasing, and sorting for non-SQL sources
        if conn.conn_type != 'database_sql':
            records, columns = self._apply_in_memory_projections_and_filters(records, columns)
            if effective_limit and len(records) > effective_limit:
                records = records[:effective_limit]

        # Update watermark state from extracted batch
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
                'message': _('Incremental watermark has been reset. Next run will extract all records from the beginning.'),
                'type': 'info',
            }
        }

    # ------------------------------------------------------------
    # 3. VISUAL BUILDER RPC DATA HANDLERS
    # ------------------------------------------------------------

    def get_visual_builder_data(self):
        """Provides full context and schema to the OWL Visual Extraction Builder widget."""
        self.ensure_one()
        schema_data = self.connection_id.inspect_source_schema() if self.connection_id else {'tables': []}

        return {
            'id': self.id,
            'name': self.name,
            'connection_id': self.connection_id.id if self.connection_id else False,
            'connection_name': self.connection_id.name if self.connection_id else '',
            'conn_type': self.conn_type or 'file_csv',
            'extraction_type': self.extraction_type,
            'use_visual_builder': self.use_visual_builder,
            'watermark_column': self.watermark_column or '',
            'last_watermark_value': self.last_watermark_value or '',
            'watermark_datatype': self.watermark_datatype,
            'selected_table': self.selected_table or 'source_table',
            'selected_fields': json.loads(self.selected_fields_json or '[]'),
            'where_clauses': json.loads(self.where_clauses_json or '[]'),
            'sort_clauses': json.loads(self.sort_clauses_json or '[]'),
            'custom_query': self.custom_query or '',
            'compiled_query': self.compiled_query or '',
            'ai_optimization_notes': self.ai_optimization_notes or '',
            'ai_explanation': self.ai_explanation or '',
            'preview_data': json.loads(self.preview_data or '[]'),
            'last_extracted_count': self.last_extracted_count,
            'latency_ms': self.latency_ms,
            'schema': schema_data,
        }

    def save_visual_builder_data(self, data):
        """Saves updated visual builder parameters from the OWL widget and recompiles query."""
        self.ensure_one()
        vals = {}
        if 'selected_table' in data:
            vals['selected_table'] = data['selected_table']
        if 'selected_fields' in data:
            vals['selected_fields_json'] = json.dumps(data['selected_fields'])
        if 'where_clauses' in data:
            vals['where_clauses_json'] = json.dumps(data['where_clauses'])
        if 'sort_clauses' in data:
            vals['sort_clauses_json'] = json.dumps(data['sort_clauses'])
        if 'custom_query' in data:
            vals['custom_query'] = data['custom_query']
        if 'use_visual_builder' in data:
            vals['use_visual_builder'] = data['use_visual_builder']
        if 'watermark_column' in data:
            vals['watermark_column'] = data['watermark_column']
        if 'extraction_type' in data:
            vals['extraction_type'] = data['extraction_type']

        self.write(vals)
        return self.get_visual_builder_data()

    # ------------------------------------------------------------
    # 4. AI INTEGRATION & QUERY OPTIMIZATION ASSISTANT
    # ------------------------------------------------------------

    def _get_ai_provider(self):
        """Helper to get configured active AI provider."""
        provider = self.env['migration.ai.config'].get_default_provider()
        if not provider:
            raise UserError(_(
                "No active AI Provider found. Please configure an AI Provider in 'ETL Pipeline Setup > AI Assistant Settings'."
            ))
        return provider

    def action_ai_generate_query(self, user_prompt):
        """Generates visual query configuration and SQL from natural language instructions."""
        self.ensure_one()
        ai_provider = self._get_ai_provider()

        # Build schema summary for AI prompt
        schema_data = self.connection_id.inspect_source_schema() if self.connection_id else {'tables': []}
        schema_summary = json.dumps(schema_data, indent=2)[:3000]

        sys_prompt = (
            "You are an expert Data Migration Engineer and SQL Optimizer for Odoo 19 ERP.\n"
            "Given the user request and source schema, construct an optimal extraction query.\n"
            "Always return ONLY a valid raw JSON object matching this schema:\n"
            "{\n"
            '  "selected_table": "table_name",\n'
            '  "selected_fields": [{"field": "col_name", "alias": "alias_name", "cast": "none|integer|float|varchar|date", "selected": true}],\n'
            '  "where_clauses": [{"field": "col_name", "operator": "=|!=|>|<|LIKE|IN|IS NOT NULL", "value": "val", "conjunction": "AND"}],\n'
            '  "sort_clauses": [{"field": "col_name", "direction": "ASC|DESC"}],\n'
            '  "watermark_column": "recommended_watermark_col_or_empty",\n'
            '  "sql_query": "SELECT ...",\n'
            '  "explanation": "Brief explanation of query logic and safety notes"\n'
            "}"
        )

        user_msg = (
            f"Connection Type: {self.conn_type}\n"
            f"Source Schema:\n{schema_summary}\n\n"
            f"User Requirement:\n{user_prompt}"
        )

        res = ai_provider.call_ai_completion(user_msg, system_prompt=sys_prompt, json_mode=True)
        if isinstance(res, dict):
            vals = {
                'ai_explanation': res.get('explanation', ''),
            }
            if res.get('selected_table'):
                vals['selected_table'] = res['selected_table']
            if res.get('selected_fields'):
                vals['selected_fields_json'] = json.dumps(res['selected_fields'])
            if res.get('where_clauses'):
                vals['where_clauses_json'] = json.dumps(res['where_clauses'])
            if res.get('sort_clauses'):
                vals['sort_clauses_json'] = json.dumps(res['sort_clauses'])
            if res.get('watermark_column'):
                vals['watermark_column'] = res['watermark_column']
                vals['extraction_type'] = 'incremental_watermark'
            if res.get('sql_query'):
                vals['custom_query'] = res['sql_query']

            self.write(vals)
            return {
                'success': True,
                'message': _('AI Query Generation Successful'),
                'data': self.get_visual_builder_data(),
            }

        raise UserError(_("AI provider did not return valid JSON."))

    def action_ai_optimize_query(self):
        """Analyzes query performance bottlenecks, suggests source indexes, and rewrites query for speed."""
        self.ensure_one()
        ai_provider = self._get_ai_provider()
        query = self.compiled_query or self.custom_query or "SELECT * FROM source_table"

        schema_data = self.connection_id.inspect_source_schema() if self.connection_id else {'tables': []}
        schema_summary = json.dumps(schema_data, indent=2)[:3000]

        sys_prompt = (
            "You are a database performance tuning specialist. Analyze this ETL extraction query for performance bottlenecks.\n"
            "Return ONLY a valid JSON object matching:\n"
            "{\n"
            '  "optimized_query": "SELECT ... (optimized query avoiding SELECT *, indexing hints, sargable predicates)",\n'
            '  "recommended_indexes": ["CREATE INDEX idx_... ON ... (...)"],\n'
            '  "performance_notes": "Detailed performance analysis and recommendations",\n'
            '  "watermark_advisor": "Suggestions on delta watermark efficiency"\n'
            "}"
        )

        user_msg = (
            f"Database Type: {self.conn_type} ({getattr(self.connection_id, 'db_type', 'standard')})\n"
            f"Extraction Strategy: {self.extraction_type}\n"
            f"Current Extraction Query:\n{query}\n\n"
            f"Source Schema Context:\n{schema_summary}"
        )

        res = ai_provider.call_ai_completion(user_msg, system_prompt=sys_prompt, json_mode=True)
        if isinstance(res, dict):
            notes = res.get('performance_notes', '')
            indexes = res.get('recommended_indexes', [])
            if indexes:
                notes += "\n\n### 🚀 Recommended Source Indexes:\n" + "\n".join([f"- `{idx}`" for idx in indexes])
            if res.get('watermark_advisor'):
                notes += f"\n\n### ⏱️ Watermark Strategy Advice:\n{res.get('watermark_advisor')}"

            self.write({
                'ai_optimization_notes': notes,
            })
            return {
                'success': True,
                'notes': notes,
                'optimized_query': res.get('optimized_query', query),
            }

        raise UserError(_("Failed to obtain AI optimization advice."))

    def action_ai_advise_watermark(self):
        """Analyzes schema and sample values to automatically identify and configure the ideal watermark field."""
        self.ensure_one()
        ai_provider = self._get_ai_provider()

        schema_info = json.loads(self.connection_id.source_schema_info or '{}')
        cols = json.loads(self.connection_id.source_columns or '[]')

        sys_prompt = (
            "You are an ETL watermark and incremental sync advisor.\n"
            "Given the column names and sample data types, select the best candidate column for watermark tracking.\n"
            "Return ONLY a valid JSON object matching:\n"
            "{\n"
            '  "watermark_column": "column_name",\n'
            '  "watermark_datatype": "datetime|date|integer",\n'
            '  "rationale": "Why this column is the optimal watermark"\n'
            "}"
        )

        user_msg = (
            f"Discovered Columns: {cols}\n"
            f"Schema Info: {json.dumps(schema_info, indent=2)}"
        )

        res = ai_provider.call_ai_completion(user_msg, system_prompt=sys_prompt, json_mode=True)
        if isinstance(res, dict) and res.get('watermark_column'):
            self.write({
                'watermark_column': res['watermark_column'],
                'watermark_datatype': res.get('watermark_datatype', 'datetime'),
                'extraction_type': 'incremental_watermark',
                'ai_explanation': res.get('rationale', ''),
            })
            return {
                'success': True,
                'watermark_column': res['watermark_column'],
                'watermark_datatype': res.get('watermark_datatype', 'datetime'),
                'rationale': res.get('rationale', ''),
            }

        raise UserError(_("Could not determine optimal watermark column."))

    def action_ai_explain_query(self):
        """Generates a plain-language explanation and risk audit of the current extraction query."""
        self.ensure_one()
        ai_provider = self._get_ai_provider()
        query = self.compiled_query or self.custom_query or "SELECT * FROM source_table"

        sys_prompt = (
            "You are a data migration auditor. Explain what this extraction query does in plain English.\n"
            "Identify potential data risks such as NULL values in filtered fields, timezone discrepancies in date filters, or sorting stability.\n"
            "Return ONLY a valid JSON object matching:\n"
            "{\n"
            '  "summary": "Plain English summary of the extraction",\n'
            '  "risk_audit": "Audit of potential data pitfalls, null risks, and boundary edge cases",\n'
            '  "downstream_impact": "Notes on how extracted columns align with standard Odoo models"\n'
            "}"
        )

        res = ai_provider.call_ai_completion(f"Query:\n{query}", system_prompt=sys_prompt, json_mode=True)
        if isinstance(res, dict):
            audit = (
                f"### 📋 Query Summary\n{res.get('summary', '')}\n\n"
                f"### ⚠️ Data Pitfalls & Edge Case Audit\n{res.get('risk_audit', '')}\n\n"
                f"### 🔄 Downstream Impact\n{res.get('downstream_impact', '')}"
            )
            self.write({'ai_explanation': audit})
            return {
                'success': True,
                'explanation': audit,
            }

        raise UserError(_("Failed to generate AI query explanation."))
