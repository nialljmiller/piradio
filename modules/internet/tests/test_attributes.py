import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from modules.internet.attributes import sync_folder, sync_all, guess


class AttributesTests(unittest.TestCase):
    def test_existing_values_preserved_and_only_missing_scored(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            a, b = str(folder/'a.mp3'), str(folder/'b.mp3')
            (folder/'song_attributes.csv').write_text(f'{a},75,20\n')
            scorer = Mock(return_value=(82, 31))
            target = sync_folder(folder, [a, b, b], scorer=scorer)
            scorer.assert_called_once_with(b)
            with target.open() as source:
                self.assertEqual(list(csv.reader(source)), [[a,'75','20'],[b,'82','31']])
            scorer.reset_mock()
            sync_folder(folder, [a,b], scorer=scorer)
            scorer.assert_not_called()

    def test_empty_csv_created_and_failed_audio_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            scorer = Mock(side_effect=ValueError('invalid audio'))
            target = sync_folder(directory, ['broken.mp3'], scorer=scorer)
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(), '')
            scorer = Mock(return_value=(12,34))
            sync_folder(directory, ['broken.mp3'], scorer=scorer)
            scorer.assert_called_once()

    def test_rescore_requires_explicit_request(self):
        with tempfile.TemporaryDirectory() as directory:
            target = sync_folder(directory, ['a'], scorer=lambda p: (70,30))
            sync_folder(directory, ['a'], rescore=True, scorer=lambda p: (10,90))
            self.assertEqual(target.read_text().strip(), 'a,10,90')

    def test_real_short_audio_estimator(self):
        import math, struct, wave
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'short.wav'
            with wave.open(str(path),'wb') as out:
                out.setnchannels(1); out.setsampwidth(2); out.setframerate(8000)
                out.writeframes(b''.join(struct.pack('<h', int(10000*math.sin(i*2*math.pi*440/8000))) for i in range(48000)))
            energy, organics = guess(path)
            self.assertTrue(0 <= energy <= 100)
            self.assertTrue(0 <= organics <= 100)
