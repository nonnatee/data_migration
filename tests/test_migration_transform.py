# -*- coding: utf-8 -*-

from odoo.tests import common


class TestMigrationTransform(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env['migration.connection'].create({
            'name': 'Test CSV Connection',
            'conn_type': 'file_csv',
            'source_columns': '["raw_weight", "birth_date", "cust_name", "price_str"]',
        })
        cls.partner_model = cls.env['ir.model'].search([('model', '=', 'res.partner')], limit=1)
        cls.name_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'name')], limit=1)
        
        cls.template = cls.env['migration.template'].create({
            'name': 'Test Split Stage Template',
            'connection_id': cls.connection.id,
            'target_model_id': cls.partner_model.id,
        })

    def test_cleansing_transformation_line(self):
        """Test data cleansing transformation line."""
        tline = self.env['migration.transformation.line'].create({
            'template_id': self.template.id,
            'source_field': 'cust_name',
            'output_field': 'clean_name',
            'transform_category': 'cleansing',
            'cleansing_type': 'trim',
        })
        record = {'cust_name': '  John Doe  '}
        tline.apply_transformation(record)
        self.assertEqual(record['clean_name'], 'John Doe')

        tline.write({'cleansing_type': 'upper'})
        tline.apply_transformation(record)
        self.assertEqual(record['clean_name'], '  JOHN DOE  '.strip())

    def test_derived_unit_conversion(self):
        """Test mass unit conversion deriving a new variable."""
        tline = self.env['migration.transformation.line'].create({
            'template_id': self.template.id,
            'source_field': 'raw_weight',
            'output_field': 'weight_kg',
            'transform_category': 'unit_conversion',
            'unit_type': 'mass',
            'source_unit': 'lb',
            'target_unit': 'kg',
        })
        record = {'raw_weight': '10'}
        tline.apply_transformation(record)
        self.assertAlmostEqual(record['weight_kg'], 4.5359, places=3)
        self.assertEqual(record['raw_weight'], '10')  # Raw column preserved

    def test_split_stage_pipeline_execution(self):
        """Test executing Stage 1 transformations followed by Stage 2 field mappings."""
        # 1. Stage 1 Transformation: Cleanse name
        self.env['migration.transformation.line'].create({
            'template_id': self.template.id,
            'sequence': 10,
            'source_field': 'cust_name',
            'output_field': 'derived_clean_name',
            'transform_category': 'cleansing',
            'cleansing_type': 'title',
        })

        # 2. Stage 2 Mapping: Map derived_clean_name -> res.partner.name
        self.env['migration.mapping.line'].create({
            'template_id': self.template.id,
            'sequence': 10,
            'source_field': 'derived_clean_name',
            'target_field_id': self.name_field.id,
        })

        raw_row = {'cust_name': 'john doe', 'price_str': '99.50'}
        clean_row = self.template._apply_transformation_stage(raw_row)
        self.assertEqual(clean_row['derived_clean_name'], 'John Doe')

        target_vals = self.template._apply_mapping_stage(clean_row)
        self.assertEqual(target_vals['name'], 'John Doe')

    def test_row_filter_transformation(self):
        """Test row filtering logic in transformation stage."""
        # 1. Keep if status is active
        tline = self.env['migration.transformation.line'].create({
            'template_id': self.template.id,
            'source_field': 'cust_name',
            'transform_category': 'filter_row',
            'filter_action': 'keep_if',
            'filter_field': 'status',
            'filter_operator': '=',
            'filter_value': 'active',
        })

        rec_active = {'cust_name': 'Alice', 'status': 'active'}
        res = tline.apply_transformation(rec_active)
        self.assertEqual(res, 'Alice')

        rec_inactive = {'cust_name': 'Bob', 'status': 'inactive'}
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            tline.apply_transformation(rec_inactive)

    def test_conditional_transformation_execution(self):
        """Test conditional execution filter on transformation rules."""
        # Cleanse uppercase only if cust_name contains 'corp'
        tline = self.env['migration.transformation.line'].create({
            'template_id': self.template.id,
            'source_field': 'cust_name',
            'output_field': 'clean_name',
            'transform_category': 'cleansing',
            'cleansing_type': 'upper',
            'apply_filter': True,
            'filter_field': 'cust_name',
            'filter_operator': 'contains',
            'filter_value': 'corp',
        })

        # Matching row -> transformed to uppercase
        rec_match = {'cust_name': 'acme corp'}
        tline.apply_transformation(rec_match)
        self.assertEqual(rec_match['clean_name'], 'ACME CORP')

        # Non-matching row -> filter not satisfied, original value preserved
        rec_non_match = {'cust_name': 'john doe'}
        tline.apply_transformation(rec_non_match)
        self.assertEqual(rec_non_match['clean_name'], 'john doe')

    def test_usage_hint_computation(self):
        """Test usage hints are computed accurately across transformation categories."""
        tline = self.env['migration.transformation.line'].create({
            'template_id': self.template.id,
            'source_field': 'price_str',
            'transform_category': 'cleansing',
            'cleansing_type': 'trim',
        })
        self.assertIn('John Doe', tline.usage_hint)

        tline.write({'transform_category': 'date_format'})
        self.assertIn('%Y-%m-%d', tline.usage_hint)

        tline.write({'transform_category': 'math_expr', 'math_op': 'add'})
        self.assertIn('value + operand', tline.usage_hint)

        tline.write({'transform_category': 'filter_row', 'filter_action': 'keep_if'})
        self.assertIn('Keep record ONLY', tline.usage_hint)
