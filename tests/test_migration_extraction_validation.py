# -*- coding: utf-8 -*-

import base64
import json
from odoo.tests import common
from odoo.exceptions import UserError


class TestMigrationExtractionValidation(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model'].search([('model', '=', 'res.partner')], limit=1)
        cls.name_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'name')], limit=1)
        cls.email_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'email')], limit=1)
        cls.ref_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'ref')], limit=1)

        csv_content = (
            "id,name,email,age,updated_at\n"
            "1,Alice,alice@example.com,28,2026-01-01 10:00:00\n"
            "2,Bob,bob@invalid-email,15,2026-01-02 12:00:00\n"
            "3,,charlie@example.com,35,2026-01-03 14:00:00\n"
            "4,David,david@example.com,42,2026-01-04 16:00:00\n"
        )
        cls.conn = cls.env['migration.connection'].create({
            'name': 'Test Extraction Connection',
            'conn_type': 'file_csv',
            'source_type': 'upload',
            'file_binary': base64.b64encode(csv_content.encode('utf-8')),
            'source_columns': json.dumps(['id', 'name', 'email', 'age', 'updated_at']),
        })

        cls.template = cls.env['migration.template'].create({
            'name': 'Test Validation Template',
            'connection_id': cls.conn.id,
            'target_model_id': cls.partner_model.id,
            'operation_mode': 'upsert',
        })

        cls.env['migration.mapping.line'].create({
            'template_id': cls.template.id,
            'source_field': 'name',
            'target_field_id': cls.name_field.id,
        })
        cls.env['migration.mapping.line'].create({
            'template_id': cls.template.id,
            'source_field': 'email',
            'target_field_id': cls.email_field.id,
        })
        cls.env['migration.mapping.line'].create({
            'template_id': cls.template.id,
            'source_field': 'id',
            'target_field_id': cls.ref_field.id,
            'is_key_field': True,
        })

    def test_01_extraction_and_watermarks(self):
        """Test extraction query execution and watermark tracking."""
        extraction = self.env['migration.extraction'].create({
            'name': 'Incremental Partner Extraction',
            'connection_id': self.conn.id,
            'extraction_type': 'incremental_watermark',
            'watermark_column': 'updated_at',
        })

        # Run extraction
        records, columns = extraction.execute_extraction(update_watermark=True)
        self.assertEqual(len(records), 4)
        self.assertEqual(extraction.last_watermark_value, '2026-01-04 16:00:00')

        # Test reset
        extraction.action_reset_watermark()
        self.assertFalse(extraction.last_watermark_value)

    def test_02_validation_rules_evaluation(self):
        """Test mandatory, regex, numeric range, and business rules."""
        # 1. Mandatory Rule on Name
        r_mandatory = self.env['migration.validation.rule'].create({
            'template_id': self.template.id,
            'name': 'Name is required',
            'source_field': 'name',
            'rule_type': 'mandatory',
            'action_on_failure': 'reject_record',
        })
        valid, err = r_mandatory.evaluate_rule('Alice', {'name': 'Alice'})
        self.assertTrue(valid)
        valid, err = r_mandatory.evaluate_rule('', {'name': ''})
        self.assertFalse(valid)

        # 2. Regex Rule on Email
        r_regex = self.env['migration.validation.rule'].create({
            'template_id': self.template.id,
            'name': 'Valid Email Format',
            'source_field': 'email',
            'rule_type': 'regex',
            'regex_pattern': r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
            'action_on_failure': 'reject_record',
        })
        valid, err = r_regex.evaluate_rule('alice@example.com', {})
        self.assertTrue(valid)
        valid, err = r_regex.evaluate_rule('bob@invalid-email', {})
        self.assertFalse(valid)

        # 3. Numeric Range on Age (Min 18)
        r_range = self.env['migration.validation.rule'].create({
            'template_id': self.template.id,
            'name': 'Adult Age Check',
            'source_field': 'age',
            'rule_type': 'numeric_range',
            'min_value': 18.0,
            'check_min': True,
        })
        valid, err = r_range.evaluate_rule(28, {})
        self.assertTrue(valid)
        valid, err = r_range.evaluate_rule(15, {})
        self.assertFalse(valid)

    def test_03_job_execution_with_validation_filtering(self):
        """Test ETL job execution where invalid records are rejected by validation rules."""
        self.env['migration.validation.rule'].create({
            'template_id': self.template.id,
            'name': 'Name is required',
            'source_field': 'name',
            'rule_type': 'mandatory',
            'action_on_failure': 'reject_record',
        })
        self.env['migration.validation.rule'].create({
            'template_id': self.template.id,
            'name': 'Valid Email',
            'source_field': 'email',
            'rule_type': 'regex',
            'regex_pattern': r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
            'action_on_failure': 'reject_record',
        })

        job = self.env['migration.job'].create({
            'template_id': self.template.id,
        })
        job._execute_job()

        # Total 4 records:
        # Row 1 (Alice): Valid -> Created
        # Row 2 (Bob): Invalid Email -> Rejected
        # Row 3 (Empty Name): Invalid Name -> Rejected
        # Row 4 (David): Valid -> Created
        self.assertEqual(job.total_records, 4)
        self.assertEqual(job.success_records, 2)
        self.assertEqual(job.error_records, 2)
        self.assertEqual(job.state, 'done_with_errors')

        # Check partners created
        p_alice = self.env['res.partner'].search([('ref', '=', '1')], limit=1)
        self.assertTrue(p_alice.exists())
        self.assertEqual(p_alice.name, 'Alice')

        p_bob = self.env['res.partner'].search([('ref', '=', '2')], limit=1)
        self.assertFalse(p_bob.exists())

    def test_04_ai_config_creation_and_defaults(self):
        """Test AI Provider Configuration settings."""
        ai_config = self.env['migration.ai.config'].create({
            'name': 'OpenAI Testing',
            'provider': 'openai',
            'model_name': 'gpt-4o-mini',
            'api_key': 'test-dummy-key',
            'is_default': True,
        })
        self.assertTrue(ai_config.is_default)
        default_p = self.env['migration.ai.config'].get_default_provider()
        self.assertEqual(default_p.id, ai_config.id)

    def test_05_extraction_field_selection_and_projection(self):
        """Test that field selection, deselected fields, aliases, and WHERE filters are properly applied in extraction."""
        extraction = self.env['migration.extraction'].create({
            'name': 'Projected Partner Extraction',
            'connection_id': self.conn.id,
            'extraction_type': 'custom_query',
            'selected_fields_json': json.dumps([
                {'field': 'id', 'alias': 'partner_ref', 'cast': 'integer', 'selected': True},
                {'field': 'name', 'alias': 'name', 'cast': 'none', 'selected': True},
                {'field': 'email', 'alias': 'email', 'cast': 'none', 'selected': False},  # Unselected (excluded)
                {'field': 'age', 'alias': 'age_years', 'cast': 'integer', 'selected': True},
                {'field': 'updated_at', 'alias': 'updated_at', 'cast': 'none', 'selected': False},  # Unselected
            ]),
            'where_clauses_json': json.dumps([
                {'field': 'age', 'operator': '>=', 'value': '28', 'conjunction': 'AND'}
            ]),
            'sort_clauses_json': json.dumps([
                {'field': 'age', 'direction': 'DESC'}
            ]),
        })

        records, columns = extraction.execute_extraction(limit=10, update_watermark=False)

        # 1. Verify projected columns only contains selected fields and aliases
        self.assertEqual(columns, ['partner_ref', 'name', 'age_years'])
        self.assertNotIn('email', columns)
        self.assertNotIn('updated_at', columns)

        # 2. Verify WHERE filter (age >= 28: Alice=28, Charlie=35, David=42; Bob=15 is excluded)
        self.assertEqual(len(records), 3)

        # 3. Verify ORDER BY (DESC by age: David(42), Charlie(35), Alice(28))
        self.assertEqual(records[0]['partner_ref'], 4)
        self.assertEqual(records[0]['name'], 'David')
        self.assertEqual(records[0]['age_years'], 42)
        self.assertNotIn('email', records[0])
        self.assertNotIn('updated_at', records[0])

        # 4. Test run_preview_extraction RPC helper
        preview_res = extraction.run_preview_extraction(limit=10)
        self.assertTrue(preview_res['success'])
        self.assertEqual(preview_res['columns'], ['partner_ref', 'name', 'age_years'])
        self.assertEqual(len(preview_res['records']), 3)
