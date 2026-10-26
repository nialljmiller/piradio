"""xAI text adapter sharing Gemini's factual prompt and output validation."""
import json
import logging
import os
import urllib.request
from .worker import Gemini

LOG = logging.getLogger('piradio-internet.grok')


class Grok(Gemini):
    name = 'grok'

    def __init__(self, config, budget):
        self.config, self.budget = config, budget
        self.key = os.environ.get('XAI_API_KEY', '')
        if not self.key:
            raise ValueError('XAI_API_KEY is not configured')

    def request(self, kind, body):
        if kind != 'text':
            raise ValueError('Grok is configured for text only')
        cap = self.config.get('grok_max_tokens', 1536)
        payload = json.dumps({
            'model': self.config.get('grok_text_model', 'grok-4.7'),
            'messages': [{'role': 'system', 'content': body['system_instruction']},
                         {'role': 'user', 'content': body['input']}],
            'response_format': {'type': 'json_object'},
            'max_tokens': cap, 'reasoning_effort': 'low', 'temperature': 0.5, 'stream': False,
        }, ensure_ascii=False).encode()
        # Shared global budget; no search tools, SDK, automatic retries or provider switching.
        self.budget.reserve('text', len(payload) + cap + 512)
        from .cadence import reserve
        reserve(self.config, getattr(self, '_section_categories', []))
        request = urllib.request.Request('https://api.x.ai/v1/chat/completions', data=payload,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key})
        with urllib.request.urlopen(request, timeout=75) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Oversize Grok response')
        result = json.loads(raw)
        choices = result.get('choices', [])
        if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
            raise ValueError('Grok response did not complete')
        content = choices[0].get('message', {}).get('content')
        if not isinstance(content, str):
            raise ValueError('Grok response contains no text')
        LOG.info('Grok text call completed; provider usage=%s', result.get('usage', {}))
        return {'status': 'completed', 'steps': [{'type': 'model_output',
                'content': [{'type': 'text', 'text': content}]}]}
