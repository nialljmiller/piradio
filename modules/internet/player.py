"""Mix cached speech over continuing music with automatic volume ducking."""
import array
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from .common import atomic_json, load_config, read_json, source_allowed
from .daypart import effective_config

LOG = logging.getLogger('piradio-internet.player')


def write_all(fd, data):
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise BrokenPipeError('Transmitter pipe closed')
        view = view[written:]



class Relay:
    def __init__(self, config, config_path=None):
        self.config = config
        self.config_path = config_path
        self.settings_check = 0
        self.state = Path(config['state_dir'])
        self.next_check = time.monotonic() + config.get('first_bulletin_delay_seconds', config['interval_seconds'])
        self.music_gain = 1.0

    def choose(self):
        now = time.time()
        config = effective_config(self.config, now)
        catalog = read_json(self.state / 'catalog.json', {'clips': []})
        history = read_json(self.state / 'play-history.json', {})
        candidates = []
        for clip in catalog['clips']:
            record = history.get(clip['id'], {})
            if isinstance(record, (int, float)):
                record = {'last_played': record, 'plays': 1}
            if any(not source_allowed(self.config, item['url']) for item in clip.get('sources', [])):
                continue
            if ('sections' not in clip and clip['kind'] == 'news' and
                    record.get('plays', 0) >= 1 + config['max_repeats_per_news_recording']):
                continue
            if (not clip.get('ready') or clip['expires'] <= now
                    or ('sections' not in clip and now - record.get('last_played', 0) < config['repeat_after_seconds'])):
                continue
            path = Path(clip['audio']).resolve()
            if not path.is_relative_to((self.state / 'audio').resolve()) or not path.is_file():
                continue
            duration = clip.get('duration')
            limit = self.config.get('max_bulletin_seconds', self.config['max_clip_seconds']) if 'piece_choices' in clip else self.config['max_clip_seconds']
            if (not isinstance(duration, (int, float)) or isinstance(duration, bool)
                    or not 2 <= duration <= limit):
                continue
            candidates.append(clip)
        # Unplayed fresh news first; keep evergreen recordings as reusable filler.
        def last_played(clip):
            record = history.get(clip['id'], {})
            return record.get('last_played', 0) if isinstance(record, dict) else record
        candidates.sort(key=lambda c: (c['kind'] != 'news', last_played(c), -c['created']))
        for clip in candidates:
            if 'piece_choices' in clip:
                from .segments import assemble
                record = history.get(clip['id'], {})
                if not isinstance(record, dict):
                    record = {'last_played': record, 'plays': 1}
                due, groups = [], [clip['piece_choices'][0]]
                for index, section in enumerate(clip['sections']):
                    kind = section['kind']
                    last = history.get('_section_plays', {}).get(kind, record.get('last_played', 0))
                    interval = config.get(kind + '_play_interval_seconds', config['interval_seconds'])
                    if now - last < interval:
                        continue
                    if kind == 'news' and not section.get('story_pool') and record.get('news_plays', 0) >= 1 + config['max_repeats_per_news_recording']:
                        continue
                    if section.get('story_pool'):
                        from .news_bank import news_section
                        section = news_section(config, catalog, ready=True)
                        if not section:
                            continue
                    due.append(section)
                    groups.extend(clip['piece_choices'][1 + index*2:3 + index*2])
                if not due:
                    continue
                groups.append(clip['piece_choices'][-1])
                selected = dict(clip, sections=due, piece_choices=groups)
                rotation = history.get('_connectors', {})
                iteration = rotation.get('sequence', 0)
                try:
                    return assemble(config, selected, iteration, rotation.get('indices', {}))
                except (OSError, ValueError, KeyError, TypeError):
                    LOG.warning('Bulletin pieces unavailable; trying another recording')
                    continue
            return clip
        return None

    def refresh_timing(self):
        if self.config_path:
            try:
                self.config = load_config(self.config_path)
            except (OSError, ValueError, KeyError, TypeError):
                LOG.warning('Settings reload failed; retaining last valid configuration')
        config = effective_config(self.config)
        history = read_json(self.state / 'play-history.json', {})
        last = history.get('_section_plays', {})
        if last:
            now = time.time()
            deadline = min(last.get(kind, now) + config.get(kind + '_play_interval_seconds', config['interval_seconds'])
                           for kind in ('news', 'weather'))
            self.next_check = min(self.next_check, time.monotonic() + max(0, deadline - now))

    def mark_played(self, clip):
        history = read_json(self.state / 'play-history.json', {})
        record = history.get(clip['id'], {})
        if isinstance(record, (int, float)):
            record = {'last_played': record, 'plays': 1}
        history[clip['id']] = {'last_played': clip.get('_started_at', time.time()),
                               'plays': record.get('plays', 0) + 1,
                               'news_plays': record.get('news_plays', 0) +
                                   int(any(s['kind'] == 'news' for s in clip.get('sections', [])))}
        if 'sections' in clip:
            section_plays = history.pop('_section_plays', {})
            for section in clip['sections']:
                section_plays[section['kind']] = clip.get('_started_at', time.time())
            history['_section_plays'] = section_plays
        if '_connector_indices' in clip:
            rotation = history.pop('_connectors', {})
            history['_connectors'] = {'sequence': rotation.get('sequence', 0) + 1,
                                      'indices': dict(rotation.get('indices', {}), **clip['_connector_indices'])}
        atomic_json(self.state / 'play-history.json', dict(list(history.items())[-500:]))

    def remember_news_selection(self, clip):
        # Commit before airing so a restart or decoder failure retains recency.
        indices = clip.get('_connector_indices', {})
        if '_stories' not in indices:
            return
        history = read_json(self.state / 'play-history.json', {})
        rotation = history.setdefault('_connectors', {})
        previous = rotation.setdefault('indices', {})
        for key in ('_stories', '_story_history'):
            if key in indices:
                previous[key] = indices[key]
        atomic_json(self.state / 'play-history.json', history)

    @staticmethod
    def stop_decoder(decoder):
        if decoder.stdout:
            decoder.stdout.close()
        if decoder.poll() is None:
            decoder.terminate()
            try:
                decoder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                decoder.kill()
                decoder.wait()

    def mix(self, music, speech, channels, target):
        bed = array.array('h')
        bed.frombytes(music)
        voice = array.array('h')
        voice.frombytes(speech)
        if sys.byteorder != 'little':
            bed.byteswap()
            voice.byteswap()
        # Gain advances once per audio frame, independently of buffer size.
        step = 1 / (44100 * self.config.get('duck_fade_seconds', 0.3))
        gain = self.music_gain
        for frame in range(len(bed) // channels):
            gain += max(-step, min(step, target - gain))
            for channel in range(channels):
                i = frame * channels + channel
                value = bed[i] * gain + (voice[i] * 0.95 if i < len(voice) else 0)
                bed[i] = max(-32768, min(32767, int(value)))
        self.music_gain = gain
        if sys.byteorder != 'little':
            bed.byteswap()
        return bed.tobytes()

    def decode(self, command, kwargs, output_fd, channels, inject=True):
        options = dict(kwargs)
        options.pop('stdout', None)
        decoder = subprocess.Popen(command, stdout=subprocess.PIPE, **options)
        speech_decoder = None
        active_clip = None
        next_bulletin = None
        self.music_gain = 1.0
        size = 4096 * channels * 2
        try:
            while True:
                chunk = decoder.stdout.read(size)
                if not chunk and speech_decoder is None:
                    break
                if inject and speech_decoder is None and time.monotonic() >= self.settings_check:
                    self.settings_check = time.monotonic() + 60
                    try:
                        self.refresh_timing()
                    except (OSError, ValueError, KeyError, TypeError):
                        LOG.warning('Schedule unavailable; retaining current timing')
                if inject and speech_decoder is None and chunk and time.monotonic() >= self.next_check:
                    self.next_check = time.monotonic() + 60
                    try:
                        clip = self.choose()
                        if clip:
                            speech_command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                                '-i', clip['audio'], '-t', str(self.config.get('max_bulletin_seconds', self.config['max_clip_seconds']) if 'piece_choices' in clip else self.config['max_clip_seconds']),
                                '-af', 'afade=t=in:d=0.3,afade=t=out:st=' + str(max(0, clip['duration'] - 0.3)) + ':d=0.3',
                                '-f', 's16le', '-acodec', 'pcm_s16le', '-ac', str(channels), '-ar', '44100', '-']
                            self.remember_news_selection(clip)
                            speech_decoder = subprocess.Popen(speech_command, stdout=subprocess.PIPE,
                                                              stderr=subprocess.DEVNULL)
                            active_clip = clip
                            active_clip['_started_at'] = time.time()
                            next_bulletin = time.monotonic() + effective_config(self.config)['interval_seconds']
                            LOG.info('Mixing %s bulletin %s over music', clip['kind'], clip['id'][:12])
                    except (OSError, ValueError, KeyError, TypeError):
                        LOG.warning('Bulletin queue unavailable; original playback continues')
                speech = b''
                if speech_decoder is not None:
                    speech = speech_decoder.stdout.read(len(chunk) if chunk else size)
                    if not speech:
                        result = speech_decoder.wait()
                        self.stop_decoder(speech_decoder)
                        speech_decoder = None
                        if result == 0:
                            try:
                                self.mark_played(active_clip)
                            except (OSError, ValueError, KeyError, TypeError):
                                LOG.warning('Could not save bulletin playback history')
                            self.next_check = max(time.monotonic(), next_bulletin)
                            LOG.info('Bulletin finished; music returning to full volume')
                        else:
                            LOG.warning('Bulletin decoder failed; music continues')
                        active_clip = None
                if not chunk:
                    if not speech:
                        break
                    # If a song ends first, finish the bulletin before the next
                    # spoken pirate announcement. No competing voices overlap.
                    chunk = bytes(len(speech))
                if speech_decoder is not None or self.music_gain < 1:
                    target = self.config.get('music_duck_gain', 0.08) if speech_decoder else 1.0
                    chunk = self.mix(chunk, speech, channels, target)
                write_all(output_fd, chunk)
            return decoder.wait()
        finally:
            self.stop_decoder(decoder)
            if speech_decoder is not None:
                self.stop_decoder(speech_decoder)


class PlaybackProxy:
    def __init__(self, original, relay, namespace):
        self.original, self.relay, self.namespace = original, relay, namespace

    def __getattr__(self, name):
        return getattr(self.original, name)

    def call(self, command, **kwargs):
        if (isinstance(command, list) and command and command[0] == 'ffmpeg'
                and kwargs.get('stdout') == self.namespace['music_pipe_w']
                and 's16le' in command and command[-1] == '-'):
            channels = int(command[command.index('-ac') + 1])
            source = Path(command[command.index('-i') + 1])
            is_announcement = 'announce' in source.parts
            return self.relay.decode(command, kwargs, kwargs['stdout'], channels,
                                     inject=not is_announcement)
        return self.original.call(command, **kwargs)


def attach(namespace, config_path):
    config = load_config(config_path)
    if not config['enabled']:
        return False
    if isinstance(namespace['subprocess'], PlaybackProxy):
        return True
    namespace['subprocess'] = PlaybackProxy(namespace['subprocess'], Relay(config, config_path), namespace)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    LOG.info('Internet bulletins enabled; original song ordering retained')
    return True
