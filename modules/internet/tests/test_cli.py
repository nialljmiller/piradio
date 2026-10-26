import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from modules.internet.cli import SubscriptionCLI, CLIUnavailable

class CLITests(unittest.TestCase):
    def test_subscription_process_uses_existing_prompt_and_strips_api_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'fake-cli'
            script.write_text('#!/usr/bin/python3\nimport os,sys,json\nassert "GEMINI_API_KEY" not in os.environ\nassert "FISH_API_KEY" not in os.environ\nassert any("facts only" in a for a in sys.argv)\nprint(json.dumps({"script":"A factual bulletin", "source_ids":["a"]}))\n')
            script.chmod(0o755)
            config={'state_dir':directory,'text_provider':'grok-cli','grok_cli_path':str(script)}
            budget=Mock()
            with patch.dict(os.environ,{'GEMINI_API_KEY':'secret','FISH_API_KEY':'secret'}):
                result=SubscriptionCLI(config,budget).request('text',{'system_instruction':'facts only','input':''})
            budget.reserve.assert_called_once()
            self.assertIn('A factual bulletin',result['steps'][0]['content'][0]['text'])

    def test_missing_executable_gives_fallback_error(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'state_dir':directory,'text_provider':'grok-cli','grok_cli_path':'/missing/cli'}
            with self.assertRaises(CLIUnavailable):
                SubscriptionCLI(config,Mock()).request('text',{'system_instruction':'facts','input':'reports'})

    def test_timeout_kills_process(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'fake-cli'; script.write_text('#!/usr/bin/python3\nimport time\ntime.sleep(5)\n'); script.chmod(0o755)
            config={'state_dir':directory,'text_provider':'grok-cli','grok_cli_path':str(script),'cli_timeout_seconds':0.05}
            with self.assertRaises(CLIUnavailable):
                SubscriptionCLI(config,Mock()).request('text',{'system_instruction':'facts','input':'reports'})

    def test_random_choice_is_made_for_each_request(self):
        from modules.internet.worker import text_provider
        with patch('random.choice',side_effect=['grok-cli','gemini-cli']):
            self.assertEqual(text_provider({'text_provider':'random-cli'},Mock()).name,'grok-cli')
            self.assertEqual(text_provider({'text_provider':'random-cli'},Mock()).name,'gemini-cli')

    def test_google_native_cli_envelope_and_model_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'fake-agy'
            script.write_text('#!/usr/bin/python3\nimport json,sys\nassert "--model" in sys.argv\nassert "--disable-slash-commands" in sys.argv\nprint(json.dumps({"status":"SUCCESS","response":"{\\\"sections\\\":[]}"}))\n')
            script.chmod(0o755)
            config={'state_dir':directory,'text_provider':'gemini-cli','gemini_cli_kind':'antigravity','gemini_cli_path':str(script)}
            result=SubscriptionCLI(config,Mock()).request('text',{'system_instruction':'facts','input':'reports'})
            self.assertEqual(result['steps'][0]['content'][0]['text'],'{"sections":[]}')

    def test_empty_google_response_is_not_successful_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'fake-agy'
            script.write_text('#!/usr/bin/python3\nprint(\'{"status":"SUCCESS","response":""}\')\n');script.chmod(0o755)
            config={'state_dir':directory,'text_provider':'gemini-cli','gemini_cli_kind':'antigravity','gemini_cli_path':str(script)}
            with self.assertRaises(CLIUnavailable):
                SubscriptionCLI(config,Mock()).request('text',{'system_instruction':'facts','input':'reports'})

    def test_random_selection_skips_temporarily_unavailable_cli(self):
        import time
        from modules.internet.common import atomic_json
        from modules.internet.worker import text_provider
        with tempfile.TemporaryDirectory() as directory:
            atomic_json(Path(directory)/'text-unavailable-gemini-cli.json',{'until':time.time()+900})
            with patch('random.choice',return_value='grok-cli') as choose:
                writer=text_provider({'text_provider':'random-cli','state_dir':directory},Mock())
            self.assertEqual(writer.name,'grok-cli')
            self.assertEqual(choose.call_args.args[0],['grok-cli'])
