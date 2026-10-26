import io
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from modules.internet.fish import Fish, FREE_MODEL, amplify_pcm
from modules.internet.worker import BudgetExceeded


def audio(seconds=3, streamed=False):
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(bytes(seconds * 24000 * 2))
    result = out.getvalue()
    if streamed:
        result = result[:40] + b'\xff\xff\xff\xff' + result[44:]
    return result


class FishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        reference = Path(self.tmp.name) / 'reference.wav'
        reference.write_bytes(audio())
        self.config = {'fish_reference_audio': str(reference),
                       'fish_reference_text': 'Ahoy matey!', 'max_clip_seconds': 60}
        with patch.dict(os.environ, {'FISH_API_KEY': 'test-key'}):
            self.budget = Mock()
            self.provider = Fish(self.config, self.budget)
        self.msgpack = Mock()
        self.msgpack.packb.return_value = b'encoded-reference'

    def test_streaming_wav_gets_real_duration_and_finite_cached_header(self):
        with patch.dict('sys.modules', {'msgpack': self.msgpack}), patch(
                'urllib.request.urlopen', return_value=io.BytesIO(audio(streamed=True))):
            data, duration = self.provider.voice('Ahoy, this is Reginald Radio.')
        self.assertEqual(duration, 3)
        with wave.open(io.BytesIO(data)) as wav:
            self.assertEqual(wav.getnframes(), 72000)

    def test_request_always_pins_free_model_and_includes_reference(self):
        self.config['fish_model'] = 'paid-or-misspelled-model'
        with patch.dict('sys.modules', {'msgpack': self.msgpack}), patch(
                'urllib.request.urlopen', return_value=io.BytesIO(audio())) as request:
            self.provider.voice('Ahoy!')
        self.assertEqual(request.call_args.args[0].get_header('Model'), FREE_MODEL)
        body = self.msgpack.packb.call_args.args[0]
        self.assertEqual(body['references'][0]['text'], 'Ahoy matey!')
        self.assertIsInstance(body['references'][0]['audio'], bytes)

    def test_budget_exhaustion_prevents_network_request(self):
        self.budget.reserve.side_effect = BudgetExceeded('limit reached')
        with patch.dict('sys.modules', {'msgpack': self.msgpack}), patch('urllib.request.urlopen') as request:
            with self.assertRaises(BudgetExceeded):
                self.provider.voice('Ahoy!')
        request.assert_not_called()

    def test_multiple_references_and_cache_changes_when_any_reference_changes(self):
        self.config['fish_references'] = [
            {'audio': self.config['fish_reference_audio'], 'text': 'Ahoy matey!'},
            {'audio': self.config['fish_reference_audio'], 'text': 'Arrr, all hands on deck!'}]
        original = self.provider.cache_identity()
        with patch.dict('sys.modules', {'msgpack': self.msgpack}), patch(
                'urllib.request.urlopen', return_value=io.BytesIO(audio())):
            self.provider.voice('Ahoy!')
        self.assertEqual(len(self.msgpack.packb.call_args.args[0]['references']), 2)
        self.config['fish_references'][1]['text'] = 'A different transcript'
        self.assertNotEqual(original, self.provider.cache_identity())

    def test_free_window_expiry_stops_requests_before_budget_or_network(self):
        import datetime as dt
        future = dt.datetime(2026, 12, 1, tzinfo=dt.timezone.utc)
        with patch('modules.internet.fish.dt.datetime') as clock, patch('urllib.request.urlopen') as request:
            clock.now.return_value = future
            with self.assertRaises(ValueError):
                self.provider.voice('Ahoy!')
        request.assert_not_called()
        self.budget.reserve.assert_not_called()

    def test_speech_gain_preserves_duration_and_limits_peaks(self):
        import array
        pcm = array.array('h', [3000] * 24000 + [32000] * 24000).tobytes()
        result = amplify_pcm(pcm, 24000, 1, 1.25)
        values = array.array('h')
        values.frombytes(result)
        self.assertEqual(len(result), len(pcm))
        self.assertAlmostEqual(values[12000], 3750, delta=2)
        self.assertLessEqual(max(values), 32114)
