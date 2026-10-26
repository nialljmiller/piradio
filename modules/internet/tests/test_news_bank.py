import json
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from modules.internet.common import atomic_json
from modules.internet.news_bank import add_stories, choose_pair, news_section
from modules.internet.segments import create_sections, prepare_connectors, render_sections, assemble
from modules.internet.worker import Gemini
from modules.internet.tests import test_segments as fixtures


class NewsBankTests(unittest.TestCase):
    def setUp(self):
        fixtures.SegmentTests.setUp(self)
        self.config['news_budget_aware'] = False
        self.config.pop('news_stories_per_refresh', None)
    def test_one_story_refresh_reuses_audio_and_randomises_without_calls(self):
        self.config['news_story_pool'] = True
        self.config['news_story_ttl_seconds'] = 43200
        prepare_connectors(self.config, self.voice)
        self.voice.reset_mock()
        now = time.time()
        reports = [dict(id=str(i), title='Report '+str(i), published=now,
                        url='https://example.com/'+str(i), topics=['science']) for i in range(3)]
        catalog = dict(clips=[], seen=[], news_stories=[])
        provider = Mock();provider.config = self.config
        def result(ids):return [dict(kind='news', script='Unused', source_ids=ids,
            stories=[dict(script='Standalone story '+i,source_ids=[i]) for i in ids])]
        provider.sections.return_value = result(['0','1'])
        first = create_sections(self.config,catalog,provider,reports,now)
        self.assertEqual(provider.config['_news_story_count'],2)
        # Simulate a restart after durable script commit, before voice rendering.
        catalog = json.loads(json.dumps(catalog))
        first = catalog['clips'][-1]
        render_sections(self.config,catalog,self.voice,first)
        self.assertEqual(self.voice.voice.call_count,2)
        provider.sections.return_value = result(['2'])
        second = create_sections(self.config,catalog,provider,reports,now+1)
        self.assertEqual(provider.config['_news_story_count'],1)
        self.assertEqual([r['id'] for r in provider.sections.call_args.args[0]['news']],['2'])
        render_sections(self.config,catalog,self.voice,second)
        self.assertEqual(self.voice.voice.call_count,3)
        chosen = assemble(self.config,second,0)
        previous = chosen['_connector_indices']
        chosen2 = assemble(self.config,second,1,previous)
        self.assertEqual(len(set(chosen2['_connector_indices']['_stories'])),2)
        self.assertNotEqual(previous['_stories'],chosen2['_connector_indices']['_stories'])
        self.assertEqual(self.voice.voice.call_count,3)
        # A ban or expiry cannot be bypassed by a cached story piece.
        catalog['news_stories'][0]['expires']=now-1
        self.config['banned_news_sources']=['example.com']
        self.assertIsNone(news_section(self.config,catalog,ready=True))
        with self.assertRaises(ValueError):choose_pair(self.config,catalog['news_stories'])

    def test_overnight_reports_seed_pool_and_expired_reports_do_not_advance_refresh(self):
        from modules.internet.news_bank import valid_stories
        self.config.update(news_story_pool=True, news_story_ttl_seconds=86400)
        now = time.time()
        reports = [dict(id=str(i), title='Report', published=now-13*3600,
                        url='https://example.com/'+str(i), topics=['science']) for i in range(2)]
        catalog = dict(clips=[], seen=[], news_stories=[], last_news_generation=123)
        provider = Mock();provider.config=self.config
        provider.sections.return_value = [dict(kind='news', script='Two stories', source_ids=['0','1'],
            stories=[dict(script='Story '+str(i),source_ids=[str(i)]) for i in range(2)])]
        result=create_sections(self.config,catalog,provider,reports,now)
        self.assertIsNotNone(result)
        self.assertEqual(len(valid_stories(self.config,catalog,now)),2)
        self.assertEqual(catalog['last_news_generation'],now)
        # A model cannot extend old source dates, even if it returns expired IDs.
        catalog=dict(clips=[],seen=[],news_stories=[],last_news_generation=123)
        for r in reports:r['published']=now-25*3600
        provider.sections.return_value=[]
        self.assertIsNone(create_sections(self.config,catalog,provider,reports,now))
        self.assertEqual(catalog['last_news_generation'],123)
        self.assertEqual(catalog['news_stories'],[])

    def test_model_accepts_one_new_story_only_in_pool_mode(self):
        self.config.update(news_story_pool=True,_news_story_count=1)
        provider = object.__new__(Gemini); provider.config=self.config
        story = 'NASA announced a new space telescope to study distant galaxies, according to its October fourteenth report. The instrument will observe X rays to help astronomers understand those galaxies.'
        provider.request=Mock(return_value={'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':json.dumps({'sections':[dict(kind='news',script=story,source_ids=['a'],stories=[dict(script=story,source_ids=['a'])])]})}]}]})
        result=provider.sections({'news':[{'id':'a'}]})
        self.assertEqual(len(result[0]['stories']),1)
        instruction=provider.request.call_args.args[1]['system_instruction']
        self.assertNotIn('at least two distinct',instruction)
        self.assertIn('exactly 1',instruction)

    def test_rotation_preserves_gap_and_variety_across_bulletins(self):
        import random
        for count in (2, 3, 4, 8, 12):
            stories = [dict(id=str(i), expires=time.time()+3600,
                            sources=[], piece={'audio': 'cached'}) for i in range(count)]
            history = []
            rng = random.Random(12)
            for _ in range(100):
                pair = choose_pair(self.config, stories, history[-24:], rng)
                for story in pair:
                    gap = 2 if count >= 4 else 1
                    self.assertNotIn(story['id'], history[-gap:])
                    history.append(story['id'])

    def test_expiry_and_new_stories_preserve_boundary_rule(self):
        import random
        stories = [dict(id=str(i), expires=time.time()+3600,
                        sources=[], piece={'audio': 'cached'}) for i in range(4)]
        stories[0]['expires'] = time.time()-1
        pair = choose_pair(self.config, stories, ['0','1'], random.Random(1))
        self.assertEqual({s['id'] for s in pair}, {'2','3'})
        # Duplicate catalog entries cannot defeat distinct-story selection.
        pair = choose_pair(self.config, [stories[1],stories[1],stories[2]], ['2','1'])
        self.assertEqual([s['id'] for s in pair], ['2','1'])

    def test_jitter_strongly_favours_oldest_but_breaks_a_fixed_loop(self):
        import random
        stories=[dict(id=str(i), expires=time.time()+3600, sources=[],
                      piece={'audio':'cached'}) for i in range(8)]
        rng=random.Random(19)
        first=[choose_pair(self.config,stories,list('01234567'),rng)[0]['id'] for _ in range(1000)]
        self.assertGreater(first.count('0'),800)
        self.assertLess(first.count('0'),900)
        self.assertEqual(set(first),set('012'))
        history=list('01234567')
        for _ in range(100):history.extend(s['id'] for s in choose_pair(self.config,stories,history[-192:],rng))
        self.assertGreater(len({tuple(history[i:i+8]) for i in range(8,len(history)-8,8)}),1)
        self.assertEqual(set(history[-80:]),set('01234567'))

    def test_refresh_requests_every_fresh_candidate_up_to_batch_limit(self):
        self.config.update(news_story_pool=True,news_stories_per_refresh=12)
        now=time.time()
        reports=[dict(id=str(i),title='Report '+str(i),published=now,
                      url='https://example.com/'+str(i),topics=['science']) for i in range(5)]
        catalog=dict(clips=[],seen=[],news_stories=[])
        provider=Mock();provider.config=self.config
        provider.sections.return_value=[]
        create_sections(self.config,catalog,provider,reports,now)
        self.assertEqual(provider.config['_news_story_count'],5)

    def test_large_batch_validates_and_has_enough_output_tokens(self):
        self.config.update(news_story_pool=True,_news_story_count=12)
        provider=object.__new__(Gemini);provider.config=self.config
        script=('NASA announced a new space telescope to study distant galaxies, according to its October fourteenth report. '
                'The instrument will observe X rays to help astronomers understand those galaxies.')
        stories=[dict(script=script,source_ids=[str(i)]) for i in range(12)]
        response=dict(sections=[dict(kind='news',script=' '.join([script]*12),source_ids=[str(i) for i in range(12)],stories=stories)])
        provider.request=Mock(return_value={'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':json.dumps(response)}]}]})
        result=provider.sections({'news':[{'id':str(i)} for i in range(12)]})
        self.assertEqual(len(result[0]['stories']),12)
        self.assertGreaterEqual(provider.request.call_args.args[1]['generation_config']['max_output_tokens'],3000)

    def test_batch_capacity_respects_both_voice_limits_and_reserves_weather(self):
        import datetime as dt
        from modules.internet.news_bank import news_batch_capacity
        now=dt.datetime(2026,10,26,tzinfo=dt.timezone.utc).timestamp()
        self.config.update(max_voice_calls_per_day=24,max_voice_seconds_per_day=1440,
                           max_clip_seconds=60,max_text_calls_per_day=17,
                           max_text_tokens_per_day=160000,news_feed_interval_seconds=10800,
                           weather_generation_interval_seconds=10800,daily_connectors=False)
        self.assertEqual(news_batch_capacity(self.config,{},now),2)
        atomic_json(Path(self.config['state_dir'])/'budget.json',{'2026-10-26':{'voice_calls':23,'voice_seconds':1380}})
        self.assertEqual(news_batch_capacity(self.config,{},now),0)
        atomic_json(Path(self.config['state_dir'])/'budget.json',{'2026-10-26':{'voice_calls':0,'voice_seconds':1440}})
        self.assertEqual(news_batch_capacity(self.config,{},now),0)

    def test_no_news_text_or_voice_generation_when_allowance_is_reserved(self):
        import datetime as dt
        now=dt.datetime(2026,10,26,tzinfo=dt.timezone.utc).timestamp()
        self.config.update(news_story_pool=True,news_stories_per_refresh=12,news_budget_aware=True,
                           max_voice_calls_per_day=24,max_voice_seconds_per_day=1440,
                           max_clip_seconds=60,max_text_calls_per_day=17,
                           max_text_tokens_per_day=160000,news_feed_interval_seconds=10800,
                           weather_generation_interval_seconds=10800)
        atomic_json(Path(self.config['state_dir'])/'budget.json',{'2026-10-26':{'voice_calls':24,'voice_seconds':1440}})
        provider=Mock();provider.config=self.config
        report=dict(id='new',title='New report',published=now,url='https://example.com/new',topics=['science'])
        result=create_sections(self.config,dict(clips=[],seen=[],news_stories=[]),provider,[report],now)
        self.assertIsNone(result)
        provider.sections.assert_not_called()
