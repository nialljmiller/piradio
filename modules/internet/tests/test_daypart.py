import csv
import datetime as dt
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from modules.internet.common import atomic_json, load_config
from modules.internet.daypart import current_period, effective_config, music_pool, validate, attach_music
from modules.internet.player import Relay
from modules.internet.segments import prepare_connectors, render_sections


class DayPartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = load_config(Path(__file__).resolve().parents[1] / 'config.example.json')
        self.config['state_dir'] = str(self.root / 'state')
        self.config['day_schedule']['timezone'] = 'America/New_York'
        for name, period in self.config['day_schedule']['periods'].items():
            folder = self.root / name
            folder.mkdir()
            period['music_folder'] = str(folder)

    def at(self, hour, minute=0):
        return dt.datetime(2026, 1, 15, hour, minute, tzinfo=ZoneInfo('America/New_York')).timestamp()

    def test_boundaries_cover_midnight_without_overlap(self):
        for hour, minute, expected in ((4,59,'night'), (5,0,'morning'), (9,59,'morning'),
                (10,0,'day'), (16,59,'day'), (17,0,'evening'), (18,59,'evening'),
                (19,0,'night'), (0,0,'night'), (23,59,'night')):
            self.assertEqual(current_period(self.config, self.at(hour, minute)), expected)

    def test_timezone_tracks_daylight_saving_without_changing_system_clock(self):
        winter = dt.datetime(2026,1,15,9,tzinfo=dt.timezone.utc).timestamp()
        summer = dt.datetime(2026,7,15,9,tzinfo=dt.timezone.utc).timestamp()
        self.assertEqual(current_period(self.config, winter), 'night')
        self.assertEqual(current_period(self.config, summer), 'morning')

    def test_empty_period_falls_back_without_leaking_other_period_music(self):
        main = self.root / 'main.mp3'
        main.write_bytes(b'music')
        (self.root / 'night' / 'night.mp3').write_bytes(b'music')
        folder, songs = music_pool(self.config, str(self.root), self.at(6))
        self.assertEqual(songs, [str(main)])
        morning = self.root / 'morning' / 'morning.mp3'
        morning.write_bytes(b'music')
        self.assertEqual(music_pool(self.config, str(self.root), self.at(6))[1], [str(morning)])
        self.config['day_schedule']['enabled'] = False
        self.assertEqual(music_pool(self.config, str(self.root), self.at(6))[1], [str(main)])

    def test_independent_intervals_and_disabled_schedule(self):
        morning = self.config['day_schedule']['periods']['morning']
        morning.update(news_play_interval_seconds=3600, weather_play_interval_seconds=600,
                       news_refresh_interval_seconds=7200, weather_refresh_interval_seconds=1800)
        effective = effective_config(self.config, self.at(6))
        self.assertEqual(effective['interval_seconds'], 600)
        self.assertEqual(effective['news_play_interval_seconds'], 3600)
        self.assertEqual(effective['news_generation_interval_seconds'], 7200)
        self.assertEqual(effective['weather_generation_interval_seconds'], 1800)
        self.config['day_schedule']['enabled'] = False
        self.assertEqual(effective_config(self.config, self.at(6))['interval_seconds'], self.config['interval_seconds'])

    def test_invalid_gap_or_overlap_rejected(self):
        self.config['day_schedule']['periods']['morning']['end'] = '11:00'
        with self.assertRaises(ValueError):
            validate(self.config)

    def test_music_switches_between_songs_using_original_ordering_and_preserves_attributes(self):
        config_path = self.root / 'config.json'
        atomic_json(config_path, self.config)
        attributes = self.root / 'song_attributes.csv'
        attributes.write_text('/pirateradio/main.mp3,75,20\n')
        first, second = '/pirateradio/main.mp3', str(self.root / 'night' / 'new.mp3')
        namespace = {'CSV_FILE_PATH': str(attributes), 'shuffle': False, 'play_stereo': True,
                     'music_pipe_w': 42, 'random': Mock(), 'load_song_data': Mock(return_value={}),
                     'reorder_file_list': Mock(side_effect=lambda files, data: files), 'subprocess': Mock()}
        calls = 0
        def pool(config):
            return ('/pirateradio', [first]) if calls == 0 else (str(self.root/'night'), [second])
        def play(command, **kwargs):
            nonlocal calls
            calls += 1
        namespace['subprocess'].call.side_effect = play
        attach_music(namespace, str(config_path))
        with patch('modules.internet.daypart.music_pool', side_effect=pool), \
             patch('modules.internet.daypart.sync_folder', return_value=attributes) as sync, \
             patch('modules.internet.daypart.transition_pool', return_value=[]):
            namespace['play_songs']([first], [])
        songs = [call.args[0][2] for call in namespace['subprocess'].call.call_args_list]
        self.assertEqual(songs, [first, second])
        namespace['reorder_file_list'].assert_called_once()
        with attributes.open() as source:
            rows = list(csv.reader(source))
        self.assertIn([first,'75','20'], rows)
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(sync.call_args.args[1], [second])

    def test_news_and_weather_can_be_played_independently(self):
        # Synthetic cached pieces, with no network or text generation.
        import io, wave
        provider = Mock()
        provider.cache_identity.return_value = ['test']
        def voice(script):
            out = io.BytesIO()
            with wave.open(out, 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
                wav.writeframes(bytes(3*8000*2))
            return out.getvalue(), 3
        provider.voice.side_effect = voice
        for period in self.config['day_schedule']['periods'].values():
            period.update(news_play_interval_seconds=3600, weather_play_interval_seconds=600)
        prepare_connectors(self.config, provider)
        now = time.time()
        clip = dict(id='board', kind='news', created=now, expires=now+7200, sources=[],
                    sections=[dict(kind=k, script=k, sources=[], expires=now+7200) for k in ('weather','news')])
        render_sections(self.config, {'clips':[clip]}, provider, clip)
        atomic_json(Path(self.config['state_dir']) / 'play-history.json', {
            '_section_plays': {'news': now-1200, 'weather': now-1200},
            'board': {'last_played': now-1200, 'plays': 1}})
        selected = Relay(self.config).choose()
        self.assertEqual([s['kind'] for s in selected['sections']], ['weather'])
        self.assertEqual(len(selected['piece_choices']), 4)

    def test_news_refresh_does_not_fetch_weather_before_its_interval(self):
        self.config['news_feed_interval_seconds'] = 3600
        from modules.internet.worker import refresh
        self.config['enabled'] = True
        for period in self.config['day_schedule']['periods'].values():
            period.update(news_refresh_interval_seconds=3600, weather_refresh_interval_seconds=21600)
        now = time.time()
        atomic_json(Path(self.config['state_dir']) / 'catalog.json', {
            'clips': [], 'seen': [], 'last_generation_attempt': now-600,
            'last_news_generation': now-3700, 'last_weather_generation': now-600})
        report = dict(id='local', title='Local report', topics=['NC Triangle'],
                      published=now-60, url='https://wral.com/a')
        provider = Mock()
        provider.sections.return_value = [dict(kind='news', script='Fresh news', source_ids=['local'])]
        with patch('modules.internet.worker.collect', return_value=[report]) as collect, patch(
                'modules.internet.worker.Gemini', return_value=provider), patch(
                'modules.internet.worker.voice_provider'), patch('modules.internet.worker.render'):
            refresh(self.config)
        self.assertFalse(collect.call_args.kwargs['include_weather'])
        self.assertEqual(set(provider.sections.call_args.args[0]), {'news'})
