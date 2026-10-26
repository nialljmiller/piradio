"""Deploy revised writing and retire cached memoir bulletins without restarting FM."""
import fcntl
import os
import pwd
import shutil
import sys
from pathlib import Path
sys.path.insert(0, '/home/njm/piradio/modules')
from internet.common import read_json, atomic_json
from internet.worker import current_news, usable_news_excerpt
state = Path('/var/lib/piradio-internet')
with (state/'worker.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    for name in ('segments.py','worker.py'):
        shutil.copyfile(Path(__file__).parent/name,Path('/usr/local/lib/piradio/internet')/name)
    catalog = read_json(state/'catalog.json',{})
    def unsuitable(section):
        return section.get('kind') == 'news' and any((not current_news(r) or not usable_news_excerpt(r)) for r in section.get('sources',[]))
    news = catalog.get('sections',{}).get('news',{})
    if unsuitable(news):
        catalog['sections'].pop('news',None)
        catalog['clips'] = [c for c in catalog.get('clips',[]) if not any(unsuitable(s) for s in c.get('sections',[]))]
        catalog['last_news_generation'] = 0
        atomic_json(state/'catalog.json',catalog)
        user = pwd.getpwnam('njm'); os.chown(state/'catalog.json',user.pw_uid,user.pw_gid)
        print('Retired cached retrospective; current news refresh due.')
    print('Revised news writing deployed; FM playback retained.')
