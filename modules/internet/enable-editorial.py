"""Broader editorial batch and news-first segmented playback; no FM restart."""
import fcntl
import json
import os
import pwd
import shutil
import sys
from pathlib import Path
sys.path.insert(0,'/home/njm/piradio/modules')
from internet.common import read_json,atomic_json
root=Path(__file__).parent
state=Path('/var/lib/piradio-internet')
with (state/'worker.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    for name in ('worker.py','common.py','segments.py','cli.py'):
        shutil.copyfile(root/name,Path('/usr/local/lib/piradio/internet')/name)
    config=Path('/etc/piradio-internet/config.json')
    data=read_json(config,{})
    data.update(news_candidate_limit=12,news_target_seconds=30,weather_target_seconds=25)
    data['gemini_cli_path']='/home/njm/.npm-global/bin/gemini'
    if data.get('google_cli_verified'):data['text_provider']='random-cli'
    atomic_json(config,data);config.chmod(0o644)
    catalog=read_json(state/'catalog.json',{})
    for clip in catalog.get('clips',[]):
        sections=clip.get('sections',[])
        if not sections or not clip.get('piece_choices'):continue
        old=clip['piece_choices']; pairs={s['kind']:old[1+i*2:3+i*2] for i,s in enumerate(sections)}
        clip['sections']=sorted(sections,key=lambda s:0 if s['kind']=='news' else 1)
        clip['piece_choices']=[old[0]]
        for section in clip['sections']:clip['piece_choices'].extend(pairs[section['kind']])
        clip['piece_choices'].append(old[-1])
    atomic_json(state/'catalog.json',catalog)
    user=pwd.getpwnam('njm');os.chown(state/'catalog.json',user.pw_uid,user.pw_gid)
    print('Editorial batch: 12 candidates; order: intro, news, weather, outro. Writer:',data['text_provider'])
