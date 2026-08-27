# -*- coding: utf-8 -*-

from odoo.tests import common


class TestMigrationTransform(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env['migration.connection'].create({
            'name': 'Test CSV Connection',
            'conn_type': 'file_csv',
            'source_columns': '["Weight", "BirthDate", "ProductName", "Price"]',
        })
        cls.partner_model = cls.env['ir.model'].search([('model', '=', 'res.partner')], limit=1)
        cls.name_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'name')], limit=1)
        
        cls.template = cls.env['migration.template'].create({
            'name': 'Test Template',
            'connection_id': cls.connection.id,
            'target_model_id': cls.partner_model.id,
        })

        cls.mapping_line = cls.env['migration.mapping.line'].create({
            'template_id': cls.template.id,
            'source_field': 'Weight',
            'target_field_id': cls.name_field.id,
        })

    def test_cleansing_operations(self):
        """Test data cleansing transformations."""
        transform = self.env['migration.mapping.transform'].create({
            'line_id': self.mapping_line.id,
            'transform_category': 'cleansing',
            'cleansing_type': 'trim',
        })
        res = transform.apply_transform("  hello world  ")
        self.assertEqual(res, "hello world")

        transform.write({'cleansing_type': 'upper'})
        self.assertEqual(transform.apply_transform("hello world"), "HELLO WORLD")

        transform.write({'cleansing_type': 'pad_left', 'pad_char': '0', 'pad_count': 6})
        self.assertEqual(transform.apply_transform("123"), "000123")

    def test_unit_conversions(self):
        """Test mass, length, volume, and temp unit conversions."""
        # 1. Mass kg -> lb (1 kg = ~2.20462 lb)
        t_mass = self.env['migration.mapping.transform'].create({
            'line_id': self.mapping_line.id,
            'transform_category': 'unit_conversion',
            'unit_type': 'mass',
            'source_unit': 'kg',
            'target_unit': 'lb',
        })
        lbs = t_mass.apply_transform("10 kg")
        self.assertAlmostEqual(lbs, 22.0462, places=3)

        # 2. Temp C -> F (100 C = 212 F)
        t_temp = self.env['migration.mapping.transform'].create({
            'line_id': self.mapping_line.id,
            'transform_category': 'unit_conversion',
            'unit_type': 'temp',
            'source_unit': 'C',
            'target_unit': 'F',
        })
        f = t_temp.apply_transform(100)
        self.assertEqual(f, 212.0)

    def test_date_formatting(self):
        """Test parsing date input and converting format."""
        t_date = self.env['migration.mapping.transform'].create({
            'line_id': self.mapping_line.id,
            'transform_category': 'date_format',
            'input_date_format': '%Y-%m-%d',
            'output_date_format': '%d/%m/%Y',
        })
        formatted = t_date.apply_transform("2026-07-31")
        self.assertEqual(formatted, "31/07/2026")

    def test_multi_step_pipeline(self):
        """Test chaining multiple transform steps sequentially."""
        # Step 1: Cleanse (Trim)
        self.env['migration.mapping.transform'].create({
            'sequence': 10,
            'line_id': self.mapping_line.id,
            'transform_category': 'cleansing',
            'cleansing_type': 'trim',
        })
        # Step 2: Unit conversion (kg -> lb)
        self.env['migration.mapping.transform'].create({
            'sequence': 20,
            'line_id': self.mapping_line.id,
            'transform_category': 'unit_conversion',
            'unit_type': 'mass',
            'source_unit': 'kg',
            'target_unit': 'lb',
        })
        # Step 3: Type conversion to Float
        self.env['migration.mapping.transform'].create({
            'sequence': 30,
            'line_id': self.mapping_line.id,
            'transform_category': 'type_conversion',
            'target_type': 'float',
        })

        test_res = self.mapping_line.action_test_pipeline("   5 kg   ")
        self.assertAlmostEqual(test_res['final_output'], 11.023, places=2)
        self.assertEqual(len(test_res['traces']), 3)
