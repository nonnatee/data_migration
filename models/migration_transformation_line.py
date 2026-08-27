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

    @api.onchange('source_field')
    def _onchange_source_field(self):
        if self.source_field and not self.output_field:
            self.output_field = self.source_field

    @api.depends('source_field', 'output_field', 'transform_category', 'cleansing_type')
    def _compute_name(self):
        for rec in self:
            src = rec.source_field or 'src'
            out = rec.output_field or src
            cat = rec.transform_category or 'transform'
            if cat == 'cleansing':
                action = dict(rec._fields['cleansing_type'].selection).get(rec.cleansing_type, 'Cleanse')
                rec.name = f"{src} -> {action} -> {out}"
            elif cat == 'unit_conversion':
                rec.name = f"{src} ({rec.source_unit}->{rec.target_unit}) -> {out}"
            elif cat == 'type_conversion':
                rec.name = f"{src} (cast to {rec.target_type}) -> {out}"
            elif cat == 'math_expr':
                rec.name = f"{src} (math {rec.math_op}) -> {out}"
            elif cat == 'date_format':
                rec.name = f"{src} (date format) -> {out}"
            elif cat == 'slugify':
                rec.name = f"{src} (slugify) -> {out}"
            elif cat == 'ai_prompt':
                rec.name = f"{src} (AI transform) -> {out}"
            else:
                rec.name = f"{src} ({cat}) -> {out}"

    def apply_transformation(self, record_dict):
        """Applies transformation logic reading from record_dict[source_field] and writing to record_dict[output_field]."""
        self.ensure_one()
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
