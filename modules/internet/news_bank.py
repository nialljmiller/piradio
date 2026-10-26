"""Independent cached news stories; selection and assembly never call a provider."""
import hashlib
import random
import time
from .common import source_allowed


def valid_stories(config, catalog, now=None, ready=False):
    now = time.time() if now is None else now
    return [s for s in catalog.get('news_stories', [])
            if s['expires'] > now and all(source_allowed(config, r['url']) for r in s['sources'])
            and (not ready or s.get('piece'))]


def add_stories(config, catalog, result, reports, now):
    bank = valid_stories(config, catalog, now)
    for story in result['stories']:
        sources = [r for r in reports if r['id'] in story['source_ids']]
        key = hashlib.sha256(story['script'].encode()).hexdigest()
        if any(set(r['id'] for r in s['sources']) & set(story['source_ids']) for s in bank):
            continue
        ttl = config.get('news_story_ttl_seconds', 86400)
        expires = min([now + ttl] + [r['published'] + ttl for r in sources if 'published' in r])
        if expires > now:
            bank.append(dict(id=key, script=story['script'], sources=sources,
                             created=now, expires=expires))
    catalog['news_stories'] = bank[-config.get('news_story_pool_limit', 96):]
    return bank


def news_section(config, catalog, now=None, ready=False):
    stories = valid_stories(config, catalog, now, ready)
    if len(stories) < 2:
        return None
    # A pair is selected again at playback, after both pieces are available.
    pair = stories[-2:]
    return dict(kind='news', script=' '.join(s['script'] for s in pair),
                sources=[r for s in pair for r in s['sources']],
                expires=sorted(s['expires'] for s in stories)[-2], story_pool=stories,
                writing_provider='cached-story-pool')


def news_batch_capacity(config, catalog, now=None):
    """Spread remaining daily voice allowance over refreshes; reserve other audio."""
    import datetime as dt
    import math
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from .common import read_json
    now = time.time() if now is None else now
    utc = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    tomorrow = dt.datetime.combine(utc.date()+dt.timedelta(days=1), dt.time(), dt.timezone.utc)
    seconds = (tomorrow-utc).total_seconds()
    state = Path(config['state_dir'])
    ledger = read_json(Path(config.get('budget_state_dir', state))/'budget.json', {})
    usage = ledger.get(utc.date().isoformat(), {})
    if usage.get('text_calls', 0) >= config['max_text_calls_per_day']:
        return 0
    if usage.get('text_tokens', 0) >= config['max_text_tokens_per_day']:
        return 0
    remaining = min(config['max_voice_calls_per_day']-usage.get('voice_calls', 0),
        (config['max_voice_seconds_per_day']-usage.get('voice_seconds', 0))//config['max_clip_seconds'])
    rounds = max(1, math.ceil(seconds/config.get('news_feed_interval_seconds', 10800)))
    weather = math.ceil(seconds/config.get('weather_generation_interval_seconds', 10800))
    connectors = 0
    if config.get('daily_connectors'):
        zone = ZoneInfo(config.get('day_schedule', {}).get('timezone', 'America/New_York'))
        first = utc.astimezone(zone).date()
        last = (tomorrow-dt.timedelta(seconds=1)).astimezone(zone).date()
        history = read_json(state/'daily-connectors.json', {})
        while first <= last:
            if not history.get(first.isoformat(), {}).get('complete'):
                connectors += 4
            first += dt.timedelta(days=1)
    pending = sum(not s.get('piece') for s in valid_stories(config, catalog, now))
    return max(0, int((remaining-weather-connectors-pending)//rounds))


def choose_pair(config, stories, previous=(), rng=None):
    """Favour least-recently heard stories with modest jitter and a hard gap."""
    valid = list({s['id']: s for s in valid_stories(
        config, {'news_stories': stories}, ready=True)}.values())
    if len(valid) < 2:
        raise ValueError('Two unexpired distinct news stories are required')
    rng = rng or random.SystemRandom()
    history = list(previous)
    pair = []
    for _ in range(2):
        last_seen = {story_id: index for index, story_id in enumerate(history)}
        # Keep a guaranteed gap, even when jitter chooses a near-oldest story.
        gap = 2 if len(valid) >= 4 else 1
        recent = set(history[-gap:])
        candidates = [s for s in valid if s['id'] not in recent]
        # Shuffle ties, then strongly favour the oldest few. Newly added or
        # never-heard stories get their first airing before older recordings.
        candidates = rng.sample(candidates, len(candidates))
        candidates.sort(key=lambda s: last_seen.get(s['id'], -1))
        unheard = [s for s in candidates if s['id'] not in last_seen]
        if unheard:
            story = rng.sample(unheard, 1)[0]
        else:
            choices = candidates[:3]
            story = rng.choices(choices, weights=[85, 12, 3][:len(choices)], k=1)[0]
        pair.append(story)
        history.append(story['id'])
    return pair
