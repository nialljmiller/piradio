import array
import json
import shutil
import subprocess
import tempfile
import time
import unittest
import wave
from pathlib import Path

from modules.internet.common import atomic_json
from modules.internet.player import Relay


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg required')
class AudioRelayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.config = json.loads((Path(__file__).parents[1] / 'config.example.json').read_text())
        self.config['state_dir'] = self.tmp.name
        self.music = self.state / 'music.wav'
        self.write_wave(self.music, 176400, 9000)
        self.clip = self.state / 'audio' / 'news.wav'
        self.clip.parent.mkdir()
        self.write_wave(self.clip, 88200, 3000)
        atomic_json(self.state / 'catalog.json', {'clips': [dict(id='test', kind='news', ready=True,
            created=time.time(), expires=time.time()+3600, audio=str(self.clip), duration=2, sources=[])]})

    def write_wave(self, path, frames, value):
        with wave.open(str(path), 'wb') as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(44100)
            out.writeframes(array.array('h', [value] * frames).tobytes())

    def decode(self, relay, inject=True):
        command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                   '-i', str(self.music), '-f', 's16le', '-ac', '1', '-ar', '44100', '-']
        output = self.state / 'output.pcm'
        with output.open('wb') as out:
            code = relay.decode(command, {'stdout': out.fileno(), 'stderr': subprocess.DEVNULL},
                                out.fileno(), 1, inject=inject)
        self.assertEqual(code, 0)
        return output.read_bytes()

    def test_mixing_keeps_music_timeline_and_restores_full_volume(self):
        relay = Relay(self.config)
        relay.next_check = 0
        audio = self.decode(relay)
        self.assertEqual(len(audio), 176400 * 2)
        self.assertEqual(audio[-8192:], array.array('h', [9000] * 4096).tobytes())
        self.assertEqual(audio[88200:88202], array.array('h', [3570]).tobytes())
        history = json.loads((self.state / 'play-history.json').read_text())
        self.assertEqual(history['test']['plays'], 1)

    def test_announcements_pass_through_without_fades_or_bulletins(self):
        relay = Relay(self.config)
        relay.next_check = 0
        self.assertEqual(self.decode(relay, inject=False), array.array('h', [9000] * 176400).tobytes())
        self.assertFalse((self.state / 'play-history.json').exists())

    def test_corrupt_catalog_keeps_original_music_playing(self):
        (self.state / 'catalog.json').write_text('{broken')
        relay = Relay(self.config)
        relay.next_check = 0
        self.assertEqual(self.decode(relay), array.array('h', [9000] * 176400).tobytes())

    def test_weather_only_bulletin_preserves_durable_news_rotation(self):
        relay = Relay(self.config)
        clip = dict(id='news', sections=[{'kind':'news'}], _connector_indices={
            '_stories':['a','b'], '_story_history':['c','d','a','b'], 'intro':0})
        relay.remember_news_selection(clip)
        # Selection is durable even before a decoder finishes or across restart.
        saved = json.loads((self.state/'play-history.json').read_text())
        self.assertEqual(saved['_connectors']['indices']['_story_history'], ['c','d','a','b'])
        Relay(self.config).mark_played(dict(id='weather', sections=[{'kind':'weather'}],
                                           _connector_indices={'intro':1}))
        saved = json.loads((self.state/'play-history.json').read_text())
        self.assertEqual(saved['_connectors']['indices']['_stories'], ['a','b'])
        self.assertEqual(saved['_connectors']['indices']['_story_history'], ['c','d','a','b'])
        self.assertEqual(saved['_connectors']['indices']['intro'], 1)
