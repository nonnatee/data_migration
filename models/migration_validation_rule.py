# -*- coding: utf-8 -*-

import datetime
import json
import logging
import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MigrationValidationRule(models.Model):
    _name = 'migration.validation.rule'
    _description = 'ETL Data Validation Rule'
    _order = 'sequence asc, id asc'

    template_id = fields.Many2one('migration.template', string='Mapping Template', required=True, ondelete='cascade')
    name = fields.Char(string='Rule Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)

    rule_timing = fields.Selection([
        ('pre_load', 'Pre-Load Validation (Source & Transformed Data)'),
        ('post_load', 'Post-Load Verification (Target Database Record)'),
    ], string='Validation Timing', default='pre_load', required=True)

    source_field = fields.Char(string='Source Column', help='Column name in source record to test.')
    target_field_id = fields.Many2one('ir.model.fields', string='Target Odoo Field')
    target_field_name = fields.Char(related='target_field_id.name', readonly=True)

    rule_type = fields.Selection([
        ('mandatory', 'Mandatory / Not-Null Check'),
        ('regex', 'Regex Pattern Match (e.g. Email, VAT, Phone)'),
        ('numeric_range', 'Numeric Range Boundary (Min / Max)'),
        ('value_in_set', 'Allowed Value Set (Enum / Inclusion)'),
        ('foreign_key', 'Foreign Key Relational Integrity'),
        ('custom_python', 'Custom Python Integrity Expression'),
        ('business_integrity', 'Business Logic Constraint'),
    ], string='Rule Type', default='mandatory', required=True)

    # 1. Regex & Set Options
    regex_pattern = fields.Char(string='Regex Pattern', default=r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')
    allowed_values = fields.Char(string='Allowed Values (Comma-Separated)', placeholder='draft,posted,cancel')

    # 2. Numeric Range Options
    min_value = fields.Float(string='Minimum Value', default=0.0)
    max_value = fields.Float(string='Maximum Value', default=999999999.0)
    check_min = fields.Boolean(string='Enforce Min', default=True)
    check_max = fields.Boolean(string='Enforce Max', default=False)

    # 3. Foreign Key Options
    fk_model = fields.Char(string='Relation Model', placeholder='res.country or res.partner')
    fk_field = fields.Char(string='Relation Field to Match', default='name', placeholder='code or ref or name')

    # 4. Custom Python Expression
    python_code = fields.Text(
        string='Python Validation Expression',
        default='bool(value and len(str(value)) >= 2)',
        help='Expression must evaluate to True for valid, False for failure. Variables: value, record (dict), env, re, datetime'
    )

    action_on_failure = fields.Selection([
        ('warning', 'Log Warning (Proceed with Record)'),
        ('reject_record', 'Reject Record (Skip & Log Error)'),
        ('abort_stage', 'Abort Execution (Halt Entire Stage)'),
    ], string='Action on Failure', default='reject_record', required=True)

    error_message = fields.Char(string='Custom Error Message', placeholder='Field cannot be empty or invalid')

    def evaluate_rule(self, val, raw_record):
        """Evaluates rule against given value and record dictionary.
        Returns: (is_valid: bool, error_msg: str or False)
        """
        self.ensure_one()
        rule_t = self.rule_type

        # 1. Mandatory
        if rule_t == 'mandatory':
            if val is None or str(val).strip() == '':
                msg = self.error_message or _("Mandatory field '%s' is empty or null.") % (self.source_field or self.target_field_name)
                return False, msg
            return True, False

        # 2. Regex
        elif rule_t == 'regex':
            if val is None or str(val).strip() == '':
                return True, False # Null checked by mandatory rule
            str_val = str(val).strip()
            if not re.match(self.regex_pattern or '.*', str_val):
                msg = self.error_message or _("Value '%s' does not match pattern '%s'.") % (str_val, self.regex_pattern)
                return False, msg
            return True, False

        # 3. Numeric Range
        elif rule_t == 'numeric_range':
            try:
                num = float(re.sub(r'[^\d.-]', '', str(val)))
            except Exception:
                msg = self.error_message or _("Value '%s' is not a valid number.") % val
                return False, msg

            if self.check_min and num < self.min_value:
                msg = self.error_message or _("Value %s is below minimum allowed %s.") % (num, self.min_value)
                return False, msg
            if self.check_max and num > self.max_value:
                msg = self.error_message or _("Value %s exceeds maximum allowed %s.") % (num, self.max_value)
                return False, msg
            return True, False

        # 4. Value in Set
        elif rule_t == 'value_in_set':
            if not self.allowed_values:
                return True, False
            allowed = [v.strip().lower() for v in self.allowed_values.split(',')]
            str_val = str(val).strip().lower() if val is not None else ''
            if str_val not in allowed:
                msg = self.error_message or _("Value '%s' is not in allowed list (%s).") % (val, self.allowed_values)
                return False, msg
            return True, False

        # 5. Foreign Key Relational Check
        elif rule_t == 'foreign_key':
            if not val or not self.fk_model:
                return True, False
            rel_model = self.fk_model
            if rel_model not in self.env:
                return True, False
            match_f = self.fk_field or 'name'
            exists = self.env[rel_model].search_count([(match_f, '=', val)]) > 0
            if not exists:
                msg = self.error_message or _("Referenced record '%s' not found in model '%s'.") % (val, rel_model)
                return False, msg
            return True, False

        # 6. Custom Python / Business Integrity
        elif rule_t in ('custom_python', 'business_integrity'):
            if not self.python_code:
                return True, False
            eval_ctx = {
                'value': val,
                'record': raw_record or {},
                'env': self.env,
                're': re,
                'datetime': datetime,
            }
            try:
                res = eval(self.python_code, eval_ctx)
                if not bool(res):
                    msg = self.error_message or _("Business validation constraint failed for record.")
                    return False, msg
                return True, False
            except Exception as e:
                msg = self.error_message or _("Python validation error: %s") % str(e)
                return False, msg

        return True, False
