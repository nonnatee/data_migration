# -*- coding: utf-8 -*-

from odoo.tests import common


class TestDataTransformationTemplate(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env['migration.connection'].create({
            'name': 'Test ETL Preset Connection',
            'connector_type': 'csv',
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

        cls.mapping_line = cls.env['migration.mapping.line'].create({
            'template_id': cls.template.id,
            'source_field': 'phone',
            'target_field_id': cls.phone_field.id,
        })

    def test_preset_creation_and_application(self):
        """Test creating a Transformation Preset and applying it to a mapping line."""
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

        # Apply preset to line
        self.mapping_line.action_apply_preset(preset.id)
        self.assertEqual(len(self.mapping_line.transform_ids), 2)

        # Test line conversion
        res = self.mapping_line.convert_value("  +1 (555) 019-2834  ", {})
        self.assertEqual(res, "+15550192834")

    def test_save_as_preset(self):
        """Test exporting a field mapping line's transforms as a new reusable preset template."""
        self.env['migration.mapping.transform'].create({
            'line_id': self.mapping_line.id,
            'sequence': 10,
            'transform_category': 'slugify',
        })

        new_preset = self.mapping_line.action_save_as_preset("Exported Slug Preset")
        self.assertTrue(new_preset)
        self.assertEqual(new_preset.name, "Exported Slug Preset")
        self.assertEqual(len(new_preset.step_ids), 1)
        self.assertEqual(new_preset.step_ids[0].transform_category, 'slugify')

    def test_new_transform_operations(self):
        """Test Math & Arithmetic, String Slicing, and Slugify transform operations."""
        # 1. Math Add & Round
        t_math = self.env['migration.mapping.transform'].create({
            'line_id': self.mapping_line.id,
            'transform_category': 'math_expr',
            'math_op': 'add',
            'math_operand': 15.5,
        })
        val = t_math.apply_transform("100")
        self.assertEqual(val, 115.5)

        t_math.write({'math_op': 'round', 'math_round_precision': 1})
        self.assertEqual(t_math.apply_transform("123.456"), 123.5)

        # 2. String Slicing (Left)
        t_slice = self.env['migration.mapping.transform'].create({
            'line_id': self.mapping_line.id,
            'transform_category': 'string_slice',
            'slice_mode': 'left',
            'slice_length': 4,
        })
        self.assertEqual(t_slice.apply_transform("ABCD12345"), "ABCD")

        # 3. Slugify
        t_slug = self.env['migration.mapping.transform'].create({
            'line_id': self.mapping_line.id,
            'transform_category': 'slugify',
        })
        self.assertEqual(t_slug.apply_transform("  My Test Product - SKU #123! "), "my_test_product_sku_123")

    def test_convert_value_relational_lookup_fix(self):
        """Verify that convert_value properly evaluates Many2one relational lookups."""
        parent_partner = self.env['res.partner'].create({'name': 'Parent Company Inc'})

        rel_line = self.env['migration.mapping.line'].create({
            'template_id': self.template.id,
            'source_field': 'parent_name',
            'target_field_id': cls.parent_field.id if hasattr(self, 'parent_field') else self.env['ir.model.fields'].search([('model', '=', 'res.partner'), ('name', '=', 'parent_id')], limit=1).id,
            'lookup_strategy': 'field_search',
        })
        # Set lookup field to name
        name_field = self.env['ir.model.fields'].search([('model', '=', 'res.partner'), ('name', '=', 'name')], limit=1)
        rel_line.write({'lookup_field_id': name_field.id})

        res_id = rel_line.convert_value('Parent Company Inc', {})
        self.assertEqual(res_id, parent_partner.id)
