"""Local-date section request limits shared across all text providers."""
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
from .common import atomic_json,read_json


def day(config):
    return dt.datetime.now(ZoneInfo(config.get('day_schedule',{}).get('timezone','America/New_York'))).date().isoformat()


def eligible(config, groups):
    ledger=read_json(Path(config['state_dir'])/'section-prompts.json',{}) if config.get('section_prompt_limits') else {}
    usage=ledger.get(day(config),{})
    return {k:v for k,v in groups.items() if not config.get('section_prompt_limits') or usage.get(k,0)<config['section_prompt_limits'].get(k,8)}


def reserve(config, kinds):
    if not kinds or not config.get('section_prompt_limits'):
        return
    path=Path(config['state_dir'])/'section-prompts.json'
    ledger=read_json(path,{})
    usage=ledger.setdefault(day(config),{})
    for kind in kinds:
        usage[kind]=usage.get(kind,0)+1
    atomic_json(path,ledger)
