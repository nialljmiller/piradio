"""Reusable speech pieces and local assembly; playback never calls an API."""
import hashlib
import io
import json
import logging
import os
import re
import datetime as dt
import time
import urllib.error
import wave
from pathlib import Path

from .common import atomic_json, read_json, source_allowed

LOG = logging.getLogger('piradio-internet.segments')


def factual_fallback(groups):
    """Source summary sentences and forecast facts, without model invention."""
    sections = []
    for kind, reports in groups.items():
        if kind == 'weather':
            report = reports[0]
            periods = json.loads(report['excerpt'])
            phrases = []
            for period in periods[:2]:
                date = dt.datetime.fromisoformat(period['startTime']).strftime('%A, %B %d')
                phrases.append(f'{date}, {period["name"]}: {period["shortForecast"]}. '
                    f'Temperature {period["temperature"]} degrees {period["temperatureUnit"]}; '
                    f'wind {period["windDirection"]}, {period["windSpeed"]}.')
            script = 'Arr, here be the National Weather Service forecast for ' + report['title'].removesuffix(' forecast') + '. ' + ' '.join(phrases)
            ids = [report['id']]
        else:
            # Raw RSS teasers cannot guarantee two self-contained stories. Keep
            # the previous valid news recording until the model writes a new one.
            continue
        sections.append({'kind': kind, 'script': script, 'source_ids': ids,
                         'writing_provider': 'factual-fallback'})
    return sections


def write_sections(config, provider, groups):
    if not config.get('text_failure_fallback', False):
        return provider.sections(groups)
    from .worker import BudgetExceeded
    from .cli import CLIUnavailable
    name = getattr(provider, 'name', config.get('text_provider', 'gemini'))
    if not isinstance(name, str):
        name = config.get('text_provider', 'gemini')
    path = Path(config['state_dir']) / ('text-unavailable.json' if name == 'gemini' else 'text-unavailable-' + name + '.json')
    key = getattr(provider, 'key', '')
    fingerprint = hashlib.sha256((key if isinstance(key, str) else '').encode()).hexdigest()
    unavailable = read_json(path, {})
    if unavailable.get('key') == fingerprint and unavailable.get('until', 0) > time.time():
        return factual_fallback(groups)
    try:
        result = provider.sections(groups)
        for section in result:
            section['writing_provider'] = name
        path.unlink(missing_ok=True)
        return result
    except CLIUnavailable as exc:
        atomic_json(path, {'key': fingerprint, 'until': time.time() + 900, 'status': 'cli-unavailable'})
        LOG.warning('%s', exc)
    except BudgetExceeded:
        LOG.warning('Text allowance reached; retaining cached news and using forecast facts')
    except urllib.error.HTTPError as exc:
        if exc.code not in (402, 429, 500, 502, 503, 504):
            raise
        delay = 86400 if exc.code == 402 else 3600 if exc.code == 429 else 900
        atomic_json(path, {'key': fingerprint, 'until': time.time() + delay, 'status': exc.code})
        LOG.warning('Text provider HTTP %s; retaining cached news and using forecast facts', exc.code)
    return factual_fallback(groups)


def identity(config, provider):
    return provider.cache_identity() if hasattr(provider, 'cache_identity') else [
        'gemini', config['voice_model'], config['voice'], config['voice_style']]


def piece(config, provider, script):
    key = hashlib.sha256(json.dumps([script, identity(config, provider)],
                                   ensure_ascii=False).encode()).hexdigest()
    path = Path(config['state_dir']) / 'audio' / (key + '.wav')
    if not path.exists():
        data, _ = provider.voice(script)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(data)
        os.replace(temporary, path)
    with wave.open(str(path)) as wav:
        duration = wav.getnframes() / wav.getframerate()
    return {'audio': str(path), 'duration': duration, 'script': script}


def prepare_connectors(config, provider):
    """Gradually fill the library within the normal request limits."""
    library = {}
    # First generate one of every kind, then additional alternatives. A failed
    # or budget-limited run retains each successful audio file for the next run.
    settings = config['connectors']
    for index in range(max(len(options) for options in settings.values())):
        for kind, options in settings.items():
            if index < len(options):
                script = options[index].format(host_name=config['host_name'],
                                               station_name=config['station_name'])
                library.setdefault(kind, []).append(piece(config, provider, script))
                atomic_json(Path(config['state_dir']) / 'connectors.json', {
                    'identity': identity(config, provider), 'clips': library})
    return library


def render_sections(config, catalog, provider, entry):
    state = Path(config['state_dir'])
    library = read_json(state / 'connectors.json', {})
    if library.get('identity') != identity(config, provider):
        raise ValueError('Prepare connectors for the current voice first')
    choices = library['clips']
    groups = [choices['intro']]
    for section in entry['sections']:
        if any(not source_allowed(config, item['url']) for item in section['sources']):
            raise ValueError('Section contains a banned source')
        if section.get('story_pool'):
            for story in section['story_pool']:
                story['piece'] = piece(config, provider, story['script'])
                for cached in catalog.get('news_stories', []):
                    if cached['id'] == story['id']:
                        cached['piece'] = story['piece']
                atomic_json(state / 'catalog.json', catalog)
            from .news_bank import news_section
            section.update(news_section(config, catalog, ready=True))
            # The assembler substitutes two independently selected story pieces.
            section['piece'] = section['story_pool'][0]['piece']
        else:
            section['piece'] = piece(config, provider, section['script'])
        groups.extend([choices[section['kind']], [section['piece']]])
        catalog.setdefault('sections', {})[section['kind']] = section
        atomic_json(state / 'catalog.json', catalog)
    groups.append(choices['outro'])
    entry['piece_choices'] = groups
    assembled = assemble(config, entry, 0)
    entry.update(audio=assembled['audio'], duration=assembled['duration'], ready=True)
    # Keep the latest assembled bulletin, while its independent sections remain
    # in the bank for reuse at the next weather/news refresh.
    catalog['clips'] = [c for c in catalog['clips'] if c is entry or 'sections' not in c]
    atomic_json(state / 'catalog.json', catalog)


def assemble(config, entry, iteration, previous=None):
    """Choose different connectors on repeats; keep one continuous ducked clip."""
    groups = entry['piece_choices']
    if not 3 <= len(groups) <= 6 or any(not group for group in groups):
        raise ValueError('Invalid bulletin pieces')
    previous = previous or {}
    indices, parts = {}, []
    labels = ['intro']
    for section in entry['sections']:
        labels.extend([section['kind'], 'content-' + section['kind']])
    labels.append('outro')
    for label, group in zip(labels, groups):
        seed = hashlib.sha256(f'{entry["id"]}:{iteration}:{label}'.encode()).digest()
        options = list(range(len(group)))
        if len(options) > 1 and previous.get(label) in options:
            options.remove(previous[label])
        index = options[int.from_bytes(seed[:4], 'big') % len(options)]
        indices[label] = index
        if label == 'content-news' and next((s for s in entry['sections'] if s['kind'] == 'news' and s.get('story_pool')), None):
            from .news_bank import choose_pair
            section = next(s for s in entry['sections'] if s['kind'] == 'news')
            history = previous.get('_story_history', previous.get('_stories', ()))
            pair = choose_pair(config, section['story_pool'], history)
            indices['_stories'] = [s['id'] for s in pair]
            indices['_story_history'] = (list(history) + indices['_stories'])[-config.get('news_story_history_limit', 192):]
            parts.extend(s['piece'] for s in pair)
        else:
            parts.append(group[index])
    root = (Path(config['state_dir']) / 'audio').resolve()
    chunks, params = [], None
    for part in parts:
        path = Path(part['audio']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Piece outside audio cache')
        with wave.open(str(path)) as wav:
            current = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
            if current[0] not in (1, 2) or current[1] != 2 or not 8000 <= current[2] <= 96000:
                raise ValueError('Unsupported piece audio')
            if params is not None and current != params:
                raise ValueError('Piece audio formats differ')
            params = current
            raw = wav.readframes(config['max_clip_seconds'] * current[2] + 1)
            if len(raw) > config['max_clip_seconds'] * current[2] * current[0] * current[1]:
                raise ValueError('Individual piece exceeds duration limit')
            chunks.append(raw)
    channels, width, rate = params
    # Short pauses between phrases, with the bed staying quiet throughout.
    gap = bytes(int(rate * 0.16) * channels * width)
    pcm = gap.join(chunks)
    duration = len(pcm) / (rate * channels * width)
    if not 2 <= duration <= config.get('max_bulletin_seconds', config['max_clip_seconds']):
        raise ValueError('Assembled bulletin exceeds duration limit')
    key = hashlib.sha256(pcm).hexdigest()
    path = root / ('assembled-' + key + '.wav')
    if not path.exists():
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(rate)
            wav.writeframes(pcm)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(output.getvalue())
        os.replace(temporary, path)
    return dict(entry, audio=str(path), duration=duration, _connector_indices=indices)


def create_sections(config, catalog, provider, items, now):
    """Reuse fresh sections; make one text request for changed categories only."""
    current = {kind: section for kind, section in catalog.get('sections', {}).items()
               if section['expires'] > now and all(source_allowed(config, i['url'])
                                                   for i in section['sources'])}
    for clip in catalog['clips']:
        for section in clip.get('sections', []):
            if (section['expires'] > now and all(source_allowed(config, i['url'])
                                               for i in section['sources'])):
                current[section['kind']] = section
    groups = {}
    for item in items:
        kind = 'weather' if 'weather' in item.get('topics', []) else 'news'
        groups.setdefault(kind, []).append(item)
    if 'weather' in groups:
        catalog['last_weather_generation'] = now
    renewed = False
    if 'weather' in groups and 'weather' in current and not config.get('rewrite_weather_each_refresh', False):
        weather = current['weather']
        if {i['id'] for i in weather['sources']} == {i['id'] for i in groups['weather']}:
            # An unchanged but freshly fetched forecast keeps its recording.
            # Validity still ends at the forecast period's end or weather TTL.
            weather = dict(weather, sources=groups.pop('weather'))
            weather['expires'] = min(i['expires'] for i in weather['sources'])
            current['weather'] = weather
            renewed = True
    if config.get('news_story_pool') and 'news' in groups:
        from .news_bank import valid_stories
        bank = valid_stories(config, catalog, now)
        existing_ids = {r['id'] for story in bank for r in story['sources']}
        groups['news'] = [r for r in groups['news'] if r['id'] not in existing_ids
                          and r.get('published', now) + config.get('news_story_ttl_seconds', 86400) > now]
        count = min(len(groups['news']), config.get('news_stories_per_refresh', max(1, 2 - len(bank))))
        if config.get('news_budget_aware'):
            from .news_bank import news_batch_capacity
            count = min(count, news_batch_capacity(config, catalog, now))
            if count == 0:
                LOG.info('News voice allowance reserved for later refreshes; cached stories continue')
                groups['news'] = []
        provider.config['_news_story_count'] = count
        if not groups['news']:
            groups.pop('news')
    changed = write_sections(config, provider, groups) if groups else []
    used = []
    for result in changed:
        if result['kind'] == 'news' and result.get('stories'):
            from .news_bank import add_stories, news_section
            before = {s['id'] for s in catalog.get('news_stories', [])}
            bank = add_stories(config, catalog, result, groups['news'], now)
            if any(s['id'] not in before for s in bank):
                catalog['last_news_generation'] = now
            atomic_json(Path(config['state_dir']) / 'catalog.json', catalog)
            used.extend(result['source_ids'])
            section = news_section(config, catalog, now)
            if section:
                current['news'] = section
            continue
        sources = [i for i in groups[result['kind']] if i['id'] in result['source_ids']]
        expires = min([now + config['news_ttl_seconds']] +
                      [i['expires'] for i in sources if 'expires' in i])
        current[result['kind']] = {'kind': result['kind'], 'script': result['script'],
                                  'sources': sources, 'expires': expires,
                                  'writing_provider': result.get('writing_provider', 'gemini')}
        if result['kind'] == 'news':
            catalog['last_news_generation'] = now
        used.extend(result['source_ids'])
    if config.get('news_story_pool'):
        from .news_bank import news_section
        bank_section = news_section(config, catalog, now)
        if bank_section:
            current['news'] = bank_section
    sections = [current[kind] for kind in ('news', 'weather') if kind in current]
    if (not changed and not renewed) or not sections:
        return None
    script = '\n'.join(s['script'] for s in sections)
    sources = [i for s in sections for i in s['sources']]
    entry = {'id': hashlib.sha256(json.dumps(sections, sort_keys=True).encode()).hexdigest(),
             'script': script, 'sections': sections, 'kind': 'news', 'created': now,
             'expires': min(s['expires'] for s in sections), 'ready': False,
             'sources': sources, 'topics': list(dict.fromkeys(
                 topic for i in sources for topic in i.get('topics', [])))}
    catalog['clips'].append(entry)
    catalog['sections'] = {s['kind']: s for s in sections}
    catalog['seen'] = list(dict.fromkeys(catalog['seen'] + used))[-2000:]
    atomic_json(Path(config['state_dir']) / 'catalog.json', catalog)
    return entry
