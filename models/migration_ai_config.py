# -*- coding: utf-8 -*-

import json
import logging
import urllib.request
import urllib.error
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MigrationAIConfig(models.Model):
    _name = 'migration.ai.config'
    _description = 'Migration AI Provider Configuration'
    _order = 'sequence asc, name asc'

    name = fields.Char(string='Config Name', required=True, default='Primary AI Assistant')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(string='Default Provider', default=True, help='Use this AI provider by default across all ETL operations.')

    provider = fields.Selection([
        ('openai', 'OpenAI (GPT-4o / GPT-4o-mini / GPT-4-turbo)'),
        ('gemini', 'Google Gemini (Gemini 2.0 / 1.5 Pro / Flash)'),
        ('anthropic', 'Anthropic Claude (Claude 3.5 Sonnet / Haiku)'),
        ('ollama', 'Ollama (Local LLM / Llama 3 / Mistral / Qwen)'),
        ('custom_api', 'Custom OpenAI-Compatible Endpoint'),
    ], string='AI Provider', default='openai', required=True)

    api_key = fields.Char(string='API Key', help='Secret API Key for authentication')
    model_name = fields.Char(string='Model Name', default='gpt-4o-mini', required=True,
                            help='e.g. gpt-4o, gpt-4o-mini, gemini-1.5-flash, claude-3-5-sonnet-20241022, llama3')
    base_url = fields.Char(string='Base URL / Endpoint',
                           help='Optional custom endpoint base URL, e.g. http://localhost:11434 for Ollama or https://api.openai.com/v1')
    temperature = fields.Float(string='Temperature', default=0.2, help='Lower temperature produces more deterministic responses.')
    max_tokens = fields.Integer(string='Max Tokens', default=2048)
    system_prompt_default = fields.Text(
        string='Default System Prompt',
        default="You are an expert Data Migration & ETL specialist for Odoo 19 ERP. Provide high accuracy, robust JSON outputs, and clean Python code when requested."
    )

    state = fields.Selection([
        ('draft', 'Not Tested'),
        ('connected', 'Connected / Ready'),
        ('error', 'Connection Error'),
    ], string='Status', default='draft', readonly=True)
    last_error = fields.Text(string='Last Error Message', readonly=True)

    @api.constrains('is_default')
    def _check_single_default(self):
        for rec in self:
            if rec.is_default:
                other_defaults = self.search([('id', '!=', rec.id), ('is_default', '=', True)])
                other_defaults.write({'is_default': False})

    @api.onchange('provider')
    def _onchange_provider(self):
        if self.provider == 'openai':
            self.model_name = 'gpt-4o-mini'
            self.base_url = 'https://api.openai.com/v1'
        elif self.provider == 'gemini':
            self.model_name = 'gemini-1.5-flash'
            self.base_url = 'https://generativelanguage.googleapis.com/v1beta'
        elif self.provider == 'anthropic':
            self.model_name = 'claude-3-5-sonnet-20241022'
            self.base_url = 'https://api.anthropic.com/v1'
        elif self.provider == 'ollama':
            self.model_name = 'llama3'
            self.base_url = 'http://localhost:11434'
        elif self.provider == 'custom_api':
            self.model_name = 'default'
            self.base_url = 'https://api.example.com/v1'

    def action_test_ai_connection(self):
        """Tests the AI provider connection with a ping prompt."""
        self.ensure_one()
        try:
            test_prompt = "Reply with exactly: {\"status\": \"ok\", \"message\": \"AI connection successful\"}"
            res = self.call_ai_completion(test_prompt, system_prompt="You are a ping test assistant. Return valid JSON only.", json_mode=True)
            self.write({
                'state': 'connected',
                'last_error': False,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('AI Connection Successful'),
                    'message': _('Successfully connected to %s (%s). Response: %s', self.provider.upper(), self.model_name, str(res)[:100]),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.exception("AI Connection test failed for config ID %s", self.id)
            self.write({
                'state': 'error',
                'last_error': str(e),
            })
            raise UserError(_("AI Connection test failed: %s") % str(e))

    def call_ai_completion(self, user_prompt, system_prompt=None, json_mode=True):
        """Unified method to call any configured AI Provider and return the generated text or parsed JSON."""
        self.ensure_one()
        sys_prompt = system_prompt or self.system_prompt_default or "You are an ETL expert for Odoo ERP."

        if self.provider in ('openai', 'custom_api'):
            return self._call_openai_api(user_prompt, sys_prompt, json_mode=json_mode)
        elif self.provider == 'gemini':
            return self._call_gemini_api(user_prompt, sys_prompt, json_mode=json_mode)
        elif self.provider == 'anthropic':
            return self._call_anthropic_api(user_prompt, sys_prompt, json_mode=json_mode)
        elif self.provider == 'ollama':
            return self._call_ollama_api(user_prompt, sys_prompt, json_mode=json_mode)
        else:
            raise UserError(_("Unsupported AI provider: %s") % self.provider)

    @api.model
    def get_default_provider(self):
        """Fetch the default active AI provider config."""
        provider = self.search([('active', '=', True), ('is_default', '=', True)], limit=1)
        if not provider:
            provider = self.search([('active', '=', True)], limit=1)
        return provider

    # -------------------------------------------------------------------------
    # PROVIDER HTTP CLIENTS
    # -------------------------------------------------------------------------

    def _call_openai_api(self, user_prompt, system_prompt, json_mode=True):
        base_url = (self.base_url or 'https://api.openai.com/v1').rstrip('/')
        url = f"{base_url}/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {self.api_key or ''}",
        }
        payload = {
            'model': self.model_name,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens or 2048,
        }
        if json_mode:
            payload['response_format'] = {'type': 'json_object'}

        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = json.loads(response.read().decode('utf-8'))
                raw_text = body['choices'][0]['message']['content']
                if json_mode:
                    try:
                        return json.loads(raw_text)
                    except Exception:
                        return self._extract_json_from_text(raw_text)
                return raw_text
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            raise UserError(_("OpenAI API error (%s): %s") % (e.code, error_body))
        except Exception as e:
            raise UserError(_("Failed to communicate with OpenAI API: %s") % str(e))

    def _call_gemini_api(self, user_prompt, system_prompt, json_mode=True):
        base_url = (self.base_url or 'https://generativelanguage.googleapis.com/v1beta').rstrip('/')
        model = self.model_name or 'gemini-1.5-flash'
        url = f"{base_url}/models/{model}:generateContent?key={self.api_key or ''}"
        headers = {'Content-Type': 'application/json'}
        full_prompt = f"System Instructions: {system_prompt}\n\nUser Request: {user_prompt}"
        if json_mode:
            full_prompt += "\n\nIMPORTANT: Respond ONLY with a valid raw JSON object. Do not include markdown ticks."

        payload = {
            'contents': [{'parts': [{'text': full_prompt}]}],
            'generationConfig': {
                'temperature': self.temperature,
                'maxOutputTokens': self.max_tokens or 2048,
            }
        }
        if json_mode:
            payload['generationConfig']['responseMimeType'] = 'application/json'

        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = json.loads(response.read().decode('utf-8'))
                candidates = body.get('candidates', [])
                if not candidates:
                    raise UserError(_("Gemini returned empty response."))
                raw_text = candidates[0]['content']['parts'][0]['text']
                if json_mode:
                    try:
                        return json.loads(raw_text)
                    except Exception:
                        return self._extract_json_from_text(raw_text)
                return raw_text
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            raise UserError(_("Gemini API error (%s): %s") % (e.code, error_body))
        except Exception as e:
            raise UserError(_("Failed to communicate with Gemini API: %s") % str(e))

    def _call_anthropic_api(self, user_prompt, system_prompt, json_mode=True):
        base_url = (self.base_url or 'https://api.anthropic.com/v1').rstrip('/')
        url = f"{base_url}/messages"
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': self.api_key or '',
            'anthropic-version': '2023-06-01',
        }
        user_content = user_prompt
        if json_mode:
            user_content += "\n\nRespond ONLY with a valid JSON object. No explanation or code block wrapper."

        payload = {
            'model': self.model_name or 'claude-3-5-sonnet-20241022',
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': user_content}],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens or 2048,
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = json.loads(response.read().decode('utf-8'))
                raw_text = body['content'][0]['text']
                if json_mode:
                    try:
                        return json.loads(raw_text)
                    except Exception:
                        return self._extract_json_from_text(raw_text)
                return raw_text
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            raise UserError(_("Anthropic API error (%s): %s") % (e.code, error_body))
        except Exception as e:
            raise UserError(_("Failed to communicate with Anthropic API: %s") % str(e))

    def _call_ollama_api(self, user_prompt, system_prompt, json_mode=True):
        base_url = (self.base_url or 'http://localhost:11434').rstrip('/')
        url = f"{base_url}/api/chat"
        headers = {'Content-Type': 'application/json'}
        payload = {
            'model': self.model_name or 'llama3',
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'stream': False,
            'options': {
                'temperature': self.temperature,
            }
        }
        if json_mode:
            payload['format'] = 'json'

        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                body = json.loads(response.read().decode('utf-8'))
                raw_text = body['message']['content']
                if json_mode:
                    try:
                        return json.loads(raw_text)
                    except Exception:
                        return self._extract_json_from_text(raw_text)
                return raw_text
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            raise UserError(_("Ollama API error (%s): %s") % (e.code, error_body))
        except Exception as e:
            raise UserError(_("Failed to communicate with Ollama: %s") % str(e))

    def _extract_json_from_text(self, text):
        """Extracts JSON object from markdown fenced blocks or raw string."""
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        match_arr = re.search(r'\[.*\]', text, re.DOTALL)
        if match_arr:
            try:
                return json.loads(match_arr.group(0))
            except Exception:
                pass
        raise UserError(_("Failed to parse JSON response from AI output: %s") % text[:200])
