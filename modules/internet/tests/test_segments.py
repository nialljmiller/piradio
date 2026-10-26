import hashlib
import io
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock

from modules.internet.common import atomic_json, load_config
from modules.internet.player import Relay
from modules.internet.segments import prepare_connectors, render_sections, create_sections, write_sections
from modules.internet.worker import Gemini


class SegmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = load_config(Path(__file__).resolve().parents[1] / 'config.example.json')
        self.config.update(state_dir=self.tmp.name, max_clip_seconds=5, max_bulletin_seconds=30)
        self.voice = Mock()
        self.voice.cache_identity.return_value = ['test-voice']
        def speak(text):
            output = io.BytesIO()
            sample = (int(hashlib.sha256(text.encode()).hexdigest()[:3], 16)).to_bytes(2, 'little')
            with wave.open(output, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(sample * 72000)
            return output.getvalue(), 3
        self.voice.voice.side_effect = speak

    def test_library_cached_long_assembly_and_all_connectors_change_on_replay(self):
        prepare_connectors(self.config, self.voice)
        self.assertEqual(self.voice.voice.call_count, 12)
        prepare_connectors(self.config, self.voice)
        self.assertEqual(self.voice.voice.call_count, 12)
        now = time.time()
        entry = {'id': 'bulletin', 'kind': 'news', 'created': now, 'expires': now+3600,
                 'sources': [], 'sections': [
                     {'kind': k, 'script': k + ' facts', 'sources': [], 'expires': now+3600}
                     for k in ('weather', 'news')]}
        catalog = {'clips': [entry]}
        render_sections(self.config, catalog, self.voice, entry)
        self.assertGreater(entry['duration'], self.config['max_clip_seconds'])
        self.assertEqual(self.voice.voice.call_count, 14)
        relay = Relay(self.config)
        first = relay.choose()
        first['_started_at'] = time.time() - self.config['repeat_after_seconds'] - 1
        relay.mark_played(first)
        self.assertIsNotNone(relay.choose(), 'The repeat interval is measured from start, not finish')
        history = Path(self.tmp.name) / 'play-history.json'
        import json
        record = json.loads(history.read_text())
        record['bulletin']['last_played'] = 0
        atomic_json(history, record)
        second = relay.choose()
        for k in ('intro', 'weather', 'news', 'outro'):
            self.assertNotEqual(first['_connector_indices'][k], second['_connector_indices'][k])
        self.assertNotEqual(first['audio'], second['audio'])
        self.assertEqual(self.voice.voice.call_count, 14)

    def test_unchanged_forecast_renews_without_llm_request(self):
        self.config['rewrite_weather_each_refresh'] = False
        now = time.time()
        forecast = {'id': 'forecast', 'url': 'https://api.weather.gov/forecast',
                    'expires': now+3000, 'topics': ['weather']}
        section = {'kind': 'weather', 'script': 'Cached forecast', 'sources': [forecast], 'expires': now+10}
        news = {'kind': 'news', 'script': 'Cached news', 'sources': [], 'expires': now+5000}
        catalog = {'clips': [], 'seen': ['forecast'], 'sections': {'weather': section, 'news': news}}
        provider = Mock()
        entry = create_sections(self.config, catalog, provider, [forecast], now)
        provider.sections.assert_not_called()
        self.assertEqual(entry['sections'][1]['expires'], now+3000)
        self.assertEqual(entry['sections'][0]['script'], 'Cached news')

    def test_changed_weather_keeps_existing_news_and_requests_only_weather(self):
        now = time.time()
        forecast = {'id': 'new', 'url': 'https://api.weather.gov/f', 'expires': now+3000, 'topics': ['weather']}
        catalog = {'clips': [], 'seen': [], 'sections': {'news': {
            'kind': 'news', 'script': 'Existing news', 'sources': [], 'expires': now+5000}}}
        provider = Mock()
        provider.sections.return_value = [{'kind': 'weather', 'script': 'New forecast', 'source_ids': ['new']}]
        entry = create_sections(self.config, catalog, provider, [forecast], now)
        self.assertEqual(set(provider.sections.call_args.args[0]), {'weather'})
        self.assertEqual(entry['sections'][0]['script'], 'Existing news')

    def test_weather_cannot_use_a_news_source_id(self):
        provider = object.__new__(Gemini)
        provider.config = self.config
        import json
        provider.request = Mock(return_value={'status': 'completed', 'steps': [{
            'type': 'model_output', 'content': [{'type': 'text', 'text': json.dumps({'sections': [{
                'kind': 'weather', 'script': 'Forecast words ' * 20, 'source_ids': ['news-id']}]})}]}]})
        with self.assertRaises(ValueError):
            provider.sections({'weather': [{'id': 'weather-id'}]})

    def test_payment_error_uses_factual_fallback_and_cools_down_requests(self):
        import urllib.error
        provider = Mock()
        provider.key = 'test-only-key'
        provider.sections.side_effect = urllib.error.HTTPError('https://example.com', 402, 'depleted', {}, None)
        groups = {'news': [{'id': 'story', 'source': 'NASA', 'report_date': '2026-10-11',
                            'title': 'A telescope was launched',
                            'excerpt': 'NASA launched a telescope to study distant galaxies.'}]}
        first = write_sections(self.config, provider, groups)
        second = write_sections(self.config, provider, groups)
        self.assertEqual(first, second)
        self.assertEqual(first, [])
        self.assertEqual(provider.sections.call_count, 1)
