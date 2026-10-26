import json
import os
import tempfile
from urllib.parse import urlsplit
from pathlib import Path


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def load_config(path):
    config = read_json(path, {})
    if config.get('text_provider', 'gemini') not in ('gemini', 'grok', 'gemini-cli', 'grok-cli', 'random-cli'):
        raise ValueError('text_provider must be gemini, grok, gemini-cli or grok-cli')
    for name, default, minimum, maximum in (('news_candidate_limit', 12, 3, 20), ('news_target_seconds', 45, 15, 45), ('weather_target_seconds', 25, 15, 40)):
        value = config.get(name, default)
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            raise ValueError('Invalid bounded setting: ' + name)
    limits = config.get('section_prompt_limits')
    if limits is not None and (not isinstance(limits, dict) or set(limits) != {'news','weather'} or any(not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 24 for v in limits.values())):
        raise ValueError('section_prompt_limits requires bounded news and weather counts')
    timeout = config.get('cli_timeout_seconds', 120)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 15 <= timeout <= 240:
        raise ValueError('cli_timeout_seconds must be 15 to 240')
    cap = config.get('grok_max_tokens', 1536)
    if not isinstance(cap, int) or isinstance(cap, bool) or not 64 <= cap <= 4096:
        raise ValueError('grok_max_tokens must be 64 to 4096')
    if 'grok_text_model' in config and (not isinstance(config['grok_text_model'], str) or not config['grok_text_model'].strip()):
        raise ValueError('grok_text_model must be a nonempty string')
    for name in ('interval_seconds', 'repeat_after_seconds', 'news_ttl_seconds',
                 'max_clip_seconds', 'max_text_calls_per_day', 'max_voice_calls_per_day',
                 'max_text_tokens_per_day', 'max_voice_seconds_per_day'):
        value = config.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError('Invalid positive integer setting: ' + name)
    if config['max_clip_seconds'] > 120:
        raise ValueError('Bulletins must be at most 120 seconds')
    if not isinstance(config.get('feeds'), list):
        raise ValueError('feeds must be a list')
    if not isinstance(config.get('topics'), list):
        raise ValueError('topics must be a list of names and keywords')
    for topic in config['topics']:
        if not isinstance(topic, dict) or not isinstance(topic.get('name'), str):
            raise ValueError('Every topic needs a name')
        if not isinstance(topic.get('keywords', []), list) or not all(
                isinstance(word, str) for word in topic.get('keywords', [])):
            raise ValueError('Topic keywords must be strings')
    if not isinstance(config.get('enabled'), bool):
        raise ValueError('enabled must be boolean')
    if not Path(config.get('state_dir', '')).is_absolute():
        raise ValueError('state_dir must be absolute')
    for name in ('host_name', 'station_name', 'voice_style'):
        if not isinstance(config.get(name), str) or not 1 <= len(config[name]) <= 500:
            raise ValueError('Invalid identity or voice setting: ' + name)
    for name in ('preferred_news_sources', 'banned_news_sources'):
        if not isinstance(config.get(name), list):
            raise ValueError(name + ' must be a list')
        for domain in config[name]:
            if not isinstance(domain, str):
                raise ValueError('Source domains must be strings')
            source_domain(domain)
    repeats = config.get('max_repeats_per_news_recording')
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 0:
        raise ValueError('Repeat limit must be a nonnegative integer')
    spacing = config.get('generation_interval_seconds')
    if not isinstance(spacing, int) or isinstance(spacing, bool) or spacing < 1:
        raise ValueError('Generation spacing must be a positive integer')
    if config.get('voice_provider', 'gemini') not in ('gemini', 'fish'):
        raise ValueError('Unknown voice provider')
    speech_gain = config.get('fish_speech_gain', 1.0)
    if not isinstance(speech_gain, (int, float)) or isinstance(speech_gain, bool) or not 0.5 <= speech_gain <= 2:
        raise ValueError('fish_speech_gain must be between 0.5 and 2')
    priorities = config.get('news_topic_priorities', {})
    if (not isinstance(priorities, dict) or any(not isinstance(k, str) or
            not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100
            for k, v in priorities.items())):
        raise ValueError('News topic priorities must be integers from 0 to 100')
    for name, minimum, maximum, default in (
            ('priority_override_score', 101, 1000, 200),
            ('priority_override_max_age_seconds', 1, 86400, 14400)):
        value = config.get(name, default)
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            raise ValueError('Invalid priority setting: ' + name)
    patterns = config.get('priority_override_patterns', [])
    if not isinstance(patterns, list) or len(patterns) > 20:
        raise ValueError('Invalid priority override patterns')
    import re
    for pattern in patterns:
        if not isinstance(pattern, str) or not 1 <= len(pattern) <= 250:
            raise ValueError('Invalid priority pattern')
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError('Invalid priority expression') from exc
    if not isinstance(config.get('news_story_pool', False), bool):
        raise ValueError('news_story_pool must be boolean')
    ttl = config.get('news_story_ttl_seconds', 86400)
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 3600 <= ttl <= 86400:
        raise ValueError('Invalid news story expiry')
    if not isinstance(config.get('segmented_bulletins', False), bool):
        raise ValueError('segmented_bulletins must be boolean')
    if config.get('segmented_bulletins'):
        limit = config.get('max_bulletin_seconds', config['max_clip_seconds'])
        if not isinstance(limit, int) or isinstance(limit, bool) or not config['max_clip_seconds'] <= limit <= 600:
            raise ValueError('Invalid assembled bulletin duration limit')
        delay = config.get('first_bulletin_delay_seconds', config['interval_seconds'])
        if not isinstance(delay, int) or isinstance(delay, bool) or not 0 <= delay <= config['interval_seconds']:
            raise ValueError('Invalid initial bulletin delay')
        connectors = config.get('connectors', {})
        if set(connectors) != {'intro', 'weather', 'news', 'outro'}:
            raise ValueError('Four connector categories required')
        for options in connectors.values():
            if (not isinstance(options, list) or not 1 <= len(options) <= 4 or
                    any(not isinstance(s, str) or not 1 <= len(s) <= 250 for s in options)):
                raise ValueError('One to four short connector phrases required')
            for script in options:
                try:
                    script.format(host_name=config['host_name'], station_name=config['station_name'])
                except (KeyError, ValueError, IndexError) as exc:
                    raise ValueError('Unknown connector placeholder') from exc
    gain = config.get('music_duck_gain', 0.08)
    if not isinstance(gain, (int, float)) or isinstance(gain, bool) or not 0 <= gain <= 1:
        raise ValueError('music_duck_gain must be between zero and one')
    fade = config.get('duck_fade_seconds', 0.3)
    if not isinstance(fade, (int, float)) or isinstance(fade, bool) or not 0.05 <= fade <= 2:
        raise ValueError('duck_fade_seconds must be between 0.05 and 2 seconds')
    from .daypart import validate
    validate(config)
    return config


def source_domain(value):
    value = value.strip().lower()
    parsed = urlsplit(value if '://' in value else 'https://' + value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('Source must be a domain or HTTP(S) URL')
    return parsed.hostname.rstrip('.').encode('idna').decode('ascii')


def domain_matches(url, domains):
    host = source_domain(url)
    return any(host == source_domain(d) or host.endswith('.' + source_domain(d))
               for d in domains)


def source_allowed(config, url):
    try:
        return not domain_matches(url, config.get('banned_news_sources', []))
    except (ValueError, UnicodeError):
        return False
