import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('downloader', Path(__file__).resolve().parents[3]/'scripts'/'yt-mp3.py')
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)


class DownloaderTests(unittest.TestCase):
    def test_links_normalise_and_ignore_playlist_and_tracking(self):
        for url in ('youtu.be/BaW_jenozKc?si=abc',
                    'https://www.youtube.com/watch?v=BaW_jenozKc&list=123',
                    'https://music.youtube.com/watch?v=BaW_jenozKc',
                    'https://m.youtube.com/shorts/BaW_jenozKc',
                    'https://youtube.com/live/BaW_jenozKc',
                    '"https://www.youtube.com/watch?v=BaW_jenozKc\\&t=30"'):
            self.assertEqual(downloader.parse_link(url), 'https://www.youtube.com/watch?v=BaW_jenozKc')

    def test_invalid_links_rejected(self):
        for url in ('https://youtube.com.evil.test/watch?v=BaW_jenozKc',
                    'https://youtube.com/playlist?list=123', 'https://youtu.be/short',
                    'file:///tmp/test', 'https://evil@youtube.com/watch?v=BaW_jenozKc'):
            with self.assertRaises(ValueError):
                downloader.parse_link(url)

    def test_score_validation_and_default(self):
        with patch('builtins.input', side_effect=['no', '-1', '101', '']):
            self.assertEqual(downloader.score('Energy'), 50)
        with patch('builtins.input', return_value='83'):
            self.assertEqual(downloader.score('Organics'), 83)

    def test_publishes_completed_file_with_default_scores_and_keeps_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)/'music'; folder.mkdir()
            def fake(url, temporary):
                audio = Path(temporary)/'song [BaW_jenozKc].mp3'
                audio.write_bytes(b'complete audio')
                return audio
            with patch.object(downloader, 'download', side_effect=fake), patch('builtins.input', side_effect=['','']):
                downloader.import_song(folder, 'url')
            audio = folder/'song [BaW_jenozKc].mp3'
            self.assertEqual(audio.read_bytes(), b'complete audio')
            with (folder/'song_attributes.csv').open() as source:
                self.assertEqual(list(csv.reader(source)), [[str(audio),'50','50']])
            with patch.object(downloader, 'download', side_effect=fake), patch('builtins.input') as ask:
                downloader.import_song(folder, 'url')
                ask.assert_not_called()
            self.assertFalse(list(folder.glob('.import-*')))

    def test_loop_survives_failure_until_empty_link(self):
        with patch('sys.argv', ['yt-mp3.py']), patch.object(downloader, 'load_config', return_value={}), \
             patch.object(downloader, 'choose_folder', return_value=Path('/example')), \
             patch.object(downloader, 'import_song', side_effect=[RuntimeError('network'), None]) as add, \
             patch('builtins.input', side_effect=['https://youtu.be/BaW_jenozKc','https://youtu.be/BaW_jenozKc','']):
            self.assertEqual(downloader.main(), 0)
            self.assertEqual(add.call_count, 2)

    def test_noninteractive_import_sets_requested_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/'music';folder.mkdir()
            def fake(url,temporary):
                p=Path(temporary)/'album [BaW_jenozKc].mp3';p.write_bytes(b'complete');return p
            with patch.object(downloader,'download',side_effect=fake),patch('builtins.input') as ask:
                target=downloader.import_song(folder,'url',30,50,prefix='macroblank')
            ask.assert_not_called()
            with (folder/'song_attributes.csv').open() as source:
                self.assertEqual(list(csv.reader(source)),[[str(target),'30','50']])

    def test_batch_continues_after_failure_and_resumes_without_duplicates(self):
        import argparse,json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);queue=root/'queue.csv';state=root/'state.json';folder=root/'music'
            queue.write_text('artist,title,youtube_url,duration\nmacroblank,failed,https://youtu.be/BaW_jenozKc,1800\nslowerpace,good,https://youtu.be/jNQXAC9IVRw,1800\n')
            args=argparse.Namespace(batch=str(queue),folder=str(folder),state=str(state),energy=30,organics=50,retry_failed=False)
            def add(dest,url,*args,**kwargs):
                if 'BaW_' in url:raise RuntimeError('unavailable')
                p=dest/'complete.mp3';p.write_bytes(b'music');return p
            with patch('shutil.disk_usage', return_value=argparse.Namespace(free=100*1024**3)), \
                 patch.object(downloader,'import_song',side_effect=add) as importer:
                self.assertEqual(downloader.run_batch(args),0)
                self.assertEqual(importer.call_count,2)
                importer.reset_mock()
                self.assertEqual(downloader.run_batch(args),0)
                importer.assert_not_called()
            self.assertEqual({j['status'] for j in json.loads(state.read_text())['jobs'].values()},{'complete','failed'})
