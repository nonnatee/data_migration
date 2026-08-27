# -*- coding: utf-8 -*-

from odoo import fields, models


class MigrationTransformTemplateStep(models.Model):
    _name = 'migration.transform.template.step'
    _description = 'Transformation Preset Step'
    _order = 'sequence asc, id asc'

    template_id = fields.Many2one('migration.transform.template', string='Preset Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)

    transform_category = fields.Selection([
        ('cleansing', 'Data Cleansing & Sanitization'),
        ('date_format', 'Date & Time Formatting'),
        ('unit_conversion', 'Unit Conversion'),
        ('type_conversion', 'Data Type Conversion'),
        ('value_map', 'Value Translation Table'),
        ('math_expr', 'Math & Arithmetic Calculations'),
        ('string_slice', 'String Substring / Split / Slice'),
        ('slugify', 'Code / URL Slugify'),
        ('case_when', 'Conditional Logic (Case-When)'),
        ('python_expr', 'Custom Python Expression'),
        ('ai_prompt', 'AI Natural Language Transformer'),
    ], string='Transformation Category', default='cleansing', required=True)

    # Cleansing
    cleansing_type = fields.Selection([
        ('trim', 'Trim Whitespace'),
        ('upper', 'UPPERCASE'),
        ('lower', 'lowercase'),
        ('title', 'Title Case'),
        ('capitalize', 'Capitalize First Letter'),
        ('pad_left', 'Pad String Left'),
        ('pad_right', 'Pad String Right'),
        ('regex', 'Regex Search & Replace'),
        ('regex_extract', 'Regex Group Extract'),
        ('strip_html', 'Strip HTML Tags'),
        ('strip_non_numeric', 'Strip Non-Numeric Characters'),
        ('strip_non_alphanumeric', 'Strip Non-Alphanumeric Characters'),
        ('handle_null', 'Null / Empty Fallback Default'),
        ('drop_if_null', 'Drop / Skip Record if Null'),
    ], string='Cleansing Operation', default='trim')

    pad_char = fields.Char(string='Pad Character', default='0')
    pad_count = fields.Integer(string='Total Length', default=10)
    regex_pattern = fields.Char(string='Regex Pattern', default='')
    regex_replace = fields.Char(string='Regex Replacement', default='')
    regex_group_index = fields.Integer(string='Regex Group Index', default=1)

    # Date
    input_date_format = fields.Char(string='Input Format Pattern', default='%Y-%m-%d')
    output_date_format = fields.Char(string='Target Format Pattern', default='%Y-%m-%d')
    tz_offset_hours = fields.Float(string='Timezone Offset (Hours)', default=0.0)
    date_math_days = fields.Integer(string='Add/Subtract Days', default=0)

    # Unit
    unit_type = fields.Selection([
        ('mass', 'Weight / Mass (kg, g, lb, oz)'),
        ('length', 'Length / Distance (m, km, ft, in)'),
        ('volume', 'Volume (l, ml, gal)'),
        ('temp', 'Temperature (°C, °F, K)'),
        ('custom', 'Custom Scale Multiplier Ratio'),
    ], string='Unit Category', default='mass')

    source_unit = fields.Selection([
        ('kg', 'Kilogram (kg)'),
        ('g', 'Gram (g)'),
        ('mg', 'Milligram (mg)'),
        ('lb', 'Pound (lb)'),
        ('oz', 'Ounce (oz)'),
        ('m', 'Meter (m)'),
        ('km', 'Kilometer (km)'),
        ('cm', 'Centimeter (cm)'),
        ('mm', 'Millimeter (mm)'),
        ('ft', 'Feet (ft)'),
        ('in', 'Inch (in)'),
        ('mi', 'Mile (mi)'),
        ('l', 'Liter (l)'),
        ('ml', 'Milliliter (ml)'),
        ('gal', 'Gallon (gal)'),
        ('C', 'Celsius (°C)'),
        ('F', 'Fahrenheit (°F)'),
        ('K', 'Kelvin (K)'),
    ], string='Source Unit', default='kg')

    target_unit = fields.Selection([
        ('kg', 'Kilogram (kg)'),
        ('g', 'Gram (g)'),
        ('mg', 'Milligram (mg)'),
        ('lb', 'Pound (lb)'),
        ('oz', 'Ounce (oz)'),
        ('m', 'Meter (m)'),
        ('km', 'Kilometer (km)'),
        ('cm', 'Centimeter (cm)'),
        ('mm', 'Millimeter (mm)'),
        ('ft', 'Feet (ft)'),
        ('in', 'Inch (in)'),
        ('mi', 'Mile (mi)'),
        ('l', 'Liter (l)'),
        ('ml', 'Milliliter (ml)'),
        ('gal', 'Gallon (gal)'),
        ('C', 'Celsius (°C)'),
        ('F', 'Fahrenheit (°F)'),
        ('K', 'Kelvin (K)'),
    ], string='Target Unit', default='lb')

    custom_scale_ratio = fields.Float(string='Scale Ratio Multiplier', default=1.0)

    # Type
    target_type = fields.Selection([
        ('string', 'String / Text'),
        ('integer', 'Integer Number'),
        ('float', 'Float / Decimal Number'),
        ('boolean', 'Boolean (True / False)'),
        ('date', 'Date Object (YYYY-MM-DD)'),
        ('datetime', 'Datetime Object (YYYY-MM-DD HH:MM:SS)'),
        ('json_parse', 'Parse JSON String -> Object'),
        ('json_dump', 'Object -> JSON String'),
        ('base64_encode', 'Base64 Encode'),
        ('base64_decode', 'Base64 Decode'),
    ], string='Target Data Type', default='string')

    value_mapping_json = fields.Text(string='Value Mapping (JSON)', default='{}')
    python_code = fields.Text(string='Python Snippet', default='')
    default_fallback = fields.Char(string='Default Fallback Value')

    # Math
    math_op = fields.Selection([
        ('add', 'Add (+ operand)'),
        ('subtract', 'Subtract (- operand)'),
        ('multiply', 'Multiply (* operand)'),
        ('divide', 'Divide (/ operand)'),
        ('round', 'Round to Precision'),
        ('abs', 'Absolute Value'),
        ('modulo', 'Modulo (% operand)'),
        ('percentage', 'Calculate Percentage (% of operand)'),
    ], string='Math Operation', default='add')
    math_operand = fields.Float(string='Math Operand Value', default=0.0)
    math_round_precision = fields.Integer(string='Round Decimal Digits', default=2)

    # Slicing / Split
    slice_mode = fields.Selection([
        ('slice', 'Start to End Index'),
        ('left', 'First N Characters (Left)'),
        ('right', 'Last N Characters (Right)'),
        ('split', 'Split by Delimiter & Pick Index'),
    ], string='Slice Mode', default='slice')
    slice_start = fields.Integer(string='Start Index', default=0)
    slice_end = fields.Integer(string='End Index', default=10)
    slice_length = fields.Integer(string='Character Count', default=5)
    split_delimiter = fields.Char(string='Split Delimiter', default=',')
    split_index = fields.Integer(string='Pick Token Index', default=0)

    # Case-When
    case_when_json = fields.Text(string='Case-When Rules (JSON)', default='[]')

    # AI
    ai_prompt_template = fields.Text(string='AI Instruction Prompt')
