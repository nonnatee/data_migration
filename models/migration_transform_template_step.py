# -*- coding: utf-8 -*-

from odoo import api, fields, models


class MigrationTransformTemplateStep(models.Model):
    _name = 'migration.transform.template.step'
    _description = 'Transformation Preset Step'
    _order = 'sequence asc, id asc'

    template_id = fields.Many2one('migration.transform.template', string='Preset Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Step Name', compute='_compute_name', store=True, readonly=False)

    transform_category = fields.Selection([
        ('cleansing', 'Data Cleansing & Sanitization'),
        ('filter_row', 'Filter / Drop Records (Row Filter)'),
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

    # Filter & Conditional Settings
    apply_filter = fields.Boolean(string='Apply Filter Condition', default=False)
    filter_field = fields.Char(string='Filter Variable')
    filter_operator = fields.Selection([
        ('=', 'Equals (=)'),
        ('!=', 'Not Equals (!=)'),
        ('>', 'Greater Than (>)'),
        ('<', 'Less Than (<)'),
        ('>=', 'Greater or Equal (>=)'),
        ('<=', 'Less or Equal (<=)'),
        ('contains', 'Contains Substring'),
        ('not_contains', 'Does Not Contain Substring'),
        ('is_null', 'Is Null / Empty'),
        ('is_not_null', 'Is Not Null / Not Empty'),
        ('in', 'In Set (comma-separated: A, B, C)'),
        ('regex', 'Matches Regex Pattern'),
        ('python', 'Python Condition'),
    ], string='Filter Operator', default='=')
    filter_value = fields.Char(string='Filter Target Value')
    filter_action = fields.Selection([
        ('keep_if', 'Keep Record If Condition Met (Drop / Skip otherwise)'),
        ('drop_if', 'Drop / Skip Record If Condition Met (Keep otherwise)'),
    ], string='Filter Action', default='keep_if')

    usage_hint = fields.Char(string='Usage Example & Hint', compute='_compute_usage_hint')

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

    @api.depends(
        'transform_category', 'cleansing_type', 'unit_type', 'source_unit', 'target_unit',
        'target_type', 'math_op', 'slice_mode', 'filter_action', 'filter_operator'
    )
    def _compute_usage_hint(self):
        for rec in self:
            cat = rec.transform_category
            if cat == 'cleansing':
                hints = {
                    'trim': '"John Doe   " ➔ "John Doe" (Removes leading & trailing whitespace)',
                    'upper': '"acme corp" ➔ "ACME CORP" (Converts all characters to uppercase)',
                    'lower': '"User@Company.COM" ➔ "user@company.com" (Standardizes email/text to lowercase)',
                    'title': '"john doe jr" ➔ "John Doe Jr" (Capitalizes first letter of each word)',
                    'capitalize': '"pending review" ➔ "Pending review" (Capitalizes first letter only)',
                    'pad_left': '"42" (pad="0", len=6) ➔ "000042" (Fixed-width invoice / customer codes)',
                    'pad_right': '"SKU" (pad="_", len=8) ➔ "SKU_____" (Appends padding to target length)',
                    'regex': 'Pattern: r"[^\\d+]" Repl: "" ➔ "(555) 123-4567" becomes "5551234567"',
                    'regex_extract': 'Pattern: r"INV-(\\d+)" Group: 1 ➔ Extracts "1002" from "INV-1002-2026"',
                    'strip_html': '"<p><b>Hello</b> World</p>" ➔ "Hello World" (Strips HTML tags & decodes entities)',
                    'strip_non_numeric': '"$1,250.75 USD" ➔ "1250.75" (Keeps only digits and decimal point)',
                    'strip_non_alphanumeric': '"AB#12-34_XY!" ➔ "AB1234XY" (Strips punctuation & symbols)',
                    'handle_null': 'Empty or None ➔ Default fallback value (e.g. "N/A" or "0")',
                    'drop_if_null': 'Empty or None ➔ Drops / skips entire record from ETL load',
                }
                rec.usage_hint = hints.get(rec.cleansing_type, 'Cleanses and sanitizes input data.')
            elif cat == 'filter_row':
                if rec.filter_action == 'keep_if':
                    rec.usage_hint = 'Keep record ONLY if condition is met (e.g. status == "active" or amount > 0); drop otherwise.'
                else:
                    rec.usage_hint = 'Drop / skip record if condition is met (e.g. is_deleted == "1" or country == "TEST"); keep otherwise.'
            elif cat == 'date_format':
                rec.usage_hint = '"25/12/2025" (Input: "%d/%m/%Y", Output: "%Y-%m-%d") ➔ "2025-12-25". Supports tz offset & day offsets.'
            elif cat == 'unit_conversion':
                if rec.unit_type == 'mass':
                    rec.usage_hint = f'Mass conversion ({rec.source_unit} ➔ {rec.target_unit}): e.g. 100 lb ➔ ~45.36 kg'
                elif rec.unit_type == 'length':
                    rec.usage_hint = f'Length conversion ({rec.source_unit} ➔ {rec.target_unit}): e.g. 10 in ➔ 25.4 cm'
                elif rec.unit_type == 'volume':
                    rec.usage_hint = f'Volume conversion ({rec.source_unit} ➔ {rec.target_unit}): e.g. 5 gal ➔ ~18.93 l'
                elif rec.unit_type == 'temp':
                    rec.usage_hint = f'Temperature conversion ({rec.source_unit} ➔ {rec.target_unit}): e.g. 98.6 °F ➔ 37.0 °C'
                else:
                    rec.usage_hint = 'Multiplier ratio: Value * Scale Ratio (e.g. 100 * 1.07 = 107.0 for VAT/markup)'
            elif cat == 'type_conversion':
                hints = {
                    'string': '123 ➔ "123" (Casts number/object to text string)',
                    'integer': '"123.45" ➔ 123 (Casts to integer whole number)',
                    'float': '"$1250.50" ➔ 1250.50 (Casts to floating point decimal)',
                    'boolean': '"yes", "1", "true", "active" ➔ True; others ➔ False',
                    'date': '"2026-08-29 15:30:00" ➔ "2026-08-29" (Extracts ISO date portion)',
                    'datetime': '"2026-08-29" ➔ "2026-08-29 00:00:00" (Expands date to timestamp)',
                    'json_parse': '\'{"key": "val"}\' ➔ Python dictionary object',
                    'json_dump': 'Dictionary / List ➔ JSON string representation',
                    'base64_encode': '"hello" ➔ "aGVsbG8=" (Encodes text/binary for attachments)',
                    'base64_decode': '"aGVsbG8=" ➔ "hello" (Decodes base64 string back to text)',
                }
                rec.usage_hint = hints.get(rec.target_type, 'Casts variable to target data type.')
            elif cat == 'value_map':
                rec.usage_hint = 'JSON: {"M": "Male", "F": "Female", "O": "Other"} ➔ Translates legacy codes to standard values.'
            elif cat == 'math_expr':
                hints = {
                    'add': 'value + operand (e.g. 100 + 15 = 115)',
                    'subtract': 'value - operand (e.g. 100 - 20 = 80)',
                    'multiply': 'value * operand (e.g. qty * unit_price)',
                    'divide': 'value / operand (e.g. total / 12 = monthly_installment)',
                    'round': 'round(value, precision) (e.g. 12.3456 with precision 2 ➔ 12.35)',
                    'modulo': 'value % operand (e.g. 10 % 3 = 1)',
                    'percentage': '(value / 100.0) * operand (e.g. 10% discount on 250 = 25.0)',
                    'abs': 'abs(value) (e.g. -45.5 ➔ 45.5)',
                }
                rec.usage_hint = hints.get(rec.math_op, 'Applies arithmetic calculation to variable.')
            elif cat == 'string_slice':
                hints = {
                    'slice': 'Start 0, End 4 on "2026-Q1" ➔ "2026" (Character index substring)',
                    'left': 'Length 3 on "DE12345" ➔ "DE" (First N characters from left)',
                    'right': 'Length 4 on "ABC1234" ➔ "1234" (Last N characters from right)',
                    'split': 'Delimiter "-" Index 1 on "INV-2026-001" ➔ "2026" (Token split)',
                }
                rec.usage_hint = hints.get(rec.slice_mode, 'Extracts substring or splits variable.')
            elif cat == 'slugify':
                rec.usage_hint = '"Apple iPhone 15 Pro (128GB)!" ➔ "apple_iphone_15_pro_128gb" (URL/XML-ID safe slug)'
            elif cat == 'case_when':
                rec.usage_hint = 'JSON: [{"when": "VIP", "then": 0.20}, {"when": "STD", "then": 0.05}] ➔ Multi-branch logic'
            elif cat == 'python_expr':
                rec.usage_hint = 'value.strip().lower() if value else default or record.get("qty", 0) * record.get("price", 0)'
            elif cat == 'ai_prompt':
                rec.usage_hint = '"Extract province from Thai address: {value}" or "Categorize product into category: {value}"'
            else:
                rec.usage_hint = 'Transform input variable for migration mapping.'

    @api.depends('transform_category', 'cleansing_type', 'unit_type', 'target_type', 'math_op', 'filter_action')
    def _compute_name(self):
        for rec in self:
            cat = rec.transform_category
            if cat == 'cleansing':
                rec.name = dict(rec._fields['cleansing_type'].selection).get(rec.cleansing_type, 'Cleanse')
            elif cat == 'filter_row':
                action = "Keep if" if rec.filter_action == 'keep_if' else "Drop if"
                rec.name = f"Row Filter: {action} {rec.filter_field or ''} {rec.filter_operator} {rec.filter_value or ''}"
            elif cat == 'unit_conversion':
                rec.name = f"Convert {rec.source_unit} -> {rec.target_unit}"
            elif cat == 'type_conversion':
                rec.name = f"Cast to {rec.target_type}"
            elif cat == 'math_expr':
                rec.name = f"Math: {rec.math_op}"
            elif cat == 'date_format':
                rec.name = f"Date: {rec.output_date_format}"
            elif cat == 'slugify':
                rec.name = "Slugify"
            elif cat == 'case_when':
                rec.name = "Case-When Rules"
            elif cat == 'ai_prompt':
                rec.name = "AI Transformer"
            elif cat == 'python_expr':
                rec.name = "Python Snippet"
            else:
                rec.name = dict(rec._fields['transform_category'].selection).get(cat, 'Transform')
