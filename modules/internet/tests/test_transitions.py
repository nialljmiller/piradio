import tempfile
import unittest
from pathlib import Path
from modules.internet.common import load_config
from modules.internet.daypart import transition_pool
from unittest.mock import patch

class TransitionTests(unittest.TestCase):
    def test_period_specific_and_safe_shared_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(Path(__file__).resolve().parents[1]/'config.example.json')
            shared = root/'pirate.mp3'; shared.write_bytes(b'audio')
            for name, period in config['day_schedule']['periods'].items():
                folder=root/name; folder.mkdir(); period['transition_folder']=str(folder)
            evening=root/'evening'/'GTA.mp3'; evening.write_bytes(b'audio')
            night=root/'night'/'Fallout.mp3'; night.write_bytes(b'audio')
            for name in ('morning','day'):
                with patch('modules.internet.daypart.current_period',return_value=name):
                    self.assertEqual(transition_pool(config,str(root)),[str(shared)])
            with patch('modules.internet.daypart.current_period',return_value='evening'):
                self.assertEqual(transition_pool(config,str(root)),[str(evening)])
            with patch('modules.internet.daypart.current_period',return_value='night'):
                self.assertEqual(transition_pool(config,str(root)),[str(night)])
            config['day_schedule']['enabled']=False
            self.assertEqual(transition_pool(config,str(root)),[str(shared)])
