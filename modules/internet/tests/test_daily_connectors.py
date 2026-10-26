import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from modules.internet.common import atomic_json,read_json
from modules.internet.daily_connectors import refresh,KINDS
from modules.internet.cadence import eligible,reserve

class DailyTests(unittest.TestCase):
    def test_daily_set_appends_and_reuses_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'daily_connectors':True,'state_dir':directory,'voice_model':'m','voice':'v','voice_style':'pirate'}
            voice=Mock();voice.cache_identity.return_value=['voice']
            library={'identity':['voice'],'clips':{k:[{'script':'old '+k,'audio':'old','duration':1}] for k in KINDS}}
            atomic_json(Path(directory)/'connectors.json',library)
            text=Mock();text.name='grok-cli';text.connector_set.return_value={k:'fresh '+k for k in KINDS}
            with patch('modules.internet.daily_connectors.piece',side_effect=lambda c,p,s:{'script':s,'audio':s,'duration':2}) as create:
                refresh(config,text,voice,{'clips':[]})
                refresh(config,text,voice,{'clips':[]})
            text.connector_set.assert_called_once();self.assertEqual(create.call_count,4)
            saved=read_json(Path(directory)/'connectors.json')
            self.assertTrue(all(len(saved['clips'][k])==2 for k in KINDS))

    def test_failed_voice_resumes_without_second_text_request(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'daily_connectors':True,'state_dir':directory}
            voice=Mock();voice.cache_identity.return_value=['voice']
            atomic_json(Path(directory)/'connectors.json',{'identity':['voice'],'clips':{k:[] for k in KINDS}})
            text=Mock();text.name='grok-cli';text.connector_set.return_value={k:'fresh '+k for k in KINDS}
            def generate(c,p,s):
                if s=='fresh weather' and not getattr(generate,'recovered',False):raise RuntimeError('voice unavailable')
                return {'script':s,'audio':s,'duration':1}
            with patch('modules.internet.daily_connectors.piece',side_effect=generate):
                with self.assertRaises(RuntimeError):refresh(config,text,voice,{'clips':[]})
                generate.recovered=True;refresh(config,text,voice,{'clips':[]})
            text.connector_set.assert_called_once()
            self.assertTrue(all(len(v)==1 for v in read_json(Path(directory)/'connectors.json')['clips'].values()))

    def test_eight_section_requests_each_shared_across_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'state_dir':directory,'section_prompt_limits':{'news':8,'weather':8}}
            for i in range(8):
                self.assertEqual(set(eligible(config,{'news':[],'weather':[]})),{'news','weather'})
                reserve(config,['news','weather'])
            self.assertEqual(eligible(config,{'news':[],'weather':[]}),{})
