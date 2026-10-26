"""One fresh reusable connector set per local date, with resumable voice caching."""
import datetime as dt
import hashlib
import json
import logging
import time
from pathlib import Path
from zoneinfo import ZoneInfo
from .common import atomic_json, read_json
from .segments import piece, identity
LOG = logging.getLogger('piradio-internet.connectors')
KINDS = ('intro', 'news', 'weather', 'outro')


def refresh(config, text, voice, catalog):
    if not config.get('daily_connectors', False):
        return
    state = Path(config['state_dir'])
    path = state/'daily-connectors.json'
    history = read_json(path, {})
    date = dt.datetime.now(ZoneInfo(config.get('day_schedule', {}).get('timezone', 'America/New_York'))).date().isoformat()
    entry = history.get(date)
    library = read_json(state/'connectors.json', {})
    if library.get('identity') != identity(config, voice):
        LOG.warning('Daily connectors require the existing voice library')
        return
    if entry is None or ('scripts' not in entry and entry.get('attempts', 0) < 3 and entry.get('retry_after', 0) <= time.time()):
        # One text attempt per date; persist before TTS so voice retries never rewrite.
        history[date] = {'attempts': (entry or {}).get('attempts', 0) + 1, 'retry_after': time.time() + 900}
        atomic_json(path, history)
        examples = {kind: [p['script'] for p in library['clips'].get(kind, [])][-12:] for kind in KINDS}
        try:
            scripts = text.connector_set(examples)
            for kind, script in scripts.items():
                if script.strip().casefold() in {p['script'].strip().casefold() for p in library['clips'].get(kind, [])}:
                    raise ValueError('Connector already exists in cached library')
        except Exception as exc:
            LOG.warning('Daily connector writing unavailable (%s); cached library retained', type(exc).__name__)
            return
        entry = history[date] = {'scripts': scripts, 'writer': text.name}
        atomic_json(path, history)
    entry = history.get(date, {})
    if 'scripts' not in entry or entry.get('complete'):
        return
    for kind in KINDS:
        script = entry['scripts'][kind]
        options = library['clips'].setdefault(kind, [])
        if any(p['script'] == script for p in options):
            continue
        options.append(dict(piece(config, voice, script), created_date=date))
        atomic_json(state/'connectors.json', library)
    entry['complete'] = True
    atomic_json(path, history)
    # Existing bulletins can immediately mix in the expanded bank.
    for clip in catalog.get('clips', []):
        if 'piece_choices' not in clip:
            continue
        clip['piece_choices'][0] = library['clips']['intro']
        clip['piece_choices'][-1] = library['clips']['outro']
        for i, section in enumerate(clip['sections']):
            clip['piece_choices'][1+i*2] = library['clips'][section['kind']]
    atomic_json(state/'catalog.json', catalog)
    LOG.info('Added daily connector set for %s', date)
