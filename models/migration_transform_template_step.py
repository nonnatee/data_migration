# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class MigrationTransformTemplateStep(models.Model):
    _name = 'migration.transform.template.step'
    _description = 'Transformation Step Preset Template'
    _order = 'sequence asc, id asc'

    sequence = fields.Integer(string='Sequence', default=10)
    template_id = fields.Many2one('migration.transform.template', string='Transformation Preset Template', required=True, ondelete='cascade')

    transform_category = fields.Selection([
        ('cleansing', 'Data Cleansing'),
        ('date_format', 'Date & Time Formatting'),
        ('unit_conversion', 'Unit Conversion'),
        ('type_conversion', 'Data Type Conversion'),
        ('value_map', 'Value Mapping Table'),
        ('math_expr', 'Math & Arithmetic'),
        ('string_slice', 'String Substring / Slice'),
        ('slugify', 'URL / Code Slugify'),
        ('python_expr', 'Python Expression'),
    ], string='Transformation Category', default='cleansing', required=True)

    # 1. Data Cleansing Options
    cleansing_type = fields.Selection([
        ('trim', 'Trim Whitespace'),
        ('upper', 'UPPERCASE'),
        ('lower', 'lowercase'),
        ('title', 'Title Case'),
        ('capitalize', 'Capitalize First Letter'),
        ('pad_left', 'Pad String Left'),
        ('pad_right', 'Pad String Right'),
        ('regex', 'Regex Search & Replace'),
        ('strip_html', 'Strip HTML Tags'),
        ('strip_non_numeric', 'Strip Non-Numeric Characters'),
    ], string='Cleansing Operation', default='trim')

    pad_char = fields.Char(string='Pad Character', default='0')
    pad_count = fields.Integer(string='Total Length', default=10)
    regex_pattern = fields.Char(string='Regex Pattern', default=r'[^\w\s]')
    regex_replace = fields.Char(string='Regex Replacement', default='')

    # 2. Date Formatting Options
    input_date_format = fields.Char(string='Input Format Pattern', default='%Y-%m-%d')
    output_date_format = fields.Char(string='Target Format Pattern', default='%Y-%m-%d')
    tz_offset_hours = fields.Float(string='Timezone Offset (Hours)', default=0.0)

    # 3. Unit Conversion Options
    unit_type = fields.Selection([
        ('mass', 'Weight / Mass (kg, g, lb, oz)'),
        ('length', 'Length / Distance (m, km, ft, in)'),
        ('volume', 'Volume (l, ml, gal)'),
        ('temp', 'Temperature (C, F, K)'),
        ('custom', 'Custom Scale Multiplier'),
    ], string='Unit Category', default='mass')

    source_unit = fields.Selection([
        ('kg', 'Kilogram (kg)'), ('g', 'Gram (g)'), ('mg', 'Milligram (mg)'), ('lb', 'Pound (lb)'), ('oz', 'Ounce (oz)'),
        ('m', 'Meter (m)'), ('km', 'Kilometer (km)'), ('cm', 'Centimeter (cm)'), ('mm', 'Millimeter (mm)'), ('ft', 'Feet (ft)'), ('in', 'Inch (in)'), ('mi', 'Mile (mi)'),
        ('l', 'Liter (l)'), ('ml', 'Milliliter (ml)'), ('gal', 'Gallon (gal)'),
        ('C', 'Celsius (°C)'), ('F', 'Fahrenheit (°F)'), ('K', 'Kelvin (K)'),
    ], string='Source Unit', default='kg')

    target_unit = fields.Selection([
        ('kg', 'Kilogram (kg)'), ('g', 'Gram (g)'), ('mg', 'Milligram (mg)'), ('lb', 'Pound (lb)'), ('oz', 'Ounce (oz)'),
        ('m', 'Meter (m)'), ('km', 'Kilometer (km)'), ('cm', 'Centimeter (cm)'), ('mm', 'Millimeter (mm)'), ('ft', 'Feet (ft)'), ('in', 'Inch (in)'), ('mi', 'Mile (mi)'),
        ('l', 'Liter (l)'), ('ml', 'Milliliter (ml)'), ('gal', 'Gallon (gal)'),
        ('C', 'Celsius (°C)'), ('F', 'Fahrenheit (°F)'), ('K', 'Kelvin (K)'),
    ], string='Target Unit', default='lb')

    custom_scale_ratio = fields.Float(string='Scale Ratio Multiplier', default=1.0)

    # 4. Type Conversion Options
    target_type = fields.Selection([
        ('string', 'String / Text'),
        ('integer', 'Integer Number'),
        ('float', 'Float / Decimal Number'),
        ('boolean', 'Boolean (True/False)'),
        ('date', 'Date Object'),
        ('datetime', 'Datetime Object'),
    ], string='Target Data Type', default='string')

    # 5. Value Map & Python Snippet
    value_mapping_json = fields.Text(string='Value Mapping (JSON)', default='{"raw_val": "target_val"}')
    python_code = fields.Text(string='Python Snippet', default='value.strip().title() if value else default')
    default_fallback = fields.Char(string='Default Fallback Value')

    # 6. Math Expressions
    math_op = fields.Selection([
        ('add', 'Add (+ operand)'),
        ('subtract', 'Subtract (- operand)'),
        ('multiply', 'Multiply (* operand)'),
        ('divide', 'Divide (/ operand)'),
        ('round', 'Round to Precision'),
        ('abs', 'Absolute Value'),
    ], string='Math Operation', default='add')
    math_operand = fields.Float(string='Math Operand Value', default=0.0)
    math_round_precision = fields.Integer(string='Round Decimal Digits', default=2)

    # 7. Substring / Slicing
    slice_mode = fields.Selection([
        ('slice', 'Start to End Index'),
        ('left', 'First N Characters (Left)'),
        ('right', 'Last N Characters (Right)'),
    ], string='Slice Mode', default='slice')
    slice_start = fields.Integer(string='Start Index', default=0)
    slice_end = fields.Integer(string='End Index', default=10)
    slice_length = fields.Integer(string='Character Count', default=5)

    name = fields.Char(string='Step Summary', compute='_compute_name', store=True)

    @api.depends('transform_category', 'cleansing_type', 'unit_type', 'math_op', 'slice_mode')
    def _compute_name(self):
        for rec in self:
            if rec.transform_category == 'cleansing':
                rec.name = f"Cleanse: {rec.cleansing_type}"
            elif rec.transform_category == 'date_format':
                rec.name = f"Date Format ({rec.input_date_format} -> {rec.output_date_format})"
            elif rec.transform_category == 'math_expr':
                rec.name = f"Math: {rec.math_op}"
            elif rec.transform_category == 'string_slice':
                rec.name = f"Slice: {rec.slice_mode}"
            elif rec.transform_category == 'slugify':
                rec.name = "Slugify text"
            else:
                rec.name = f"Step ({rec.transform_category})"
