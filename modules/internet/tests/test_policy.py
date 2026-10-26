import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from modules.internet.common import atomic_json, load_config, source_allowed
from modules.internet.player import PlaybackProxy, Relay
from modules.internet.worker import Gemini, refresh, rank_reports

EXAMPLE = Path(__file__).resolve().parents[1] / 'config.example.json'


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = load_config(EXAMPLE)
        self.config['state_dir'] = self.tmp.name

    def test_bans_cover_subdomains_without_blocking_similar_names(self):
        self.config['banned_news_sources'] = ['example.com']
        self.assertFalse(source_allowed(self.config, 'https://news.example.com/article'))
        self.assertTrue(source_allowed(self.config, 'https://notexample.com/article'))
        self.assertFalse(source_allowed(self.config, 'file:///etc/passwd'))

    def test_news_plays_twice_then_stops(self):
        self.config['max_repeats_per_news_recording'] = 1
        state = Path(self.tmp.name)
        audio = state / 'audio' / 'clip.wav'
        audio.parent.mkdir()
        audio.touch()
        clip = dict(id='test', ready=True, expires=time.time()+3600,
                    audio=str(audio), duration=2, kind='news', created=time.time(), sources=[])
        atomic_json(state / 'catalog.json', {'clips': [clip]})
        relay = Relay(self.config)
        self.assertEqual(relay.choose(), clip)
        relay.mark_played(clip)
        self.assertIsNone(relay.choose())
        atomic_json(state / 'play-history.json', {'test': {'last_played': 0, 'plays': 1}})
        self.assertEqual(relay.choose(), clip)
        relay.mark_played(clip)
        atomic_json(state / 'play-history.json', {'test': {'last_played': 0, 'plays': 2}})
        self.assertIsNone(relay.choose())

    def test_announcement_does_not_allow_injection(self):
        relay = Mock()
        proxy = PlaybackProxy(Mock(), relay, {'music_pipe_w': 42})
        command = ['ffmpeg', '-i', '/pirateradio/announce/pirate.mp3',
                   '-f', 's16le', '-ac', '2', '-']
        proxy.call(command, stdout=42)
        self.assertFalse(relay.decode.call_args.kwargs['inject'])
        command[2] = '/pirateradio/song.mp3'
        proxy.call(command, stdout=42)
        self.assertTrue(relay.decode.call_args.kwargs['inject'])

    def test_disabled_worker_does_not_create_state_or_call_api(self):
        self.config['state_dir'] = str(Path(self.tmp.name) / 'unused')
        refresh(self.config)
        self.assertFalse(Path(self.config['state_dir']).exists())

    def test_prompt_contains_identity_and_style(self):
        provider = object.__new__(Gemini)
        provider.config = self.config
        provider.request = Mock(return_value={'status': 'completed', 'steps': [
            {'type': 'model_output', 'content': [{'type': 'text', 'text': json.dumps({
                'script': 'This is Captain Niall with Pirate Radio and here is your news update. '
                          'The supplied report says a new space mission has been announced.',
                'source_ids': ['source']})}]}]})
        provider.script([{'id': 'source'}])
        prompt = json.loads(provider.request.call_args.args[1]['input'])
        for setting in ('host_name', 'station_name', 'voice_style'):
            self.assertEqual(prompt[setting], self.config[setting])

    def test_local_and_science_stay_above_routine_world_even_after_recent_coverage(self):
        now = time.time()
        reports = [dict(id=k, title='A routine report', topics=[topic],
                        published=now-60, url='https://bbc.com/article')
                   for k, topic in [('world', 'world news'), ('science', 'science'), ('local', 'NC Triangle')]]
        ranked = rank_reports(reports, self.config, {'NC Triangle', 'science'}, now)
        self.assertEqual([r['id'] for r in ranked], ['local', 'science', 'world'])

    def test_fresh_major_world_event_overrides_local_but_old_breaking_does_not(self):
        now = time.time()
        local = dict(id='local', title='Local council report', topics=['NC Triangle'],
                     published=now-100, url='https://wral.com/a')
        world = dict(id='world', title='Breaking: major earthquake triggers tsunami warning',
                     topics=['world news'], published=now-60, url='https://bbc.com/a')
        self.assertEqual(rank_reports([local, world], self.config, set(), now)[0]['id'], 'world')
        world['published'] = now - 18000
        self.assertEqual(rank_reports([local, world], self.config, set(), now)[0]['id'], 'local')

    def test_urgent_unseen_report_can_refresh_before_regular_generation_interval(self):
        self.config['news_feed_interval_seconds'] = 0  # Legacy opt-out of feed gating.
        now = time.time()
        self.config['enabled'] = True
        atomic_json(Path(self.tmp.name) / 'catalog.json', {'clips': [], 'seen': [],
            'last_generation_attempt': now, 'last_news_generation': now})
        report = dict(id='urgent', title='Breaking: tsunami warning issued', topics=['world news'],
                      published=now-60, url='https://bbc.com/a')
        provider = Mock()
        provider.sections.return_value = [{'kind': 'news', 'script': 'Source report', 'source_ids': ['urgent']}]
        with patch('modules.internet.worker.collect', return_value=[report]), patch(
                'modules.internet.worker.Gemini', return_value=provider), patch(
                'modules.internet.worker.voice_provider'), patch('modules.internet.worker.render') as render:
            refresh(self.config)
        render.assert_called_once()

    def test_three_hour_feed_gate_includes_empty_fetch_and_keeps_weather_independent(self):
        from modules.internet.worker import collect
        self.config.update(enabled=True,news_feed_interval_seconds=10800,
                           segmented_bulletins=True,news_story_pool=True,daily_connectors=False)
        now=time.time()
        atomic_json(Path(self.tmp.name)/'catalog.json',dict(clips=[],seen=[],
            last_news_feed_check=now,last_news_generation=now,last_weather_generation=now))
        for advance,due in [(60,False),(10799,False),(10800,True),(10860,False)]:
            with patch('modules.internet.worker.time.time',return_value=now+advance), patch(
                    'modules.internet.worker.collect',return_value=[]) as fetch:
                refresh(self.config)
                self.assertEqual(fetch.call_args.kwargs['include_news'],due)
        catalog=json.loads((Path(self.tmp.name)/'catalog.json').read_text())
        self.assertEqual(catalog['last_news_feed_check'],now+10800)
        with patch('modules.internet.worker.urllib.request.urlopen') as http, patch(
                'modules.internet.worker.weather_report',return_value=None) as weather:
            collect(self.config,{},include_news=False,include_weather=True)
            http.assert_not_called()
            weather.assert_called_once()


if __name__ == '__main__':
    unittest.main()
