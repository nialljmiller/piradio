import json
import os
import unittest
from unittest.mock import Mock, patch
from modules.internet.worker import text_provider, Gemini
from modules.internet.grok import Grok

class GrokTests(unittest.TestCase):
    def test_selects_grok_without_gemini_key(self):
        with patch.dict(os.environ, {'XAI_API_KEY':'test'}, clear=True):
            self.assertIsInstance(text_provider({'text_provider':'grok'},Mock()),Grok)
            with self.assertRaises(ValueError):
                text_provider({'text_provider':'gemini'},Mock())

    def test_request_is_bounded_and_uses_supplied_prompt_without_tools(self):
        with patch.dict(os.environ, {'XAI_API_KEY':'test'}, clear=True):
            budget=Mock(); provider=Grok({},budget)
            response=Mock(); response.read.return_value=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"sections":[]}'}}]}).encode()
            response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
            with patch('urllib.request.urlopen',return_value=response) as call:
                result=provider.request('text',{'generation_config':{'max_output_tokens':400},'system_instruction':'facts only','input':'reports'})
            request=call.call_args.args[0]; body=json.loads(request.data)
            self.assertEqual(request.full_url,'https://api.x.ai/v1/chat/completions')
            self.assertEqual(body['messages'][1]['content'],'reports')
            self.assertNotIn('tools',body)
            self.assertEqual(body['reasoning_effort'],'low')
            self.assertEqual(body['max_tokens'],1536)
            budget.reserve.assert_called_once()
            self.assertEqual(result['status'],'completed')

    def test_missing_key_and_incomplete_response_rejected(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError): Grok({},Mock())
        with patch.dict(os.environ,{'XAI_API_KEY':'test'},clear=True):
            provider=Grok({},Mock())
            response=Mock(); response.read.return_value=b'{"choices":[{"finish_reason":"length"}]}'
            response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
            with patch('urllib.request.urlopen',return_value=response), self.assertRaises(ValueError):
                provider.request('text',{'generation_config':{'max_output_tokens':400},'system_instruction':'facts','input':'reports'})
