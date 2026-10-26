import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from modules.internet.common import load_config
from modules.internet.segments import factual_fallback
from modules.internet.worker import Gemini, current_news, parse_feed


class NewsWritingTests(unittest.TestCase):
    def test_recollections_not_current_news(self):
        self.assertFalse(current_news({'title': "'I watched Apollo 17 launch with Neil Armstrong'"}))
        self.assertTrue(current_news({'title': 'NASA launches new telescope'}))

    def test_raw_teasers_do_not_bypass_context_and_two_story_requirement(self):
        report = {'id':'a', 'source':'News', 'report_date':'2026-10-12',
                  'title':'Arrest reported', 'excerpt':'Abdul worked for the AI giant before his arrest.'}
        self.assertEqual(factual_fallback({'news':[report, dict(report,id='b')]}), [])

    def test_feed_preserves_context_after_old_400_character_cutoff(self):
        excerpt = 'Background information. ' * 20 + 'The FBI alleges the former researcher stole confidential AI training data.'
        raw = ('<rss><channel><item><title>Researcher charged</title><link>https://example.com/story</link>'
               '<pubDate>Wed, 14 Oct 2026 12:00:00 GMT</pubDate><description>' + excerpt +
               '</description></item></channel></rss>').encode()
        result = parse_feed(raw, 'News', 1791979200)
        self.assertEqual(len(result), 1)
        self.assertIn('confidential AI training data',result[0]['excerpt'])

    def test_news_requires_two_distinct_reports_and_accepts_two(self):
        with tempfile.TemporaryDirectory() as state:
            provider = object.__new__(Gemini)
            provider.config = load_config(Path(__file__).resolve().parents[1] / 'config.example.json')
            provider.config.update(state_dir=state, news_target_seconds=45)
            script = ('NASA launched an X-ray telescope to study distant galaxies, according to its October 14 report. '
                      'Meanwhile, Raleigh officials announced new flood protections for residents after recent storms, '
                      'according to the local government report dated October 14.')
            def response(ids):
                return {'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':json.dumps(
                    {'sections':[{'kind':'news','script':script,'source_ids':ids}]})}]}]}
            provider.request = Mock(return_value=response(['a']))
            groups = {'news':[{'id':'a'},{'id':'b'}]}
            with self.assertRaises(ValueError): provider.sections(groups)
            provider.request.return_value = response(['a','b'])
            self.assertEqual(provider.sections(groups)[0]['source_ids'], ['a','b'])
            provider.request.reset_mock()
            self.assertEqual(provider.sections({'news':[{'id':'a'}]}), [])
            provider.request.assert_not_called()
