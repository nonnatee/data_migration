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
