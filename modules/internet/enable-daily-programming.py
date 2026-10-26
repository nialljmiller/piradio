"""Deploy eight news/weather refreshes and one daily reusable connector set."""
import fcntl
import json
import shutil
from pathlib import Path
state=Path('/var/lib/piradio-internet')
with (state/'worker.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    for name in ('worker.py','segments.py','cli.py','grok.py','cadence.py','daily_connectors.py','common.py'):
        shutil.copyfile(Path(__file__).parent/name,Path('/usr/local/lib/piradio/internet')/name)
    path=Path('/etc/piradio-internet/config.json');config=json.loads(path.read_text())
    backup=path.with_name('config.before-daily-programming.json')
    if not backup.exists():shutil.copy2(path,backup)
    config.update(daily_connectors=True,section_prompt_limits={'news':8,'weather':8},
        rewrite_weather_each_refresh=True,reuse_recent_news_candidates=True,
        max_text_calls_per_day=17,max_text_tokens_per_day=160000,
        news_generation_interval_seconds=10800,weather_generation_interval_seconds=10800,
        generation_interval_seconds=10800)
    for period in config['day_schedule']['periods'].values():
        period.update(news_refresh_interval_seconds=10800,weather_refresh_interval_seconds=10800)
    tmp=path.with_suffix('.daily.tmp');tmp.write_text(json.dumps(config,indent=2)+'\n');tmp.chmod(0o644);tmp.replace(path)
    override=Path('/etc/systemd/system/piradio-internet.service.d/daily-programming.conf')
    override.parent.mkdir(exist_ok=True);override.write_text('[Service]\nTimeoutStartSec=15min\n')
    print('News/weather: every 3 hours, max 8 each per local day. Daily connector set enabled.')
    print('Shared text limits: 17 calls, 160000 reserved units. Voice cap unchanged.')
