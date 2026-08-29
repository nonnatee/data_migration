# -*- coding: utf-8 -*-

from odoo.tests import common


class TestDataTransformationTemplate(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env['migration.connection'].create({
            'name': 'Test ETL Preset Connection',
            'conn_type': 'file_csv',
            'source_columns': '["name", "code", "phone", "price", "weight"]',
        })
        cls.partner_model = cls.env['ir.model'].search([('model', '=', 'res.partner')], limit=1)
        cls.name_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'name')], limit=1)
        cls.phone_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'phone')], limit=1)
        cls.parent_field = cls.env['ir.model.fields'].search([('model_id', '=', cls.partner_model.id), ('name', '=', 'parent_id')], limit=1)

        cls.template = cls.env['migration.template'].create({
            'name': 'Test Transformation Preset Template',
            'connection_id': cls.connection.id,
            'target_model_id': cls.partner_model.id,
        })

    def test_preset_creation_and_application(self):
        """Test creating a Transformation Preset and applying it to a template."""
        preset = self.env['migration.transform.template'].create({
            'name': 'Test Phone Sanitizer',
            'category': 'cleansing',
        })
        self.env['migration.transform.template.step'].create({
            'template_id': preset.id,
            'sequence': 10,
            'transform_category': 'cleansing',
            'cleansing_type': 'trim',
        })
        self.env['migration.transform.template.step'].create({
            'template_id': preset.id,
            'sequence': 20,
            'transform_category': 'cleansing',
            'cleansing_type': 'regex',
            'regex_pattern': r'[^\d+]',
            'regex_replace': '',
        })

        # Apply preset to template
        lines = preset.action_apply_to_template(self.template, 'phone', 'clean_phone')
        self.assertEqual(len(lines), 2)

        # Test execution
        rec = {'phone': '  +1 (555) 019-2834  '}
        for l in lines:
            l.apply_transformation(rec)
        self.assertEqual(rec['clean_phone'], '+15550192834')

    def test_new_transform_operations(self):
        """Test Math & Arithmetic, String Slicing, and Slugify transform operations."""
        # 1. Math Add & Round
        t_math = self.env['migration.transformation.line'].create({
            'template_id': self.template.id,
            'source_field': 'price',
            'output_field': 'price_calc',
            'transform_category': 'math_expr',
            'math_op': 'add',
            'math_operand': 15.5,
        })
        r_math = {'price': '100'}
        t_math.apply_transformation(r_math)
        self.assertEqual(r_math['price_calc'], 115.5)

        # 2. String Slicing (Left)
        t_slice = self.env['migration.transformation.line'].create({
            'template_id': self.template.id,
            'source_field': 'code',
            'output_field': 'short_code',
            'transform_category': 'string_slice',
            'slice_mode': 'left',
            'slice_length': 4,
        })
        r_slice = {'code': 'ABCD12345'}
        t_slice.apply_transformation(r_slice)
        self.assertEqual(r_slice['short_code'], 'ABCD')

        # 3. Slugify
        t_slug = self.env['migration.transformation.line'].create({
            'template_id': self.template.id,
            'source_field': 'name',
            'output_field': 'slug_name',
            'transform_category': 'slugify',
        })
        r_slug = {'name': '  My Test Product - SKU #123! '}
        t_slug.apply_transformation(r_slug)
        self.assertEqual(r_slug['slug_name'], 'my_test_product_sku_123')

    def test_relational_lookup_resolution(self):
        """Verify that resolve_value properly evaluates Many2one relational lookups."""
        parent_partner = self.env['res.partner'].create({'name': 'Parent Company Inc'})

        name_field = self.env['ir.model.fields'].search([('model', '=', 'res.partner'), ('name', '=', 'name')], limit=1)
        rel_line = self.env['migration.mapping.line'].create({
            'template_id': self.template.id,
            'source_field': 'parent_name',
            'target_field_id': self.parent_field.id,
            'lookup_strategy': 'field_search',
            'lookup_field_id': name_field.id,
        })

        res_id = rel_line.resolve_value({'parent_name': 'Parent Company Inc'})
        self.assertEqual(res_id, parent_partner.id)

    def test_preset_with_filter_step(self):
        """Verify that presets can include row filter steps and copy them to templates."""
        preset = self.env['migration.transform.template'].create({
            'name': 'Filter Active & Trim',
            'category': 'cleansing',
        })
        self.env['migration.transform.template.step'].create({
            'template_id': preset.id,
            'sequence': 10,
            'transform_category': 'filter_row',
            'filter_action': 'keep_if',
            'filter_operator': '=',
            'filter_value': 'true',
        })
        self.env['migration.transform.template.step'].create({
            'template_id': preset.id,
            'sequence': 20,
            'transform_category': 'cleansing',
            'cleansing_type': 'trim',
        })

        lines = preset.action_apply_to_template(self.template, 'code', 'clean_code')
        self.assertEqual(len(lines), 2)
        filter_line = lines.filtered(lambda l: l.transform_category == 'filter_row')
        self.assertTrue(filter_line)
        self.assertEqual(filter_line.filter_operator, '=')
        self.assertEqual(filter_line.filter_value, 'true')
