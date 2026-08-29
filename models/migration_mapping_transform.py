# -*- coding: utf-8 -*-

import base64
import datetime
import json
import logging
import math
import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Unit conversion reference ratios to base units
MASS_TO_KG = {
    'kg': 1.0,
    'g': 0.001,
    'mg': 0.000001,
    'lb': 0.45359237,
    'oz': 0.028349523125,
}

LENGTH_TO_M = {
    'm': 1.0,
    'km': 1000.0,
    'cm': 0.01,
    'mm': 0.001,
    'ft': 0.3048,
    'in': 0.0254,
    'mi': 1609.344,
}

VOLUME_TO_L = {
    'l': 1.0,
    'ml': 0.001,
    'gal': 3.78541,
}


class MigrationMappingTransform(models.Model):
    _name = 'migration.mapping.transform'
    _description = 'Mapping Transformation Step'
    _order = 'sequence asc, id asc'

    sequence = fields.Integer(string='Sequence', default=10)
    line_id = fields.Many2one('migration.mapping.line', string='Field Mapping Line', required=True, ondelete='cascade')
    
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

    # Filter & Conditional Options
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
        ('regex_extract', 'Regex Group Extract'),
        ('strip_html', 'Strip HTML Tags'),
        ('strip_non_numeric', 'Strip Non-Numeric Characters'),
        ('strip_non_alphanumeric', 'Strip Non-Alphanumeric Characters'),
        ('handle_null', 'Null / Empty Fallback Default'),
        ('drop_if_null', 'Drop / Skip Record if Null'),
    ], string='Cleansing Operation', default='trim')
    
    pad_char = fields.Char(string='Pad Character', default='0')
    pad_count = fields.Integer(string='Total Length', default=10)
    regex_pattern = fields.Char(string='Regex Pattern', default=r'[^\w\s]')
    regex_replace = fields.Char(string='Regex Replacement', default='')
    regex_group_index = fields.Integer(string='Regex Group Index', default=1)

    # 2. Date Formatting Options
    input_date_format = fields.Char(string='Input Format Pattern', default='%Y-%m-%d',
                                    help='e.g. %Y-%m-%d, %d/%m/%Y, %Y-%m-%d %H:%M:%S, timestamp, or auto')
    output_date_format = fields.Char(string='Target Format Pattern', default='%Y-%m-%d', help='Target strftime pattern e.g. %Y-%m-%d %H:%M:%S')
    tz_offset_hours = fields.Float(string='Timezone Offset (Hours)', default=0.0, help='e.g. +7.0 for UTC+7')
    date_math_days = fields.Integer(string='Add/Subtract Days', default=0)

    # 3. Unit Conversion Options
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

    # 4. Type Conversion Options
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
        ('modulo', 'Modulo (% operand)'),
        ('percentage', 'Calculate Percentage (% of operand)'),
    ], string='Math Operation', default='add')
    math_operand = fields.Float(string='Math Operand Value', default=0.0)
    math_round_precision = fields.Integer(string='Round Decimal Digits', default=2)

    # 7. Substring / Slicing / Split
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

    # 8. Conditional Logic (Case-When)
    case_when_json = fields.Text(
        string='Case-When Rules (JSON)',
        default='[{"condition": "value == \'A\'", "result": "Option Alpha"}, {"condition": "True", "result": "Default"}]'
    )

    # 9. AI Integration Options
    ai_config_id = fields.Many2one('migration.ai.config', string='AI Provider', help='Leave empty to use default AI provider.')
    ai_prompt_template = fields.Text(
        string='AI Instruction Prompt',
        default="Extract and standardize the city/province name from the given address: '{value}'"
    )

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

    @api.depends('transform_category', 'cleansing_type', 'unit_type', 'source_unit', 'target_unit',
                 'input_date_format', 'output_date_format', 'target_type', 'math_op', 'slice_mode', 'filter_action', 'ai_prompt_template')
    def _compute_name(self):
        for rec in self:
            if rec.transform_category == 'cleansing':
                rec.name = f"Cleanse: {dict(rec._fields['cleansing_type'].selection).get(rec.cleansing_type, rec.cleansing_type)}"
            elif rec.transform_category == 'filter_row':
                action = "Keep if" if rec.filter_action == 'keep_if' else "Drop if"
                rec.name = f"Row Filter: {action} {rec.filter_field or (rec.line_id and rec.line_id.source_field) or ''} {rec.filter_operator} {rec.filter_value or ''}"
            elif rec.transform_category == 'date_format':
                rec.name = f"Date Format ({rec.input_date_format} -> {rec.output_date_format})"
            elif rec.transform_category == 'unit_conversion':
                if rec.unit_type == 'custom':
                    rec.name = f"Unit Scale (x{rec.custom_scale_ratio})"
                else:
                    rec.name = f"Unit Conv ({rec.source_unit} -> {rec.target_unit})"
            elif rec.transform_category == 'type_conversion':
                rec.name = f"Cast: {dict(rec._fields['target_type'].selection).get(rec.target_type, rec.target_type)}"
            elif rec.transform_category == 'value_map':
                rec.name = "Value Map Lookup"
            elif rec.transform_category == 'math_expr':
                rec.name = f"Math: {dict(rec._fields['math_op'].selection).get(rec.math_op, rec.math_op)}"
            elif rec.transform_category == 'string_slice':
                rec.name = f"Slice ({rec.slice_mode})"
            elif rec.transform_category == 'slugify':
                rec.name = "Slugify text"
            elif rec.transform_category == 'case_when':
                rec.name = "Case-When Branching"
            elif rec.transform_category == 'python_expr':
                rec.name = "Python Expression"
            elif rec.transform_category == 'ai_prompt':
                rec.name = f"AI Prompt: {rec.ai_prompt_template[:30]}..." if rec.ai_prompt_template else "AI Prompt"
            else:
                rec.name = "Transform Step"

    def _eval_condition(self, record_ctx):
        """Evaluates whether record_ctx satisfies this transform step's filter condition."""
        self.ensure_one()
        f_field = self.filter_field or (self.line_id and self.line_id.source_field) or ''
        raw_val = record_ctx.get(f_field) if record_ctx else None
        op = self.filter_operator or '='
        target = self.filter_value or ''

        if op == 'is_null':
            return raw_val is None or str(raw_val).strip() == ''
        elif op == 'is_not_null':
            return raw_val is not None and str(raw_val).strip() != ''

        s_val = '' if raw_val is None else str(raw_val).strip()

        if op == 'python':
            eval_ctx = {
                'value': raw_val,
                'record': record_ctx or {},
                're': re,
                'datetime': datetime,
                'math': math,
                'json': json,
            }
            try:
                return bool(eval(target, eval_ctx))
            except Exception as e:
                _logger.warning("Python filter condition error on field '%s': %s", f_field, e)
                return False

        if op == 'contains':
            return target.lower() in s_val.lower()
        elif op == 'not_contains':
            return target.lower() not in s_val.lower()
        elif op == 'in':
            items = [i.strip().lower() for i in target.split(',') if i.strip()]
            return s_val.lower() in items
        elif op == 'regex':
            try:
                return bool(re.search(target, s_val, re.IGNORECASE))
            except Exception:
                return False

        try:
            num_val = float(re.sub(r'[^\d.-]', '', s_val)) if s_val else 0.0
            num_target = float(re.sub(r'[^\d.-]', '', target)) if target else 0.0
            if op == '=':
                return s_val.lower() == target.lower() or num_val == num_target
            elif op == '!=':
                return s_val.lower() != target.lower() and num_val != num_target
            elif op == '>':
                return num_val > num_target
            elif op == '<':
                return num_val < num_target
            elif op == '>=':
                return num_val >= num_target
            elif op == '<=':
                return num_val <= num_target
        except Exception:
            if op == '=':
                return s_val.lower() == target.lower()
            elif op == '!=':
                return s_val.lower() != target.lower()
            elif op == '>':
                return s_val > target
            elif op == '<':
                return s_val < target
            elif op == '>=':
                return s_val >= target
            elif op == '<=':
                return s_val <= target

        return True

    def apply_transform(self, val, record_ctx=None):
        """Applies transformation step logic to input value."""
        self.ensure_one()

        # 1. Row Filter Category
        if self.transform_category == 'filter_row':
            matched = self._eval_condition(record_ctx or {})
            if self.filter_action == 'keep_if' and not matched:
                raise UserError("__DROP_ROW_FILTER__")
            elif self.filter_action == 'drop_if' and matched:
                raise UserError("__DROP_ROW_FILTER__")
            return val

        # 2. Conditional Transform Filter
        if self.apply_filter:
            matched = self._eval_condition(record_ctx or {})
            if not matched:
                return val

        if val is None or (isinstance(val, str) and val.strip() == ''):
            if self.transform_category == 'cleansing' and self.cleansing_type == 'handle_null':
                return self.default_fallback or ''
            elif self.transform_category == 'cleansing' and self.cleansing_type == 'drop_if_null':
                raise UserError("__DROP_ROW_NULL__")
            val = self.default_fallback or ''

        # 1. Data Cleansing
        if self.transform_category == 'cleansing':
            str_val = str(val)
            op = self.cleansing_type
            if op == 'trim':
                return str_val.strip()
            elif op == 'upper':
                return str_val.upper()
            elif op == 'lower':
                return str_val.lower()
            elif op == 'title':
                return str_val.title()
            elif op == 'capitalize':
                return str_val.capitalize()
            elif op == 'pad_left':
                char = self.pad_char or '0'
                return str_val.rjust(self.pad_count, char)
            elif op == 'pad_right':
                char = self.pad_char or ' '
                return str_val.ljust(self.pad_count, char)
            elif op == 'regex':
                pat = self.regex_pattern or ''
                repl = self.regex_replace or ''
                return re.sub(pat, repl, str_val) if pat else str_val
            elif op == 'regex_extract':
                pat = self.regex_pattern or ''
                grp = self.regex_group_index or 1
                m = re.search(pat, str_val)
                if m:
                    try:
                        return m.group(grp)
                    except IndexError:
                        return m.group(0)
                return self.default_fallback or ''
            elif op == 'strip_html':
                return re.sub(r'<[^>]*>', '', str_val)
            elif op == 'strip_non_numeric':
                return re.sub(r'[^\d.-]', '', str_val)
            elif op == 'strip_non_alphanumeric':
                return re.sub(r'[^\w\s]', '', str_val)
            elif op == 'handle_null':
                return self.default_fallback or str_val
            elif op == 'drop_if_null':
                if not str_val.strip():
                    raise UserError("__DROP_ROW_NULL__")
                return str_val

        # 2. Date Formatting
        elif self.transform_category == 'date_format':
            if not val:
                return self.default_fallback or False
            str_val = str(val).strip()
            dt_obj = None

            # Try parsing timestamp
            if str_val.isdigit() or (str_val.replace('.', '', 1).isdigit() and str_val.count('.') == 1):
                try:
                    dt_obj = datetime.datetime.fromtimestamp(float(str_val))
                except Exception:
                    dt_obj = None

            if not dt_obj:
                patterns = [self.input_date_format, '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y%m%d', '%Y/%m/%d']
                for fmt in patterns:
                    if not fmt or fmt == 'auto':
                        continue
                    try:
                        dt_obj = datetime.datetime.strptime(str_val, fmt)
                        break
                    except ValueError:
                        continue

            if not dt_obj:
                _logger.warning("Failed to parse date '%s' using pattern '%s'", str_val, self.input_date_format)
                return self.default_fallback or str_val

            if self.tz_offset_hours:
                dt_obj += datetime.timedelta(hours=self.tz_offset_hours)
            if self.date_math_days:
                dt_obj += datetime.timedelta(days=self.date_math_days)

            out_fmt = self.output_date_format or '%Y-%m-%d'
            return dt_obj.strftime(out_fmt)

        # 3. Unit Conversion
        elif self.transform_category == 'unit_conversion':
            try:
                num_val = float(re.sub(r'[^\d.-]', '', str(val)))
            except Exception:
                return val

            if self.unit_type == 'custom':
                return num_val * (self.custom_scale_ratio or 1.0)

            s_unit = self.source_unit
            t_unit = self.target_unit

            if self.unit_type == 'mass':
                if s_unit in MASS_TO_KG and t_unit in MASS_TO_KG:
                    base_kg = num_val * MASS_TO_KG[s_unit]
                    return base_kg / MASS_TO_KG[t_unit]

            elif self.unit_type == 'length':
                if s_unit in LENGTH_TO_M and t_unit in LENGTH_TO_M:
                    base_m = num_val * LENGTH_TO_M[s_unit]
                    return base_m / LENGTH_TO_M[t_unit]

            elif self.unit_type == 'volume':
                if s_unit in VOLUME_TO_L and t_unit in VOLUME_TO_L:
                    base_l = num_val * VOLUME_TO_L[s_unit]
                    return base_l / VOLUME_TO_L[t_unit]

            elif self.unit_type == 'temp':
                if s_unit == 'C':
                    c_val = num_val
                elif s_unit == 'F':
                    c_val = (num_val - 32.0) * (5.0 / 9.0)
                elif s_unit == 'K':
                    c_val = num_val - 273.15
                else:
                    c_val = num_val

                if t_unit == 'C':
                    return c_val
                elif t_unit == 'F':
                    return (c_val * 9.0 / 5.0) + 32.0
                elif t_unit == 'K':
                    return c_val + 273.15

            return num_val

        # 4. Type Conversion
        elif self.transform_category == 'type_conversion':
            ttype = self.target_type
            if ttype == 'string':
                return str(val) if val is not None else ''
            elif ttype == 'integer':
                try:
                    return int(float(str(val).strip()))
                except Exception:
                    return 0
            elif ttype == 'float':
                try:
                    return float(str(val).strip())
                except Exception:
                    return 0.0
            elif ttype == 'boolean':
                if isinstance(val, bool):
                    return val
                return str(val).lower() in ('true', '1', 'yes', 't', 'y', 'on', 'active')
            elif ttype in ('date', 'datetime'):
                return str(val)
            elif ttype == 'json_parse':
                try:
                    return json.loads(str(val))
                except Exception:
                    return val
            elif ttype == 'json_dump':
                return json.dumps(val, default=str)
            elif ttype == 'base64_encode':
                return base64.b64encode(str(val).encode('utf-8')).decode('utf-8')
            elif ttype == 'base64_decode':
                try:
                    return base64.b64decode(str(val)).decode('utf-8')
                except Exception:
                    return val

        # 5. Value Mapping Table
        elif self.transform_category == 'value_map':
            if not self.value_mapping_json:
                return val
            try:
                dict_map = json.loads(self.value_mapping_json)
                return dict_map.get(str(val), dict_map.get(val, self.default_fallback or val))
            except Exception as e:
                _logger.warning("Error parsing value mapping JSON: %s", e)
                return val

        # 6. Math & Arithmetic
        elif self.transform_category == 'math_expr':
            try:
                num_val = float(str(val).strip())
            except Exception:
                return val

            op = self.math_op
            operand = self.math_operand or 0.0

            if op == 'add':
                return num_val + operand
            elif op == 'subtract':
                return num_val - operand
            elif op == 'multiply':
                return num_val * operand
            elif op == 'divide':
                return num_val / operand if operand != 0 else num_val
            elif op == 'modulo':
                return num_val % operand if operand != 0 else num_val
            elif op == 'percentage':
                return (num_val / operand * 100.0) if operand != 0 else 0.0
            elif op == 'round':
                prec = max(0, int(self.math_round_precision or 0))
                return round(num_val, prec)
            elif op == 'abs':
                return abs(num_val)

            return num_val

        # 7. Substring / Slicing / Split
        elif self.transform_category == 'string_slice':
            str_val = str(val)
            mode = self.slice_mode
            if mode == 'left':
                return str_val[:max(0, self.slice_length)]
            elif mode == 'right':
                n = max(0, self.slice_length)
                return str_val[-n:] if n > 0 else ''
            elif mode == 'split':
                delim = self.split_delimiter or ','
                parts = str_val.split(delim)
                idx = self.split_index or 0
                if 0 <= idx < len(parts):
                    return parts[idx].strip()
                return self.default_fallback or ''
            else:
                s = max(0, self.slice_start)
                e = max(s, self.slice_end)
                return str_val[s:e]

        # 8. Slugify Text
        elif self.transform_category == 'slugify':
            str_val = str(val).strip().lower()
            str_val = re.sub(r'[^\w\s-]', '', str_val)
            return re.sub(r'[-\s]+', '_', str_val)

        # 9. Case-When Conditional Logic
        elif self.transform_category == 'case_when':
            if not self.case_when_json:
                return val
            try:
                cases = json.loads(self.case_when_json)
                eval_ctx = {'value': val, 'record': record_ctx or {}, 're': re}
                for c in cases:
                    cond = c.get('condition', 'True')
                    if eval(cond, eval_ctx):
                        return c.get('result', val)
            except Exception as e:
                _logger.warning("Case-when evaluation error: %s", e)
            return val

        # 10. Python Expression
        elif self.transform_category == 'python_expr':
            if not self.python_code:
                return val
            eval_ctx = {
                'value': val,
                'record': record_ctx or {},
                'env': self.env,
                'default': self.default_fallback,
                're': re,
                'datetime': datetime,
                'math': math,
                'json': json,
            }
            try:
                return eval(self.python_code, eval_ctx)
            except Exception as e:
                _logger.error("Python expression transform error: %s", e)
                return val

        # 11. AI Natural Language Transformer
        elif self.transform_category == 'ai_prompt':
            if not self.ai_prompt_template:
                return val
            ai_config = self.ai_config_id or self.env['migration.ai.config'].get_default_provider()
            if not ai_config:
                _logger.warning("No AI provider configured for AI transform step ID %s", self.id)
                return val
            
            prompt = self.ai_prompt_template.replace('{value}', str(val))
            try:
                res = ai_config.call_ai_completion(prompt, json_mode=False)
                return str(res).strip()
            except Exception as e:
                _logger.error("AI prompt transformation error: %s", e)
                return self.default_fallback or val

        return val
