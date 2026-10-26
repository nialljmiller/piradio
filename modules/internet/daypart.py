"""Station-local day periods, music pools and independent bulletin intervals."""
import csv
import datetime as dt
import logging
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo
from .attributes import sync_folder, sync_all

LOG = logging.getLogger('piradio.daypart')
NAMES = ('morning', 'day', 'evening', 'night')
EXTENSIONS = {'.aac', '.mp3', '.wav', '.flac', '.m4a'}


def minute(value):
    hour, minutes = map(int, value.split(':'))
    if len(value) != 5 or not 0 <= hour < 24 or not 0 <= minutes < 60:
        raise ValueError('Day period boundaries must use HH:MM')
    return hour * 60 + minutes


def contains(start, end, value):
    return start <= value < end if start < end else value >= start or value < end


def validate(config):
    schedule = config.get('day_schedule')
    if schedule is None:
        return
    if not isinstance(schedule, dict) or not isinstance(schedule.get('enabled'), bool):
        raise ValueError('day_schedule requires a boolean enabled setting')
    ZoneInfo(schedule['timezone'])
    periods = schedule['periods']
    if set(periods) != set(NAMES):
        raise ValueError('Four day periods required: morning, day, evening, night')
    coverage = [0] * 1440
    folders = set()
    for period in periods.values():
        start, end = minute(period['start']), minute(period['end'])
        if start == end:
            raise ValueError('A day period cannot be empty or occupy a whole day')
        for value in range(1440):
            coverage[value] += contains(start, end, value)
        folder = Path(period['music_folder'])
        if not folder.is_absolute() or folder == Path('/pirateradio') or folder in folders:
            raise ValueError('Day music folders must be distinct absolute paths')
        folders.add(folder)
        for name in ('news_play_interval_seconds', 'weather_play_interval_seconds',
                     'news_refresh_interval_seconds', 'weather_refresh_interval_seconds'):
            value = period[name]
            if not isinstance(value, int) or isinstance(value, bool) or not 60 <= value <= 604800:
                raise ValueError('Day interval must be 60 seconds to seven days: ' + name)
    if any(value != 1 for value in coverage):
        raise ValueError('Day periods must cover every minute exactly once')


def current_period(config, timestamp=None):
    schedule = config.get('day_schedule', {})
    if not schedule.get('enabled'):
        return None
    local = dt.datetime.fromtimestamp(time.time() if timestamp is None else timestamp,
                                     ZoneInfo(schedule['timezone']))
    value = local.hour * 60 + local.minute
    for name, period in schedule['periods'].items():
        if contains(minute(period['start']), minute(period['end']), value):
            return name
    raise ValueError('No day period covers the current time')


def effective_config(config, timestamp=None):
    result = dict(config)
    name = current_period(config, timestamp)
    if name is not None:
        period = config['day_schedule']['periods'][name]
        for key in ('news_play_interval_seconds', 'weather_play_interval_seconds'):
            result[key] = period[key]
        result['news_generation_interval_seconds'] = period['news_refresh_interval_seconds']
        result['weather_generation_interval_seconds'] = period['weather_refresh_interval_seconds']
        result['generation_interval_seconds'] = min(period['news_refresh_interval_seconds'],
                                                     period['weather_refresh_interval_seconds'])
        result['interval_seconds'] = min(period['news_play_interval_seconds'],
                                         period['weather_play_interval_seconds'])
    result['active_day_period'] = name
    return result


def scan(folder, excluded=()):
    result = []
    excluded = {Path(p).resolve() for p in excluded}
    for directory, children, files in os.walk(folder):
        children[:] = sorted(c for c in children if (Path(directory) / c).resolve() not in excluded)
        for filename in sorted(files):
            path = Path(directory) / filename
            if path.suffix.lower() in EXTENSIONS and path.is_file() and path.stat().st_size > 0:
                result.append(str(path))
    return result


def music_pool(config, root='/pirateradio', timestamp=None):
    name = current_period(config, timestamp)
    reserved = [p['music_folder'] for p in config.get('day_schedule', {}).get('periods', {}).values()]
    main = scan(root, reserved + [str(Path(root) / 'announce')])
    if name:
        folder = config['day_schedule']['periods'][name]['music_folder']
        specific = scan(folder)
        if specific:
            return folder, specific
    return root, main


def transition_pool(config, root='/pirateradio/announce', timestamp=None):
    periods = config.get('day_schedule', {}).get('periods', {})
    reserved = [p.get('transition_folder', str(Path(root)/name)) for name,p in periods.items()]
    shared = scan(root, reserved)
    name = current_period(config, timestamp)
    if name:
        folder = periods[name].get('transition_folder', str(Path(root)/name))
        specific = scan(folder)
        if specific:
            return specific
    return shared


def attach_music(namespace, config_path):
    from .common import load_config
    config = load_config(config_path)
    if 'day_schedule' not in config or namespace.get('_daypart_attached'):
        return False
    namespace['_daypart_attached'] = True
    cached_config = config

    def settings():
        nonlocal cached_config
        try:
            cached_config = load_config(config_path)
        except (OSError, ValueError, KeyError, TypeError):
            LOG.warning('Day settings reload failed; retaining last valid configuration')
        return cached_config


    def merge_attributes(files):
        folder, _ = music_pool(settings())
        namespace['CSV_FILE_PATH'] = str(sync_folder(folder, files))

    def build_files():
        config = settings()
        sync_all(config)
        namespace['CSV_FILE_PATH'] = '/pirateradio/song_attributes.csv'
        reserved = [p['music_folder'] for p in config['day_schedule']['periods'].values()]
        files = scan('/pirateradio', reserved + ['/pirateradio/announce'])
        announcements = transition_pool(config)
        length = max(len(files), len(announcements))
        return (namespace['extend_list_to_length'](files, length),
                namespace['extend_list_to_length'](announcements, length))

    def play_songs(original_files, announcements):
        signature, queue, index, announce_index = None, [], 0, 0
        with open(os.devnull, 'w') as silent:
            while True:
                config = settings()
                folder, files = music_pool(config)
                selected = (folder, tuple(files))
                if selected != signature:
                    merge_attributes(files)
                    if signature is None and folder == '/pirateradio':
                        queue = list(original_files)
                    else:
                        queue = namespace['reorder_file_list'](list(files), namespace['load_song_data']())
                    if namespace['shuffle']:
                        namespace['random'].shuffle(queue)
                    index, signature = 0, selected
                    LOG.info('Day period %s; music pool %s (%s songs)',
                             current_period(config) or 'disabled', folder, len(files))
                if index >= len(queue):
                    if not queue:
                        time.sleep(1)
                    return
                active_announcements = transition_pool(config)
                if active_announcements:
                    announcement = active_announcements[announce_index % len(active_announcements)]
                    announce_index += 1
                    LOG.info('Playing announcement %s', announcement)
                    namespace['subprocess'].call(['ffmpeg', '-i', announcement, '-f', 's16le',
                        '-acodec', 'pcm_s16le', '-ac', '2' if namespace['play_stereo'] else '1',
                        '-ar', '44100', '-'], stdout=namespace['music_pipe_w'], stderr=silent)
                # An announcement can straddle a boundary; choose the song using
                # the period that applies when the announcement has finished.
                config = settings()
                folder, files = music_pool(config)
                selected = (folder, tuple(files))
                if selected != signature:
                    merge_attributes(files)
                    queue = namespace['reorder_file_list'](list(files), namespace['load_song_data']())
                    if namespace['shuffle']:
                        namespace['random'].shuffle(queue)
                    index, signature = 0, selected
                    LOG.info('Day period %s; music pool %s (%s songs)',
                             current_period(config) or 'disabled', folder, len(files))
                if not queue:
                    time.sleep(1)
                    return
                song = queue[index]
                index += 1
                LOG.info('Playing song %s', song)
                namespace['subprocess'].call(['ffmpeg', '-i', song, '-f', 's16le',
                    '-acodec', 'pcm_s16le', '-ac', '2' if namespace['play_stereo'] else '1',
                    '-ar', '44100', '-'], stdout=namespace['music_pipe_w'], stderr=silent)

    namespace['build_file_list'] = build_files
    namespace['ensure_csv_up_to_date'] = merge_attributes
    namespace['play_songs'] = play_songs
    LOG.info('Day-aware music hook attached; period changes apply between songs')
    return True
