# -*- coding: utf-8 -*-

import datetime
import hashlib
import json
import logging
import math
import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MigrationTransformationLine(models.Model):
    _name = 'migration.transformation.line'
    _description = 'ETL Data Transformation Stage Rule'
    _order = 'sequence asc, id asc'

    template_id = fields.Many2one('migration.template', string='Mapping Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Rule Name', compute='_compute_name', store=True, readonly=False)
    active = fields.Boolean(default=True)

    source_field = fields.Char(string='Source Variable', required=True, help='Input column name from extraction or previous transformation.')
    output_field = fields.Char(
        string='Output Variable',
        required=True,
        help='Target variable name. Set same as source variable for in-place cleansing, or a new name for derived fields.'
    )

    transform_category = fields.Selection([
        ('cleansing', 'Data Cleansing & Sanitization'),
        ('filter_row', 'Filter / Drop Records (Row Filter)'),
        ('date_format', 'Date & Time Formatting'),
        ('unit_conversion', 'Unit Conversion'),
        ('type_conversion', 'Data Type Casting'),
        ('value_map', 'Value Translation Table'),
        ('math_expr', 'Math & Arithmetic Calculations'),
        ('string_slice', 'String Substring / Split / Slice'),
        ('slugify', 'Code / URL Slugify'),
        ('case_when', 'Conditional Logic (Case-When)'),
        ('python_expr', 'Custom Python Expression'),
        ('ai_prompt', 'AI Natural Language Transformer'),
    ], string='Transformation Category', default='cleansing', required=True)

    # 0. Conditional Filter & Row Filtering
    apply_filter = fields.Boolean(
        string='Apply Filter Condition',
        default=False,
        help='Only execute this transformation on records that match the specified filter condition.'
    )
    filter_field = fields.Char(
        string='Filter Variable',
        help='Source variable to test condition against. Defaults to source variable if left empty.'
    )
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
        ('python', 'Python Condition (e.g. value > 100)'),
    ], string='Filter Operator', default='=')
    filter_value = fields.Char(
        string='Filter Target Value',
        help='Comparison value, comma-separated set, regex pattern, or Python expression.'
    )
    filter_action = fields.Selection([
        ('keep_if', 'Keep Record If Condition Met (Drop / Skip otherwise)'),
        ('drop_if', 'Drop / Skip Record If Condition Met (Keep otherwise)'),
    ], string='Filter Action', default='keep_if')

    # Computed Usage Example Hint
    usage_hint = fields.Char(string='Usage Example & Hint', compute='_compute_usage_hint')

    # 1. Cleansing
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

    # 2. Date
    input_date_format = fields.Char(string='Input Format Pattern', default='%Y-%m-%d')
    output_date_format = fields.Char(string='Target Format Pattern', default='%Y-%m-%d')
    tz_offset_hours = fields.Float(string='Timezone Offset (Hours)', default=0.0)
    date_math_days = fields.Integer(string='Add/Subtract Days', default=0)

    # 3. Unit
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

    # 4. Type
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

    # 5. Math
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

    # 6. Slicing / Split
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

    # 7. Case-When
    case_when_json = fields.Text(string='Case-When Rules (JSON)', default='[]')

    # 8. AI
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

    @api.depends('source_field', 'output_field', 'transform_category', 'cleansing_type', 'filter_action', 'apply_filter')
    def _compute_name(self):
        for rec in self:
            src = rec.source_field or 'src'
            out = rec.output_field or src
            cat = rec.transform_category or 'transform'
            prefix = "[Filtered] " if rec.apply_filter else ""
            if cat == 'cleansing':
                action = dict(rec._fields['cleansing_type'].selection).get(rec.cleansing_type, 'Cleanse')
                rec.name = f"{prefix}{src} -> {action} -> {out}"
            elif cat == 'filter_row':
                action = "Keep if" if rec.filter_action == 'keep_if' else "Drop if"
                rec.name = f"Row Filter: {action} {rec.filter_field or src} {rec.filter_operator} {rec.filter_value or ''}"
            elif cat == 'unit_conversion':
                rec.name = f"{prefix}{src} ({rec.source_unit}->{rec.target_unit}) -> {out}"
            elif cat == 'type_conversion':
                rec.name = f"{prefix}{src} (cast to {rec.target_type}) -> {out}"
            elif cat == 'math_expr':
                rec.name = f"{prefix}{src} (math {rec.math_op}) -> {out}"
            elif cat == 'date_format':
                rec.name = f"{prefix}{src} (date format) -> {out}"
            elif cat == 'slugify':
                rec.name = f"{prefix}{src} (slugify) -> {out}"
            elif cat == 'ai_prompt':
                rec.name = f"{prefix}{src} (AI transform) -> {out}"
            else:
                rec.name = f"{prefix}{src} ({cat}) -> {out}"

    def _eval_condition(self, row_dict):
        """Evaluates whether row_dict satisfies this transformation line's filter condition."""
        self.ensure_one()
        f_field = self.filter_field or self.source_field
        raw_val = row_dict.get(f_field)
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
                'record': row_dict,
                're': re,
                'datetime': datetime,
                'math': math,
                'json': json,
            }
            try:
                return bool(eval(target, eval_ctx))
            except Exception as e:
                _logger.warning("Python filter condition evaluation error on field '%s': %s", f_field, e)
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

        # Numeric or String comparison for =, !=, >, <, >=, <=
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

    def apply_transformation(self, record_dict):
        """Applies transformation logic reading from record_dict[source_field] and writing to record_dict[output_field]."""
        self.ensure_one()

        # 1. Row Filter Category
        if self.transform_category == 'filter_row':
            matched = self._eval_condition(record_dict)
            if self.filter_action == 'keep_if' and not matched:
                raise UserError("__DROP_ROW_FILTER__")
            elif self.filter_action == 'drop_if' and matched:
                raise UserError("__DROP_ROW_FILTER__")
            return record_dict.get(self.source_field)

        # 2. Conditional Transform Filter
        if self.apply_filter:
            matched = self._eval_condition(record_dict)
            if not matched:
                out_f = self.output_field or self.source_field
                if out_f not in record_dict:
                    record_dict[out_f] = record_dict.get(self.source_field)
                return record_dict.get(out_f)

        raw_val = record_dict.get(self.source_field)
        transformed_val = self._evaluate_single_transform(raw_val, record_dict)
        record_dict[self.output_field] = transformed_val
        return transformed_val

    def _evaluate_single_transform(self, raw_value, row_dict=None):
        if row_dict is None:
            row_dict = {}

        cat = self.transform_category

        # 1. CLEANSING
        if cat == 'cleansing':
            ctype = self.cleansing_type
            if raw_value is None or raw_value is False:
                if ctype == 'handle_null':
                    return self.default_fallback or ''
                elif ctype == 'drop_if_null':
                    raise UserError("__DROP_ROW_NULL__")
                return ''

            s_val = str(raw_value)
            if ctype == 'trim':
                return s_val.strip()
            elif ctype == 'upper':
                return s_val.upper()
            elif ctype == 'lower':
                return s_val.lower()
            elif ctype == 'title':
                return s_val.title()
            elif ctype == 'capitalize':
                return s_val.capitalize()
            elif ctype == 'pad_left':
                return s_val.rjust(self.pad_count, (self.pad_char or '0')[:1])
            elif ctype == 'pad_right':
                return s_val.ljust(self.pad_count, (self.pad_char or '0')[:1])
            elif ctype == 'regex':
                pattern = self.regex_pattern or ''
                repl = self.regex_replace or ''
                return re.sub(pattern, repl, s_val)
            elif ctype == 'regex_extract':
                pattern = self.regex_pattern or ''
                m = re.search(pattern, s_val)
                if m:
                    idx = self.regex_group_index or 1
                    return m.group(idx) if idx <= len(m.groups()) else m.group(0)
                return self.default_fallback or ''
            elif ctype == 'strip_html':
                clean_text = re.sub(r'<[^>]*>', '', s_val)
                import html
                return html.unescape(clean_text).strip()
            elif ctype == 'strip_non_numeric':
                return re.sub(r'[^\d.]', '', s_val)
            elif ctype == 'strip_non_alphanumeric':
                return re.sub(r'[^\w\s]', '', s_val)
            elif ctype == 'handle_null':
                return s_val if s_val.strip() else (self.default_fallback or '')
            elif ctype == 'drop_if_null':
                if not s_val.strip():
                    raise UserError("__DROP_ROW_NULL__")
                return s_val

        # 2. DATE FORMAT
        elif cat == 'date_format':
            if not raw_value:
                return False
            s_val = str(raw_value).strip()
            in_fmt = self.input_date_format or '%Y-%m-%d'
            out_fmt = self.output_date_format or '%Y-%m-%d'

            dt = None
            for fmt in (in_fmt, '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y'):
                try:
                    dt = datetime.datetime.strptime(s_val, fmt)
                    break
                except ValueError:
                    continue

            if not dt:
                return s_val

            if self.tz_offset_hours:
                dt += datetime.timedelta(hours=self.tz_offset_hours)
            if self.date_math_days:
                dt += datetime.timedelta(days=self.date_math_days)

            return dt.strftime(out_fmt)

        # 3. UNIT CONVERSION
        elif cat == 'unit_conversion':
            if raw_value is None or raw_value == '':
                return 0.0
            try:
                num = float(re.sub(r'[^\d.-]', '', str(raw_value)))
            except Exception:
                return raw_value

            utype = self.unit_type
            if utype == 'custom':
                return num * (self.custom_scale_ratio or 1.0)
            elif utype == 'mass':
                # kg base
                factors = {'kg': 1.0, 'g': 0.001, 'mg': 0.000001, 'lb': 0.45359237, 'oz': 0.0283495}
                val_kg = num * factors.get(self.source_unit, 1.0)
                return val_kg / factors.get(self.target_unit, 1.0)
            elif utype == 'length':
                # m base
                factors = {'m': 1.0, 'km': 1000.0, 'cm': 0.01, 'mm': 0.001, 'ft': 0.3048, 'in': 0.0254, 'mi': 1609.34}
                val_m = num * factors.get(self.source_unit, 1.0)
                return val_m / factors.get(self.target_unit, 1.0)
            elif utype == 'volume':
                # l base
                factors = {'l': 1.0, 'ml': 0.001, 'gal': 3.78541}
                val_l = num * factors.get(self.source_unit, 1.0)
                return val_l / factors.get(self.target_unit, 1.0)
            elif utype == 'temp':
                s_u = self.source_unit
                t_u = self.target_unit
                if s_u == 'C':
                    c_deg = num
                elif s_u == 'F':
                    c_deg = (num - 32.0) * (5.0 / 9.0)
                elif s_u == 'K':
                    c_deg = num - 273.15
                else:
                    c_deg = num

                if t_u == 'C':
                    return c_deg
                elif t_u == 'F':
                    return (c_deg * (9.0 / 5.0)) + 32.0
                elif t_u == 'K':
                    return c_deg + 273.15

        # 4. TYPE CONVERSION
        elif cat == 'type_conversion':
            tt = self.target_type
            if raw_value is None or raw_value == '':
                if tt in ('integer', 'float'):
                    return 0 if tt == 'integer' else 0.0
                elif tt == 'boolean':
                    return False
                return ''

            s_val = str(raw_value).strip()
            if tt == 'string':
                return s_val
            elif tt == 'integer':
                try:
                    return int(float(s_val))
                except Exception:
                    return 0
            elif tt == 'float':
                try:
                    return float(re.sub(r'[^\d.-]', '', s_val))
                except Exception:
                    return 0.0
            elif tt == 'boolean':
                return s_val.lower() in ('1', 'true', 't', 'yes', 'y', 'on', 'enabled')
            elif tt == 'date':
                return s_val[:10]
            elif tt == 'datetime':
                return s_val[:19]
            elif tt == 'json_parse':
                try:
                    return json.loads(s_val)
                except Exception:
                    return {}
            elif tt == 'json_dump':
                return json.dumps(raw_value, default=str)
            elif tt == 'base64_encode':
                import base64
                return base64.b64encode(str(raw_value).encode('utf-8')).decode('ascii')
            elif tt == 'base64_decode':
                import base64
                try:
                    return base64.b64decode(str(raw_value)).decode('utf-8', errors='replace')
                except Exception:
                    return str(raw_value)

        # 5. VALUE MAPPING
        elif cat == 'value_map':
            mapping_dict = {}
            if self.value_mapping_json:
                try:
                    mapping_dict = json.loads(self.value_mapping_json)
                except Exception:
                    mapping_dict = {}
            key = str(raw_value).strip() if raw_value is not None else ''
            if key in mapping_dict:
                return mapping_dict[key]
            return self.default_fallback or raw_value

        # 6. MATH EXPRESSION
        elif cat == 'math_expr':
            try:
                num = float(raw_value or 0.0)
            except Exception:
                num = 0.0
            op = self.math_op
            operand = self.math_operand or 0.0
            if op == 'add':
                return num + operand
            elif op == 'subtract':
                return num - operand
            elif op == 'multiply':
                return num * operand
            elif op == 'divide':
                return (num / operand) if operand != 0 else num
            elif op == 'round':
                prec = self.math_round_precision or 0
                return round(num, prec) if prec > 0 else int(round(num))
            elif op == 'abs':
                return abs(num)
            elif op == 'modulo':
                return num % operand if operand != 0 else num
            elif op == 'percentage':
                return (num / 100.0) * operand

        # 7. STRING SLICING / SPLIT
        elif cat == 'string_slice':
            s_val = str(raw_value or '')
            smode = self.slice_mode
            if smode == 'slice':
                return s_val[self.slice_start:self.slice_end]
            elif smode == 'left':
                return s_val[:self.slice_length]
            elif smode == 'right':
                return s_val[-self.slice_length:] if self.slice_length > 0 else s_val
            elif smode == 'split':
                delimiter = self.split_delimiter or ','
                tokens = s_val.split(delimiter)
                idx = self.split_index or 0
                if idx < len(tokens):
                    return tokens[idx].strip()
                return self.default_fallback or ''

        # 8. SLUGIFY
        elif cat == 'slugify':
            s_val = str(raw_value or '').strip().lower()
            s_val = re.sub(r'[^\w\s-]', '', s_val)
            return re.sub(r'[-\s]+', '_', s_val).strip('_')

        # 9. CASE-WHEN
        elif cat == 'case_when':
            rules = []
            if self.case_when_json:
                try:
                    rules = json.loads(self.case_when_json)
                except Exception:
                    rules = []
            s_val = str(raw_value or '').strip()
            for r in rules:
                when_val = str(r.get('when', '')).strip()
                then_val = r.get('then', '')
                if s_val.lower() == when_val.lower():
                    return then_val
            return self.default_fallback or raw_value

        # 10. PYTHON EXPRESSION
        elif cat == 'python_expr':
            if not self.python_code:
                return raw_value
            eval_ctx = {
                'value': raw_value,
                'record': row_dict,
                'datetime': datetime,
                're': re,
                'json': json,
                'math': math,
                'default': self.default_fallback,
            }
            try:
                return eval(self.python_code, eval_ctx)
            except Exception as e:
                _logger.warning("Python transform snippet error on variable '%s': %s", self.source_field, e)
                return self.default_fallback or raw_value

        # 11. AI PROMPT
        elif cat == 'ai_prompt':
            if not self.ai_prompt_template:
                return raw_value
            ai_config = self.env['migration.ai.config'].get_default_provider()
            if not ai_config:
                return raw_value
            prompt = self.ai_prompt_template.replace('{value}', str(raw_value)).replace('{record}', json.dumps(row_dict, default=str))
            try:
                res = ai_config.call_ai_completion(prompt, json_mode=False)
                return str(res).strip()
            except Exception as e:
                _logger.warning("AI Prompt transform error: %s", e)
                return self.default_fallback or raw_value

        return raw_value
