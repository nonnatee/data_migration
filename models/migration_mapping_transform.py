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

    name = fields.Char(string='Step Summary', compute='_compute_name', store=True)

    @api.depends('transform_category', 'cleansing_type', 'unit_type', 'source_unit', 'target_unit',
                 'input_date_format', 'output_date_format', 'target_type', 'math_op', 'slice_mode', 'ai_prompt_template')
    def _compute_name(self):
        for rec in self:
            if rec.transform_category == 'cleansing':
                rec.name = f"Cleanse: {dict(rec._fields['cleansing_type'].selection).get(rec.cleansing_type, rec.cleansing_type)}"
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

    def apply_transform(self, val, record_ctx=None):
        """Applies transformation step logic to input value."""
        self.ensure_one()
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
