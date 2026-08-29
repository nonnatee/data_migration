# -*- coding: utf-8 -*-

import base64
import json
from unittest.mock import patch
from odoo.tests import common
from odoo.exceptions import UserError


class TestMigrationExtractionAI(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model'].search([('model', '=', 'res.partner')], limit=1)

        csv_content = (
            "id,name,email,created_at,amount\n"
            "101,Acme Corp,acme@example.com,2026-01-01 10:00:00,5000\n"
            "102,Globex,globex@example.com,2026-01-02 12:00:00,12000\n"
            "103,Soylent,soylent@example.com,2026-01-03 14:00:00,3500\n"
            "104,Initech,initech@example.com,2026-01-04 16:00:00,22000\n"
        )
        cls.conn = cls.env['migration.connection'].create({
            'name': 'Test Extraction Source',
            'conn_type': 'file_csv',
            'source_type': 'upload',
            'file_binary': base64.b64encode(csv_content.encode('utf-8')),
            'source_columns': json.dumps(['id', 'name', 'email', 'created_at', 'amount']),
            'source_schema_info': json.dumps({
                'id': {'inferred_type': 'integer', 'sample_value': '101'},
                'name': {'inferred_type': 'varchar', 'sample_value': 'Acme Corp'},
                'email': {'inferred_type': 'varchar', 'sample_value': 'acme@example.com'},
                'created_at': {'inferred_type': 'datetime', 'sample_value': '2026-01-01 10:00:00'},
                'amount': {'inferred_type': 'float', 'sample_value': '5000'},
            }),
        })

        cls.ai_config = cls.env['migration.ai.config'].create({
            'name': 'Mock AI Assistant',
            'provider': 'openai',
            'model_name': 'gpt-4o-mini',
            'api_key': 'dummy-api-key',
            'is_default': True,
        })

    def test_01_visual_query_compilation(self):
        """Test compiling visual builder settings into standard SQL query."""
        extraction = self.env['migration.extraction'].create({
            'name': 'Visual SQL Extraction',
            'connection_id': self.conn.id,
            'selected_table': 'legacy_customers',
            'use_visual_builder': True,
            'selected_fields_json': json.dumps([
                {'field': 'id', 'alias': 'customer_id', 'cast': 'integer', 'selected': True},
                {'field': 'name', 'alias': 'full_name', 'cast': 'varchar', 'selected': True},
                {'field': 'amount', 'alias': 'total_spend', 'cast': 'float', 'selected': True},
                {'field': 'email', 'alias': 'email', 'cast': 'none', 'selected': False},
            ]),
            'where_clauses_json': json.dumps([
                {'field': 'amount', 'operator': '>', 'value': '1000', 'conjunction': 'AND'},
                {'field': 'name', 'operator': 'IS NOT NULL', 'value': '', 'conjunction': 'AND'},
            ]),
            'sort_clauses_json': json.dumps([
                {'field': 'created_at', 'direction': 'DESC'},
            ]),
        })

        compiled = extraction.compile_query_from_visual()
        self.assertIn("SELECT CAST(id AS integer) AS customer_id, CAST(name AS varchar) AS full_name, CAST(amount AS float) AS total_spend", compiled)
        self.assertIn("FROM legacy_customers", compiled)
        self.assertIn("WHERE amount > 1000 AND name IS NOT NULL", compiled)
        self.assertIn("ORDER BY created_at DESC", compiled)

    def test_02_query_safety_validation(self):
        """Test that destructive SQL statements are strictly rejected."""
        extraction = self.env['migration.extraction'].create({
            'name': 'Safety Check Extraction',
            'connection_id': self.conn.id,
        })

        # Test malicious DROP TABLE
        with self.assertRaises(UserError) as cm:
            extraction._validate_query_safety("SELECT * FROM users; DROP TABLE users;")
        self.assertIn("Prohibited", str(cm.exception))

        # Test malicious DELETE FROM
        with self.assertRaises(UserError) as cm:
            extraction._validate_query_safety("DELETE FROM orders WHERE 1=1")
        self.assertIn("Prohibited", str(cm.exception))

        # Test malicious TRUNCATE
        with self.assertRaises(UserError) as cm:
            extraction._validate_query_safety("TRUNCATE table_name")
        self.assertIn("Prohibited", str(cm.exception))

        # Test safe SELECT
        extraction._validate_query_safety("SELECT id, name, created_at FROM accounts WHERE active = 1")

    def test_03_downstream_template_column_sync(self):
        """Test that template retrieves projected aliases from extraction."""
        extraction = self.env['migration.extraction'].create({
            'name': 'Aliased Extraction',
            'connection_id': self.conn.id,
            'selected_fields_json': json.dumps([
                {'field': 'id', 'alias': 'ext_id', 'selected': True},
                {'field': 'name', 'alias': 'client_title', 'selected': True},
            ]),
        })

        cols = extraction.get_extraction_columns()
        self.assertEqual(cols, ['ext_id', 'client_title'])

        template = self.env['migration.template'].create({
            'name': 'Synced Template',
            'connection_id': self.conn.id,
            'extraction_id': extraction.id,
            'target_model_id': self.partner_model.id,
        })
        available_vars = template.get_available_source_variables()
        self.assertIn('ext_id', available_vars)
        self.assertIn('client_title', available_vars)

    def test_04_preview_sandbox_execution(self):
        """Test running sample preview extraction via RPC handler."""
        extraction = self.env['migration.extraction'].create({
            'name': 'Sandbox Extraction',
            'connection_id': self.conn.id,
            'extraction_type': 'full',
        })

        res = extraction.run_preview_extraction(limit=2)
        self.assertTrue(res['success'])
        self.assertEqual(len(res['records']), 2)
        self.assertIn('id', res['columns'])
        self.assertGreaterEqual(res['latency_ms'], 0.0)

    @patch('odoo.addons.data_migration.models.migration_ai_config.MigrationAIConfig.call_ai_completion')
    def test_05_ai_query_generation(self, mock_ai):
        """Test AI natural language extraction query generation."""
        mock_ai.return_value = {
            'selected_table': 'customers',
            'selected_fields': [
                {'field': 'id', 'alias': 'cust_id', 'cast': 'integer', 'selected': True},
                {'field': 'name', 'alias': 'cust_name', 'cast': 'varchar', 'selected': True},
            ],
            'where_clauses': [
                {'field': 'amount', 'operator': '>', 'value': '10000', 'conjunction': 'AND'}
            ],
            'sort_clauses': [
                {'field': 'created_at', 'direction': 'DESC'}
            ],
            'watermark_column': 'created_at',
            'sql_query': "SELECT id AS cust_id, name AS cust_name FROM customers WHERE amount > 10000 ORDER BY created_at DESC",
            'explanation': 'Extracts VIP customers spending over 10k.',
        }

        extraction = self.env['migration.extraction'].create({
            'name': 'AI Generator Test',
            'connection_id': self.conn.id,
        })

        res = extraction.action_ai_generate_query("Extract VIP customers")
        self.assertTrue(res['success'])
        self.assertEqual(extraction.selected_table, 'customers')
        self.assertEqual(extraction.watermark_column, 'created_at')
        self.assertEqual(extraction.extraction_type, 'incremental_watermark')

    @patch('odoo.addons.data_migration.models.migration_ai_config.MigrationAIConfig.call_ai_completion')
    def test_06_ai_query_optimizer_and_advisor(self, mock_ai):
        """Test AI Performance Optimizer and Watermark Advisor."""
        mock_ai.return_value = {
            'optimized_query': 'SELECT id, name, created_at FROM legacy_customers WHERE created_at > :watermark',
            'recommended_indexes': ['CREATE INDEX idx_created_at ON legacy_customers(created_at)'],
            'performance_notes': 'Explicit columns projection prevents table scans.',
            'watermark_advisor': 'Use created_at timestamp with B-tree index.',
        }

        extraction = self.env['migration.extraction'].create({
            'name': 'Optimizer Test',
            'connection_id': self.conn.id,
            'custom_query': 'SELECT * FROM legacy_customers',
        })

        res = extraction.action_ai_optimize_query()
        self.assertTrue(res['success'])
        self.assertIn("Recommended Source Indexes", extraction.ai_optimization_notes)
        self.assertIn("CREATE INDEX idx_created_at", extraction.ai_optimization_notes)
