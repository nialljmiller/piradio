"""Subscription-authenticated CLI text generation using existing bulletin prompts."""
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from .worker import Gemini


class CLIUnavailable(RuntimeError):
    pass


class SubscriptionCLI(Gemini):
    def __init__(self, config, budget):
        self.config, self.budget = config, budget
        self.name = config['text_provider']
        # Cooldown identifies CLI auth files rather than the unused API key.
        auth = Path.home()/('.grok/auth.json' if self.name=='grok-cli' else '.gemini/antigravity-cli/antigravity-oauth-token' if config.get('gemini_cli_kind') == 'antigravity' else '.gemini/oauth_creds.json')
        self.key = str(auth.stat().st_mtime_ns) if auth.exists() else 'not-signed-in'

    def request(self, kind, body):
        if kind != 'text':
            raise ValueError('Subscription CLI only provides text')
        prompt = body['system_instruction'] + '\n\n' + body['input']
        self.budget.reserve('text', len(prompt.encode()) + 1536 + 512)
        from .cadence import reserve
        reserve(self.config, getattr(self, '_section_categories', []))
        env = os.environ.copy()
        for name in ('GEMINI_API_KEY','GOOGLE_API_KEY','XAI_API_KEY','GROK_API_KEY','GROK_DEPLOYMENT_KEY','FISH_API_KEY','GOOGLE_APPLICATION_CREDENTIALS'):
            env.pop(name,None)
        env['NO_COLOR']='1'
        env['PATH']='/home/njm/.local/share/piradio-node/bin:' + env.get('PATH','/usr/bin:/bin')
        env['NODE_OPTIONS']='--max-old-space-size=192'
        if self.name == 'gemini-cli':
            env['GEMINI_CLI_TRUST_WORKSPACE']='true'
        if self.name == 'grok-cli':
            executable = self.config.get('grok_cli_path','/home/njm/.grok/bin/grok')
            command = [executable,'-p',prompt,'--output-format','plain','--max-turns','1',
                       '--tools','','--no-subagents','--no-memory','--no-plan','--disable-web-search',
                       '--reasoning-effort','low']
        else:
            executable = self.config.get('gemini_cli_path','/home/njm/.npm-global/bin/gemini')
            command = [executable,'-p',prompt,'--output-format','json']
            if self.config.get('gemini_cli_kind') == 'antigravity':
                command.extend(['--model', self.config.get('gemini_cli_model','gemini-3.8-flash-medium'), '--disable-slash-commands', '--print-timeout', str(self.config.get('cli_timeout_seconds',120))+'s'])
        # Isolated empty directory prevents repository context influencing bulletins.
        work = Path(self.config['state_dir'])/'cli-work'
        work.mkdir(parents=True,exist_ok=True)
        if self.name == 'gemini-cli' and self.config.get('gemini_cli_kind') != 'antigravity':
            settings = work / '.gemini'
            settings.mkdir(exist_ok=True)
            (settings / 'settings.json').write_text(json.dumps({'tools': {'core': []}, 'mcp': {'allowed': []}, 'context': {'includeDirectoryTree': False}}))
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            try:
                process = subprocess.Popen(command,cwd=work,env=env,stdin=subprocess.DEVNULL,
                                           stdout=output,stderr=errors,start_new_session=True)
            except OSError as exc:
                raise CLIUnavailable('CLI executable unavailable; sign-in/setup required') from exc
            try:
                status = process.wait(timeout=self.config.get('cli_timeout_seconds',120))
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait()
                raise CLIUnavailable('CLI timed out; fallback retained') from exc
            if status:
                # Don't log CLI diagnostics: authentication responses can contain tokens.
                raise CLIUnavailable(f'{self.name} exited with status {status}; check subscription login')
            output.seek(0)
            raw = output.read(65537)
            if len(raw)>65536:
                raise CLIUnavailable('CLI response exceeded size limit')
        text=raw.decode('utf-8').strip()
        if self.name=='gemini-cli':
            result=json.loads(text)
            if self.config.get('gemini_cli_kind') == 'antigravity' and result.get('status') != 'SUCCESS':
                raise CLIUnavailable('Google CLI returned an unsuccessful response')
            text=result.get('response','')
        if not isinstance(text, str) or not text.strip():
            raise CLIUnavailable('CLI returned no usable text; fallback retained')
        if text.startswith('```'):
            text='\n'.join(text.splitlines()[1:-1]).strip()
        return {'status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':text}]}]}
