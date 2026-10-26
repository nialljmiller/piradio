"""Fish Audio speech, pinned to the free model with no paid fallback."""
import hashlib
import datetime as dt
import io
import json
import os
import subprocess
import urllib.request
import wave
from pathlib import Path

FREE_MODEL = 's2.1-pro-free'
FREE_THROUGH = dt.date(2026, 11, 30)


def amplify_pcm(pcm, rate, channels, gain):
    if gain == 1:
        return pcm
    process = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-f', 's16le', '-ar', str(rate), '-ac', str(channels), '-i', 'pipe:0',
        '-af', f'volume={gain},alimiter=limit=0.98:level=false:latency=true',
        '-f', 's16le', '-ar', str(rate), '-ac', str(channels), 'pipe:1'],
        input=pcm, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if process.returncode or len(process.stdout) != len(pcm):
        raise ValueError('Speech gain processing failed')
    return process.stdout


class Fish:
    def __init__(self, config, budget):
        self.config, self.budget = config, budget
        self.key = os.environ.get('FISH_API_KEY', '')
        if not self.key:
            raise ValueError('FISH_API_KEY is not configured')

    def references(self):
        settings = self.config.get('fish_references')
        if settings is None:
            settings = [{'audio': self.config['fish_reference_audio'],
                         'text': self.config['fish_reference_text']}]
        if not isinstance(settings, list) or not 1 <= len(settings) <= 5:
            raise ValueError('One to five voice references required')
        result, total = [], 0
        for reference in settings:
            path, text = Path(reference['audio']), reference['text']
            if not path.is_absolute() or path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError('Invalid or oversize voice reference')
            if not isinstance(text, str) or not 1 <= len(text) <= 2000:
                raise ValueError('Voice reference transcript is required')
            audio = path.read_bytes()
            total += len(audio)
            if total > 4 * 1024 * 1024:
                raise ValueError('Combined voice references exceed limit')
            result.append({'audio': audio, 'text': text})
        return result

    def cache_identity(self):
        return ['fish', FREE_MODEL, [[hashlib.sha256(r['audio']).hexdigest(), r['text']]
                                    for r in self.references()]]

    def voice(self, script):
        if dt.datetime.now(dt.timezone.utc).date() > FREE_THROUGH:
            raise ValueError('Fish free window needs verification before further requests')
        import msgpack
        body = {'text': script, 'references': self.references(),
                'format': 'wav', 'sample_rate': 44100, 'latency': 'normal',
                'temperature': 0.7, 'top_p': 0.7,
                'prosody': {'speed': 1, 'volume': 0, 'normalize_loudness': True}}
        payload = msgpack.packb(body, use_bin_type=True)
        self.budget.reserve('voice', self.config['max_clip_seconds'])
        request = urllib.request.Request('https://api.fish.audio/v1/tts', data=payload,
            headers={'Authorization': 'Bearer ' + self.key,
                     'Content-Type': 'application/msgpack', 'model': FREE_MODEL})
        with urllib.request.urlopen(request, timeout=75) as response:
            result = response.read(12 * 1024 * 1024 + 1)
        if len(result) > 12 * 1024 * 1024:
            raise ValueError('Oversize speech response')
        with wave.open(io.BytesIO(result)) as wav:
            if wav.getsampwidth() != 2 or wav.getnchannels() not in (1, 2):
                raise ValueError('Unsupported generated audio')
            rate, channels = wav.getframerate(), wav.getnchannels()
            if not 8000 <= rate <= 96000:
                raise ValueError('Unsupported generated sample rate')
            pcm = wav.readframes(self.config['max_clip_seconds'] * rate + 1)
            duration = len(pcm) / (rate * channels * 2)
            if not 2 <= duration <= self.config['max_clip_seconds']:
                raise ValueError('Generated audio duration outside limits')
        # Streaming WAV headers can advertise an unknown (0xffffffff) length.
        # Validate actual PCM bytes and rebuild a finite header for the cache.
        output = io.BytesIO()
        pcm = amplify_pcm(pcm, rate, channels, self.config.get('fish_speech_gain', 1.0))
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(pcm)
        return output.getvalue(), duration
