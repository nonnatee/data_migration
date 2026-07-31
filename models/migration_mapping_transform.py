# -*- coding: utf-8 -*-

import datetime
import json
import logging
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
        ('cleansing', 'Data Cleansing'),
        ('date_format', 'Date & Time Formatting'),
        ('unit_conversion', 'Unit Conversion'),
        ('type_conversion', 'Data Type Conversion'),
        ('value_map', 'Value Mapping Table'),
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
    input_date_format = fields.Char(string='Input Format Pattern', default='%Y-%m-%d', help='e.g. %Y-%m-%d, %d/%m/%Y, %Y-%m-%d %H:%M:%S, or timestamp')
    output_date_format = fields.Char(string='Target Format Pattern', default='%Y-%m-%d', help='Target strftime pattern e.g. %Y-%m-%d %H:%M:%S')
    tz_offset_hours = fields.Float(string='Timezone Offset (Hours)', default=0.0, help='e.g. +7.0 for UTC+7')

    # 3. Unit Conversion Options
    unit_type = fields.Selection([
        ('mass', 'Weight / Mass (kg, g, lb, oz)'),
        ('length', 'Length / Distance (m, km, ft, in)'),
        ('volume', 'Volume (l, ml, gal)'),
        ('temp', 'Temperature (C, F, K)'),
        ('custom', 'Custom Scale Multiplier'),
    ], string='Unit Category', default='mass')

    source_unit = fields.Selection([
        # Mass
        ('kg', 'Kilogram (kg)'),
        ('g', 'Gram (g)'),
        ('mg', 'Milligram (mg)'),
        ('lb', 'Pound (lb)'),
        ('oz', 'Ounce (oz)'),
        # Length
        ('m', 'Meter (m)'),
        ('km', 'Kilometer (km)'),
        ('cm', 'Centimeter (cm)'),
        ('mm', 'Millimeter (mm)'),
        ('ft', 'Feet (ft)'),
        ('in', 'Inch (in)'),
        ('mi', 'Mile (mi)'),
        # Volume
        ('l', 'Liter (l)'),
        ('ml', 'Milliliter (ml)'),
        ('gal', 'Gallon (gal)'),
        # Temp
        ('C', 'Celsius (°C)'),
        ('F', 'Fahrenheit (°F)'),
        ('K', 'Kelvin (K)'),
    ], string='Source Unit', default='kg')

    target_unit = fields.Selection([
        # Mass
        ('kg', 'Kilogram (kg)'),
        ('g', 'Gram (g)'),
        ('mg', 'Milligram (mg)'),
        ('lb', 'Pound (lb)'),
        ('oz', 'Ounce (oz)'),
        # Length
        ('m', 'Meter (m)'),
        ('km', 'Kilometer (km)'),
        ('cm', 'Centimeter (cm)'),
        ('mm', 'Millimeter (mm)'),
        ('ft', 'Feet (ft)'),
        ('in', 'Inch (in)'),
        ('mi', 'Mile (mi)'),
        # Volume
        ('l', 'Liter (l)'),
        ('ml', 'Milliliter (ml)'),
        ('gal', 'Gallon (gal)'),
        # Temp
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
        ('boolean', 'Boolean (True/False)'),
        ('date', 'Date Object'),
        ('datetime', 'Datetime Object'),
    ], string='Target Data Type', default='string')

    # 5. Value Map & Python Snippet
    value_mapping_json = fields.Text(string='Value Mapping (JSON)', default='{"raw_val": "target_val"}')
    python_code = fields.Text(string='Python Snippet', default='value.strip().title() if value else default')
    default_fallback = fields.Char(string='Default Fallback Value')

    name = fields.Char(string='Step Summary', compute='_compute_name', store=True)

    @api.depends('transform_category', 'cleansing_type', 'unit_type', 'source_unit', 'target_unit', 'input_date_format', 'output_date_format', 'target_type')
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
                rec.name = f"Cast to {dict(rec._fields['target_type'].selection).get(rec.target_type, rec.target_type)}"
            elif rec.transform_category == 'value_map':
                rec.name = "Value Map Lookup"
            elif rec.transform_category == 'python_expr':
                rec.name = "Python Snippet"
            else:
                rec.name = "Transform Step"

    def apply_transform(self, val, record_ctx=None):
        """Applies transformation step logic to input value."""
        self.ensure_one()
        if val is None:
            val = self.default_fallback or ''

        # 1. Data Cleansing
        if self.transform_category == 'cleansing':
            str_val = str(val)
            if self.cleansing_type == 'trim':
                return str_val.strip()
            elif self.cleansing_type == 'upper':
                return str_val.upper()
            elif self.cleansing_type == 'lower':
                return str_val.lower()
            elif self.cleansing_type == 'title':
                return str_val.title()
            elif self.cleansing_type == 'capitalize':
                return str_val.capitalize()
            elif self.cleansing_type == 'pad_left':
                char = self.pad_char or '0'
                return str_val.rjust(self.pad_count, char)
            elif self.cleansing_type == 'pad_right':
                char = self.pad_char or ' '
                return str_val.ljust(self.pad_count, char)
            elif self.cleansing_type == 'regex':
                pat = self.regex_pattern or ''
                repl = self.regex_replace or ''
                return re.sub(pat, repl, str_val) if pat else str_val
            elif self.cleansing_type == 'strip_html':
                return re.sub(r'<[^>]*>', '', str_val)
            elif self.cleansing_type == 'strip_non_numeric':
                return re.sub(r'[^\d.-]', '', str_val)

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
                for fmt in [self.input_date_format, '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                    if not fmt:
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
                # Convert source to Celsius first
                if s_unit == 'C':
                    c_val = num_val
                elif s_unit == 'F':
                    c_val = (num_val - 32.0) * (5.0 / 9.0)
                elif s_unit == 'K':
                    c_val = num_val - 273.15
                else:
                    c_val = num_val

                # Convert Celsius to target
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
                return str(val).lower() in ('true', '1', 'yes', 't', 'y', 'on')
            elif ttype in ('date', 'datetime'):
                return str(val)

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

        # 6. Python Expression
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
            }
            try:
                return eval(self.python_code, eval_ctx)
            except Exception as e:
                _logger.error("Python expression transform error: %s", e)
                return val

        return val
