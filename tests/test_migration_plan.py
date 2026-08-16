# -*- coding: utf-8 -*-

import json
from odoo.tests import common
from odoo.exceptions import UserError


class TestMigrationPlan(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # 1. Partner Model & Fields
        cls.partner_model = cls.env['ir.model'].search([('model', '=', 'res.partner')], limit=1)
        cls.p_name_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'name')], limit=1)
        cls.p_email_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'email')], limit=1)
        cls.p_ref_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'ref')], limit=1)

        # 2. Product Template Model & Fields
        cls.product_model = cls.env['ir.model'].search([('model', '=', 'product.template')], limit=1)
        cls.prod_name_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.product_model.id), ('name', '=', 'name')], limit=1)
        cls.prod_code_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.product_model.id), ('name', '=', 'default_code')], limit=1)

        # 3. Connection with Mock Records
        cls.conn_partner = cls.env['migration.connection'].create({
            'name': 'Mock Partners CSV',
            'conn_type': 'file_csv',
            'source_columns': json.dumps(['code', 'name', 'email']),
            'state': 'connected',
        })

        cls.conn_product = cls.env['migration.connection'].create({
            'name': 'Mock Products CSV',
            'conn_type': 'file_csv',
            'source_columns': json.dumps(['prod_code', 'prod_name']),
            'state': 'connected',
        })

        # 4. Partner Template
        cls.template_partner = cls.env['migration.template'].create({
            'name': 'Partner Template',
            'connection_id': cls.conn_partner.id,
            'target_model_id': cls.partner_model.id,
            'operation_mode': 'upsert',
        })
        cls.env['migration.mapping.line'].create({
            'template_id': cls.template_partner.id,
            'source_field': 'name',
            'target_field_id': cls.p_name_field.id,
            'transform_type': 'direct',
        })
        cls.env['migration.mapping.line'].create({
            'template_id': cls.template_partner.id,
            'source_field': 'email',
            'target_field_id': cls.p_email_field.id,
            'transform_type': 'direct',
        })
        cls.env['migration.mapping.line'].create({
            'template_id': cls.template_partner.id,
            'source_field': 'code',
            'target_field_id': cls.p_ref_field.id,
            'transform_type': 'direct',
            'is_key_field': True,
        })

        # 5. Product Template
        cls.template_product = cls.env['migration.template'].create({
            'name': 'Product Template',
            'connection_id': cls.conn_product.id,
            'target_model_id': cls.product_model.id,
            'operation_mode': 'upsert',
        })
        cls.env['migration.mapping.line'].create({
            'template_id': cls.template_product.id,
            'source_field': 'prod_name',
            'target_field_id': cls.prod_name_field.id,
            'transform_type': 'direct',
        })
        cls.env['migration.mapping.line'].create({
            'template_id': cls.template_product.id,
            'source_field': 'prod_code',
            'target_field_id': cls.prod_code_field.id,
            'transform_type': 'direct',
            'is_key_field': True,
        })

    def test_01_plan_creation_and_preflight(self):
        """Test plan hierarchy creation and pre-flight validation check."""
        plan = self.env['migration.plan'].create({
            'name': 'Test ERP Migration Plan',
            'default_error_policy': 'abort_stage',
        })
        self.assertTrue(plan.code.startswith('PLAN-') or plan.code != 'New')

        stage1 = self.env['migration.plan.stage'].create({
            'plan_id': plan.id,
            'name': '01 - Contacts',
            'sequence': 10,
        })
        step1 = self.env['migration.plan.step'].create({
            'stage_id': stage1.id,
            'template_id': self.template_partner.id,
            'sequence': 10,
        })

        self.assertEqual(plan.stage_count, 1)
        self.assertEqual(plan.step_count, 1)

        # Run pre-flight check
        check_action = plan.action_preflight_check()
        self.assertIn('params', check_action)
        self.assertEqual(check_action['params']['type'], 'success')

    def test_02_record_map_relational_lookup(self):
        """Test resolving relational Many2one / Many2many via cross-stage migration.record.map."""
        # 1. Manually create a partner and simulate an entry in migration.record.map
        partner = self.env['res.partner'].create({
            'name': 'Acme Corp Supplier',
            'email': 'acme@test.com',
            'ref': 'SUP-001',
        })
        self.env['migration.record.map'].create({
            'template_id': self.template_partner.id,
            'source_key': 'SUP-001',
            'target_model': 'res.partner',
            'target_id': partner.id,
        })

        # 2. Create a mapping line on product template with lookup_strategy='record_map'
        # Check if product.template has a partner or relation field, or test _resolve_many2one directly
        line = self.env['migration.mapping.line'].create({
            'template_id': self.template_product.id,
            'source_field': 'vendor_code',
            'target_field_id': self.p_name_field.id,  # Any field to test helper
            'lookup_strategy': 'record_map',
        })

        # Mock relation model to res.partner
        resolved_id = line._resolve_from_record_map('SUP-001')
        self.assertEqual(resolved_id, partner.id)

        # Non-existing key should return False
        self.assertFalse(line._resolve_from_record_map('UNKNOWN-KEY'))

    def test_03_plan_execution_engine(self):
        """Test multi-stage execution with mock extraction."""
        plan = self.env['migration.plan'].create({
            'name': 'Full Execution Plan Test',
            'default_error_policy': 'continue_with_warning',
        })
        stage1 = self.env['migration.plan.stage'].create({
            'plan_id': plan.id,
            'name': 'Stage 1: Contacts',
            'sequence': 10,
        })
        step1 = self.env['migration.plan.step'].create({
            'stage_id': stage1.id,
            'template_id': self.template_partner.id,
            'sequence': 10,
        })

        # Mock _fetch_raw_records on connection
        sample_rows = [
            {'code': 'TEST-P01', 'name': 'Partner Alpha', 'email': 'alpha@test.com'},
            {'code': 'TEST-P02', 'name': 'Partner Beta', 'email': 'beta@test.com'},
        ]
        self.conn_partner.write({
            'file_content_cached': json.dumps(sample_rows),
            'source_columns': json.dumps(['code', 'name', 'email']),
        })

        # Execute Live Plan
        run = plan.execute_plan()
        self.assertEqual(run.state, 'done')
        self.assertEqual(plan.state, 'done')

        # Verify partners created
        p1 = self.env['res.partner'].search([('ref', '=', 'TEST-P01')], limit=1)
        self.assertTrue(p1.exists())
        self.assertEqual(p1.name, 'Partner Alpha')

        # Verify cross-reference created
        rec_map = self.env['migration.record.map'].search([
            ('template_id', '=', self.template_partner.id),
            ('source_key', '=', 'TEST-P01'),
        ], limit=1)
        self.assertTrue(rec_map.exists())
        self.assertEqual(rec_map.target_id, p1.id)

    def test_04_dry_run_simulation_rollback(self):
        """Test that dry-run simulation mode completes without modifying database."""
        plan = self.env['migration.plan'].create({
            'name': 'Dry Run Simulation Plan',
            'default_error_policy': 'abort_stage',
        })
        stage = self.env['migration.plan.stage'].create({
            'plan_id': plan.id,
            'name': 'Dry Run Stage',
            'sequence': 10,
        })
        self.env['migration.plan.step'].create({
            'stage_id': stage.id,
            'template_id': self.template_partner.id,
            'sequence': 10,
        })

        sample_rows = [
            {'code': 'DRYRUN-001', 'name': 'Dry Run Partner', 'email': 'dryrun@test.com'},
        ]
        self.conn_partner.write({
            'file_content_cached': json.dumps(sample_rows),
        })

        # Run with dry_run=True
        run = plan.execute_plan(dry_run=True)
        self.assertTrue(run.dry_run)
        self.assertIn(run.state, ('done', 'done_with_errors'))

        # Check partner was NOT committed to DB
        p_dry = self.env['res.partner'].search([('ref', '=', 'DRYRUN-001')], limit=1)
        self.assertFalse(p_dry.exists())

    def test_05_plan_run_wizard(self):
        """Test launch wizard options (single stage execution)."""
        plan = self.env['migration.plan'].create({
            'name': 'Wizard Test Plan',
        })
        stage1 = self.env['migration.plan.stage'].create({
            'plan_id': plan.id,
            'name': 'Stage 1',
            'sequence': 10,
        })
        self.env['migration.plan.step'].create({
            'stage_id': stage1.id,
            'template_id': self.template_partner.id,
            'sequence': 10,
        })

        wizard = self.env['migration.plan.run.wizard'].create({
            'plan_id': plan.id,
            'mode': 'single_stage',
            'stage_id': stage1.id,
            'sample_limit': 10,
        })
        action = wizard.action_start_execution()
        self.assertEqual(action['res_model'], 'migration.plan.run')
        self.assertTrue(action['res_id'])
