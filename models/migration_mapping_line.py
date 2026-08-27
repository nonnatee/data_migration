# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MigrationMappingLine(models.Model):
    _name = 'migration.mapping.line'
    _description = 'Data Migration Target Field Mapping'
    _order = 'sequence asc, id asc'

    template_id = fields.Many2one('migration.template', string='Mapping Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    source_field = fields.Char(string='Source Variable', required=True, help='Raw source column or transformed/derived variable name.')

    target_field_id = fields.Many2one(
        'ir.model.fields',
        string='Target Odoo Field',
        required=True,
        ondelete='cascade',
        domain="[('model_id', '=', parent.target_model_id), ('readonly', '=', False)]"
    )
    target_field_name = fields.Char(related='target_field_id.name', string='Target Field Name', store=True, readonly=True)
    target_field_ttype = fields.Selection(related='target_field_id.ttype', string='Field Type', readonly=True)
    relation_model = fields.Char(related='target_field_id.relation', string='Related Model', readonly=True)

    default_value = fields.Char(string='Default Fallback Value', help='Value used if source variable is empty or null.')
    is_key_field = fields.Boolean(
        string='Unique Match Key',
        default=False,
        help='Used as part of the composite key to match existing Odoo records during Upsert/Update operations.'
    )

    # Relational Resolution Strategy
    lookup_strategy = fields.Selection([
        ('xml_id', 'External ID (XML ID)'),
        ('field_search', 'Match by Target Field (e.g. Code / Name / Ref)'),
        ('domain_expr', 'Custom Search Domain Expression'),
        ('auto_create', 'Auto-Create Target Record if Not Found'),
        ('record_map', 'Cross-Stage Migration Map (migration.record.map)'),
    ], string='Relational Lookup Strategy', default='field_search',
       help='Strategy used to resolve foreign keys for Many2one, Many2many, or One2many relationships.')

    lookup_field_id = fields.Many2one(
        'ir.model.fields',
        string='Match Related Field',
        domain="[('model', '=', relation_model), ('store', '=', True)]",
        help='Field on the related model to match against the source value (e.g., ref, vat, default_code, name).'
    )
    lookup_domain = fields.Char(
        string='Lookup Domain Expression',
        placeholder="[('code', '=', value), ('active', '=', True)]",
        help="Python domain expression evaluated with 'value' and 'record' in context."
    )

    def resolve_value(self, clean_record_dict):
        """Resolves target field value from clean record dictionary."""
        self.ensure_one()
        raw_val = clean_record_dict.get(self.source_field)

        # Fallback to default if empty
        if (raw_val is None or raw_val == '') and self.default_value:
            raw_val = self.default_value

        # Handle relational fields
        ttype = self.target_field_ttype
        if ttype == 'many2one':
            return self._resolve_many2one(raw_val, clean_record_dict)
        elif ttype in ('many2many', 'one2many'):
            return self._resolve_x2many(raw_val, clean_record_dict)
        elif ttype == 'boolean':
            if isinstance(raw_val, bool):
                return raw_val
            return str(raw_val).strip().lower() in ('1', 'true', 'yes', 't', 'y', 'on', 'enabled')
        elif ttype == 'integer':
            try:
                return int(float(raw_val))
            except Exception:
                return False if raw_val in (None, '') else 0
        elif ttype == 'float':
            try:
                return float(raw_val)
            except Exception:
                return False if raw_val in (None, '') else 0.0

        return raw_val if raw_val is not None else False

    def _resolve_many2one(self, value, record_dict):
        if not value:
            return False

        rel_model = self.relation_model
        if not rel_model or rel_model not in self.env:
            return False

        strat = self.lookup_strategy or 'field_search'

        # 1. XML ID
        if strat == 'xml_id':
            xml_id = str(value).strip()
            if '.' not in xml_id:
                xml_id = f"__export__.{xml_id}"
            rec = self.env.ref(xml_id, raise_if_not_found=False)
            return rec.id if rec and rec._name == rel_model else False

        # 2. Record Map
        elif strat == 'record_map':
            return self._resolve_from_record_map(value)

        # 3. Custom Domain Expression
        elif strat == 'domain_expr' and self.lookup_domain:
            try:
                eval_ctx = {'value': value, 'record': record_dict}
                domain = eval(self.lookup_domain, eval_ctx)
                rec = self.env[rel_model].search(domain, limit=1)
                return rec.id if rec else False
            except Exception as e:
                _logger.warning("Domain eval error in Many2one resolution for %s: %s", self.target_field_name, e)
                return False

        # 4. Field Search & Auto-Create
        else:
            match_field = self.lookup_field_id.name if self.lookup_field_id else 'name'
            rec = self.env[rel_model].search([(match_field, '=', value)], limit=1)
            if rec:
                return rec.id

            if strat == 'auto_create':
                try:
                    new_rec = self.env[rel_model].create({match_field: value})
                    return new_rec.id
                except Exception as e:
                    _logger.warning("Auto-create failed for %s (%s): %s", rel_model, value, e)
                    return False

        return False

    def _resolve_x2many(self, value, record_dict):
        if not value:
            return [(5, 0, 0)]
        ids = []
        if isinstance(value, list):
            tokens = value
        else:
            tokens = [v.strip() for v in str(value).split(',') if v.strip()]

        for tok in tokens:
            m2o_id = self._resolve_many2one(tok, record_dict)
            if m2o_id:
                ids.append(m2o_id)

        return [(6, 0, ids)] if ids else False

    def _resolve_from_record_map(self, source_key):
        """Resolves target ID from cross-reference record maps."""
        rec_map = self.env['migration.record.map'].search([
            ('source_key', '=', str(source_key).strip()),
            ('target_model', '=', self.relation_model),
        ], limit=1)
        return rec_map.target_id if rec_map else False
