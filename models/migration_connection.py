# -*- coding: utf-8 -*-

import base64
import csv
import io
import json
import logging
import os
import struct

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MigrationConnection(models.Model):
    _name = 'migration.connection'
    _description = 'Data Migration Connection'
    _order = 'name asc'

    name = fields.Char(string='Connection Name', required=True)
    conn_type = fields.Selection([
        ('file_csv', 'CSV File'),
        ('file_excel', 'Excel File (.xlsx / .xls)'),
        ('file_json', 'JSON File'),
        ('foxpro_dbf', 'Visual FoxPro DBF File / Directory'),
        ('odbc', 'ODBC Connection (DSN / Connection String)'),
        ('database_sql', 'Direct SQL Database (PostgreSQL / MySQL / SQL Server)'),
        ('odoo_rpc', 'Odoo XML-RPC / JSON-RPC Endpoint'),
    ], string='Connection Type', default='file_csv', required=True)

    # File Storage
    source_type = fields.Selection([
        ('upload', 'File Upload'),
        ('path', 'Server File/Folder Path'),
    ], string='Source Location', default='upload')
    file_binary = fields.Binary(string='Upload File', attachment=True)
    file_name = fields.Char(string='File Name')
    file_path = fields.Char(string='Server File / Directory Path', help='Absolute filesystem path on the Odoo server host.')
    file_encoding = fields.Selection([
        ('utf-8', 'UTF-8'),
        ('cp1252', 'Windows CP1252 (Western European)'),
        ('cp850', 'DOS CP850 (Latin 1)'),
        ('latin1', 'ISO-8859-1 (Latin-1)'),
        ('gbk', 'GBK / GB2312 (Chinese)'),
        ('shift_jis', 'Shift-JIS (Japanese)'),
    ], string='File Encoding', default='utf-8')
    csv_delimiter = fields.Char(string='CSV Delimiter', default=',')
    csv_quotechar = fields.Char(string='CSV Quote Character', default='"')

    # FoxPro DBF Options
    dbf_table_name = fields.Char(string='DBF Table Name', help='Specify DBF file name if directory path is specified.')
    dbf_memo_path = fields.Char(string='Memo File Path (.fpt / .dbt)', help='Optional path to associated memo file for text fields.')

    # ODBC Configuration
    odbc_connection_string = fields.Char(
        string='ODBC Connection String',
        help='Driver={FoxPro Files};Dbq=C:\\Data; or DSN=MyLegacyDSN;UID=user;PWD=pass;'
    )

    # SQL DB Configuration
    db_type = fields.Selection([
        ('postgresql', 'PostgreSQL'),
        ('mysql', 'MySQL'),
        ('mssql', 'Microsoft SQL Server'),
    ], string='Database Type', default='postgresql')
    db_host = fields.Char(string='Host', default='localhost')
    db_port = fields.Integer(string='Port', default=5432)
    db_name = fields.Char(string='Database Name')
    db_user = fields.Char(string='Username')
    db_password = fields.Char(string='Password')
    db_query = fields.Text(string='SQL Query / Table', help='e.g., SELECT * FROM customers OR customer_table')

    # Odoo RPC Configuration
    rpc_url = fields.Char(string='Odoo URL', placeholder='https://odoo.example.com')
    rpc_db = fields.Char(string='Remote Database')
    rpc_user = fields.Char(string='Remote User')
    rpc_password = fields.Char(string='API Key / Password')
    rpc_model = fields.Char(string='Remote Model Name', placeholder='res.partner')
    rpc_domain = fields.Char(string='Search Domain Filter', default='[]')

    # Status & Cached Columns
    state = fields.Selection([
        ('draft', 'Draft'),
        ('connected', 'Connected / Tested'),
        ('error', 'Connection Error'),
    ], string='Status', default='draft', readonly=True)
    last_error = fields.Text(string='Last Connection Error', readonly=True)
    source_columns = fields.Text(string='Discovered Source Columns (JSON)', help='JSON array of column names.')
    preview_data = fields.Text(string='Sample Data Preview (JSON)', help='JSON preview of top 5 rows.')

    # ------------------------------------------------------------
    # CONNECTION TESTING & DATA FETCHING
    # ------------------------------------------------------------

    def action_test_connection(self):
        """Test connection and extract header columns + preview data."""
        self.ensure_one()
        try:
            records, columns = self._fetch_raw_records(limit=5)
            self.write({
                'state': 'connected',
                'last_error': False,
                'source_columns': json.dumps(columns),
                'preview_data': json.dumps(records, default=str),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Successfully extracted %s columns from source.', len(columns)),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.exception("Failed to test connection ID %s", self.id)
            self.write({
                'state': 'error',
                'last_error': str(e),
            })
            raise UserError(_("Connection failed: %s") % str(e))

    def _fetch_raw_records(self, limit=None):
        """Unified raw record fetcher returning (list_of_dicts, list_of_column_names)."""
        self.ensure_one()
        if self.conn_type == 'file_csv':
            return self._parse_csv(limit=limit)
        elif self.conn_type == 'file_excel':
            return self._parse_excel(limit=limit)
        elif self.conn_type == 'file_json':
            return self._parse_json(limit=limit)
        elif self.conn_type == 'foxpro_dbf':
            return self._parse_foxpro_dbf(limit=limit)
        elif self.conn_type == 'odbc':
            return self._parse_odbc(limit=limit)
        elif self.conn_type == 'database_sql':
            return self._parse_sql_db(limit=limit)
        elif self.conn_type == 'odoo_rpc':
            return self._parse_odoo_rpc(limit=limit)
        else:
            raise UserError(_("Unsupported connection type: %s") % self.conn_type)

    # ------------------------------------------------------------
    # PARSERS FOR VARIOUS SOURCE TYPES
    # ------------------------------------------------------------

    def _get_file_content_bytes(self):
        """Retrieve bytes from binary upload or local file path."""
        if self.source_type == 'upload':
            if not self.file_binary:
                raise UserError(_("Please upload a file."))
            return base64.b64decode(self.file_binary)
        else:
            if not self.file_path or not os.path.exists(self.file_path):
                raise UserError(_("File path '%s' does not exist on server.") % self.file_path)
            with open(self.file_path, 'rb') as f:
                return f.read()

    def _parse_csv(self, limit=None):
        content = self._get_file_content_bytes()
        encoding = self.file_encoding or 'utf-8'
        text_stream = io.StringIO(content.decode(encoding, errors='replace'))
        delimiter = self.csv_delimiter or ','
        quotechar = self.csv_quotechar or '"'
        reader = csv.DictReader(text_stream, delimiter=delimiter, quotechar=quotechar)
        columns = reader.fieldnames or []
        records = []
        for idx, row in enumerate(reader):
            if limit and idx >= limit:
                break
            records.append(row)
        return records, list(columns)

    def _parse_excel(self, limit=None):
        content = self._get_file_content_bytes()
        file_stream = io.BytesIO(content)
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_stream, data_only=True)
            sheet = wb.active
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                return [], []
            columns = [str(col) if col is not None else f"col_{i}" for i, col in enumerate(rows[0])]
            records = []
            for r_idx, row in enumerate(rows[1:]):
                if limit and r_idx >= limit:
                    break
                record = {columns[c_idx]: (val if val is not None else '') for c_idx, val in enumerate(row)}
                records.append(record)
            return records, columns
        except ImportError:
            raise UserError(_("Python library 'openpyxl' is required to parse Excel files. Please install it on the server."))

    def _parse_json(self, limit=None):
        content = self._get_file_content_bytes()
        encoding = self.file_encoding or 'utf-8'
        data = json.loads(content.decode(encoding, errors='replace'))
        if isinstance(data, dict):
            # If wrapped in a object key, try finding first list key
            for k, v in data.items():
                if isinstance(v, list):
                    data = v
                    break
        if not isinstance(data, list):
            raise UserError(_("JSON file content must be a JSON array of objects."))
        columns = set()
        for item in data[:50]:
            if isinstance(item, dict):
                columns.update(item.keys())
        columns = sorted(list(columns))
        records = data[:limit] if limit else data
        return records, columns

    def _parse_foxpro_dbf(self, limit=None):
        """Read Visual FoxPro DBF table natively or via dbfread."""
        # Try dbfread library first
        content_bytes = None
        target_path = self.file_path
        if self.source_type == 'upload' or not target_path:
            content_bytes = self._get_file_content_bytes()
        else:
            if os.path.isdir(target_path) and self.dbf_table_name:
                target_path = os.path.join(target_path, self.dbf_table_name)
            if not os.path.exists(target_path):
                raise UserError(_("DBF File path '%s' not found.") % target_path)

        encoding = self.file_encoding or 'cp1252'

        # Attempt native Python binary DBF parsing (dBase III / IV / Visual FoxPro)
        try:
            if content_bytes is None and target_path:
                with open(target_path, 'rb') as f:
                    content_bytes = f.read()

            return self._parse_dbf_bytes_natively(content_bytes, encoding=encoding, limit=limit)
        except Exception as err:
            _logger.info("Native DBF parser failed (%s), falling back to dbfread library...", err)
            try:
                import dbfread
                if target_path and os.path.exists(target_path):
                    table = dbfread.DBF(target_path, encoding=encoding, ignore_missing_memofile=True)
                else:
                    # Write to temp stream
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.dbf', delete=False) as tmp:
                        tmp.write(content_bytes)
                        tmp_path = tmp.name
                    table = dbfread.DBF(tmp_path, encoding=encoding, ignore_missing_memofile=True)
                columns = table.field_names
                records = []
                for idx, record in enumerate(table):
                    if limit and idx >= limit:
                        break
                    records.append(dict(record))
                return records, columns
            except ImportError:
                raise UserError(_("DBF Parsing error: %s") % str(err))

    def _parse_dbf_bytes_natively(self, data, encoding='cp1252', limit=None):
        """Native binary reader for Visual FoxPro / dBase DBF headers and records."""
        if len(data) < 32:
            raise UserError(_("Invalid DBF file header: file too small."))
        header_fmt = '<BBBBIHH14s'
        version, yy, mm, dd, num_records, header_len, record_len = struct.unpack('<BBBBIHH', data[:12])

        # Header fields start at byte 32, each field descriptor is 32 bytes ending with 0x0D
        fields_data = data[32:header_len]
        fields = []
        offset = 0
        while offset < len(fields_data):
            if fields_data[offset] == 0x0D:
                break
            field_desc = fields_data[offset:offset+32]
            if len(field_desc) < 32:
                break
            field_name_raw = field_desc[:11].replace(b'\x00', b'').decode(encoding, errors='ignore').strip()
            field_type = chr(field_desc[11])
            field_len = field_desc[16]
            field_dec = field_desc[17]
            fields.append({
                'name': field_name_raw,
                'type': field_type,
                'len': field_len,
                'dec': field_dec,
            })
            offset += 32

        columns = [f['name'] for f in fields]
        records = []
        rec_start = header_len

        for rec_idx in range(num_records):
            if limit and rec_idx >= limit:
                break
            rec_offset = rec_start + (rec_idx * record_len)
            if rec_offset + record_len > len(data):
                break
            rec_bytes = data[rec_offset:rec_offset+record_len]
            # Check deletion flag byte
            if rec_bytes and rec_bytes[0:1] == b'*':
                continue # Skip deleted record
            
            row = {}
            pos = 1 # Skip deletion flag byte
            for f in fields:
                val_bytes = rec_bytes[pos:pos+f['len']]
                pos += f['len']
                val_str = val_bytes.decode(encoding, errors='replace').strip()
                if f['type'] in ('N', 'F'):
                    if val_str:
                        val = float(val_str) if '.' in val_str else int(val_str)
                    else:
                        val = 0
                elif f['type'] == 'L':
                    val = val_str in ('T', 't', 'Y', 'y', '1')
                else:
                    val = val_str
                row[f['name']] = val
            records.append(row)

        return records, columns

    def _parse_odbc(self, limit=None):
        """Query data source via ODBC using pyodbc."""
        if not self.odbc_connection_string:
            raise UserError(_("Please provide an ODBC Connection String."))
        try:
            import pyodbc
            conn = pyodbc.connect(self.odbc_connection_string)
            cursor = conn.cursor()
            query = self.db_query or "SELECT * FROM source_table"
            if limit:
                query = f"SELECT TOP {limit} * FROM ({query}) AS subquery"
            cursor.execute(query)
            columns = [column[0] for column in cursor.description]
            records = []
            for row in cursor.fetchall():
                records.append(dict(zip(columns, row)))
            cursor.close()
            conn.close()
            return records, columns
        except ImportError:
            raise UserError(_("Python library 'pyodbc' is required for ODBC connections. Please install pyodbc on the server."))
        except Exception as e:
            raise UserError(_("ODBC error: %s") % str(e))

    def _parse_sql_db(self, limit=None):
        """Connect to direct PostgreSQL/MySQL/SQLServer database."""
        db_type = self.db_type
        host = self.db_host or 'localhost'
        port = self.db_port or 5432
        dbname = self.db_name
        user = self.db_user
        pwd = self.db_password
        query = self.db_query or "SELECT * FROM source_table"

        if db_type == 'postgresql':
            try:
                import psycopg2
                import psycopg2.extras
                conn = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=pwd)
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                if limit:
                    query = f"SELECT * FROM ({query}) sub LIMIT {limit}"
                cursor.execute(query)
                records = [dict(r) for r in cursor.fetchall()]
                columns = list(records[0].keys()) if records else []
                cursor.close()
                conn.close()
                return records, columns
            except ImportError:
                raise UserError(_("psycopg2 is required for PostgreSQL connections."))
            except Exception as e:
                raise UserError(_("PostgreSQL connection error: %s") % str(e))
        else:
            raise UserError(_("Database driver for '%s' is not installed or configured.") % db_type)

    def _parse_odoo_rpc(self, limit=None):
        """Fetch records from remote Odoo instance via XML-RPC."""
        import xmlrpc.client
        url = (self.rpc_url or '').rstrip('/')
        db = self.rpc_db
        user = self.rpc_user
        password = self.rpc_password
        model = self.rpc_model
        domain = eval(self.rpc_domain or '[]')

        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, user, password, {})
        if not uid:
            raise UserError(_("Remote Odoo authentication failed."))
        models_api = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        ids = models_api.execute_kw(db, uid, password, model, 'search', [domain], {'limit': limit or 100})
        fields_info = models_api.execute_kw(db, uid, password, model, 'fields_get', [], {'attributes': ['string', 'type']})
        columns = sorted(list(fields_info.keys()))
        records = models_api.execute_kw(db, uid, password, model, 'read', [ids], {'fields': columns})
        return records, columns
