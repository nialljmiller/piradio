# Optional internet bulletins

The Zero 2 W retrieves news and weather, uses the configured API or subscription CLI to write standalone stories, caches generated speech, and mixes bulletins over the existing FM music stream. Model inference happens remotely; playback only uses cached audio. The original music attribute CSV and nearest-neighbour song ordering are preserved.

## Current news policy

- News-feed requests are gated by `news_feed_interval_seconds` (10800 seconds,
  three hours). The ten-minute systemd timer may wake for weather or cache work,
  but does not fetch news between those windows. Empty and failed fetch attempts
  also consume a window; urgent stories do not bypass this gate.
- Enable `news_story_pool` to add independent, fresh stories at each check.
  `news_stories_per_refresh` (12) is a maximum candidate batch, not a promise to
  synthesize twelve recordings. `news_budget_aware` sizes it against remaining
  voice calls and reserved duration, spreading capacity over the day and reserving
  weather and daily connectors. Existing request, duration and category caps stay
  in force. When capacity is reserved or exhausted, cached playback continues.
- The pool retains up to `news_story_pool_limit` (96) unexpired stories. The
  24-hour `news_story_ttl_seconds` is measured from source publication when known,
  otherwise from story creation. Banned sources remain excluded at playback.
- Each bulletin selects two distinct stories. Never-heard stories get priority;
  otherwise selection favours the oldest eligible three with weights 85:12:3.
  The last story is excluded, and pools of four or more protect the last two.
  This gives a strong recency preference without a fixed repeating loop.
- The last `news_story_history_limit` (192) selections persist across restarts
  and weather-only bulletins. Selection is recorded before airing. Playback
  requires two valid stories and never pairs a story with itself.

All existing spending limits are preserved: the example has 17 text calls,
160,000 estimated text units, 24 voice calls and 1440 reserved voice seconds per
UTC day. Category and daily-connector ledgers use station-local dates. These are
local ceilings; provider/account quotas remain separate.

## Configuration

The deployed configuration is `/etc/piradio-internet/config.json`; start with `config.example.json`.

- `host_name`, `station_name`: introduction identity.
- `voice_provider`: `fish` for reference-guided free Fish Audio speech, or `gemini` for Gemini speech.
- `fish_reference_audio`, `fish_reference_text`: absolute path to a clean reference WAV and its transcript. `fish_references` optionally supplies several objects with `audio` paths and matching `text` transcripts (maximum five, combined 4 MiB), overriding the single reference. Reference audio is sent to Fish Audio for synthesis. `python3-msgpack` is the only additional dependency. Fish requests are hard-pinned to `s2.1-pro-free`, with no automatic paid fallback.
- `voice`, `voice_style`: available Gemini voice and natural-language writing/speech direction. Style descriptions do not guarantee an exact actor or character voice.
- `topics`: objects containing a `name` and `keywords`. Empty keywords accept that feed's topic without filtering. Topics can have `enabled: false`.
- `feeds`: HTTPS RSS/Atom sources with a display name and associated topics. Up to eight feeds are fetched, with bounded responses and timeouts. Items need publication dates and must be within 24 hours.
- `preferred_news_sources`, `banned_news_sources`: domains or HTTP(S) URLs. Domains include subdomains. Bans override preferences and are checked before text generation, speech generation, and cached playback. Preferences rank eligible reports rather than excluding all other sources.
- `weather`: location name and coordinates for the National Weather Service forecast.
- `generation_interval_seconds`: minimum spacing between new script attempts; default two hours; news has its own six-hour interval.
- `interval_seconds`: check for an eligible cached bulletin every 20 minutes of playback.
- `repeat_after_seconds`, `max_repeats_per_news_recording`: minimum repeat gap (20 minutes from bulletin start), and maximum extra news plays (17).
- `news_ttl_seconds`: six-hour news expiry; `weather_ttl_seconds` is three hours, bounded by the forecast period end. The two-hour refresh interval leaves a one-hour buffer for failures.
- `max_*_per_day`: request, estimated text allowance, and voice duration allowances. Failed requests consume their reserved allowance. The segmented defaults cap text requests at 16/day and voice requests at 24/day. These are local ceilings, not provider quotas or a guarantee of success.

Topics and source preferences must be accompanied by suitable configured feeds. This free-tier version automatically retrieves feeds and weather; it does not offer unrestricted LLM web search. Google Search grounding is unavailable on the free API tier of the new-project text model, `gemini-3.5-flash-lite`.

## Installation and activation

Run `sudo bash modules/internet/install.sh` from the repository. This stages the module and services without enabling the timer or changing playback. The service currently expects the `njm` account on the migrated Pi.

Store `GEMINI_API_KEY=your-key` in `/etc/piradio-internet/credentials.env`, owned by root with mode 0600. For Fish speech, also add `FISH_API_KEY=your-key` to that file. Keep credentials outside the repository. Use a Gemini API project with billing disabled for zero-charge operation. Consumer chat allowances are separate from API quotas; free API availability can change.

Run `sudo python3 modules/internet/activate.py`. It generates and validates a first cached recording under the restricted worker service, then installs the optional foreground playback hook and enables the timer. If activation fails, it restores original playback. Activation restarts the station once. Configuration changes affecting playback need a station restart; worker changes take effect on its next run.

Inspect the worker with `journalctl -u piradio-internet.service`. Inspect station playback with `journalctl -u pirateradio`. The timer wakes every ten minutes, but actual news-feed requests are gated to three-hour windows. News generation runs at eligible checks within the existing daily allowances. A forecast nearing its period end may refresh early. Cached replay uses no API requests. Text allowances are local conservative estimates, not provider monetary caps. For speech failures the script is cached before synthesis, avoiding a new text request on retry.

Music keeps advancing while a bulletin plays over it. The music gain falls smoothly to `music_duck_gain` (default 0.08, approximately -22 dB), then returns to full volume over `duck_fade_seconds` (default 0.3 seconds). If a song ends while a bulletin is speaking, the next pirate announcement waits for the bulletin to finish. Files under an `announce` directory are never interrupted; long announcement files can delay a bulletin. No bulletin enters the music attribute CSV. Missing Wi-Fi, expired clips or generation failures leave the original station playing.

To disable, set `enabled` false in the configuration, run `sudo systemctl disable --now piradio-internet.timer`, and restart `pirateradio`. The original launcher is backed up at `/usr/local/lib/piradio/foreground.before-internet.py`.

## Verification

From the repository root:

```sh
python3 -m unittest discover -s modules/internet/tests -v
```

Tests cover domain bans, identity prompts, repeat limits, disabled operation, music timeline preservation and volume recovery through mixing, announcement pass-through and corrupt-cache fallback. Provider calls and RF reception require separate deployment checks.

Fish commissioning produced a validated 9.1-second Reginald Radio introduction using an existing pirate interlude. The user confirmed successful reception and music ducking, but wanted a raspier voice. FakeYou legacy synthesis returned a dead job titled "Legacy TTS is retired" and is not integrated.

## Reusable bulletin pieces

`segmented_bulletins: true` generates independent factual news and weather sections in one Gemini request when needed. Fresh unchanged sections retain their audio. A freshly retrieved unchanged forecast renews validity without another text or speech request. News refreshes at most every `news_generation_interval_seconds` (six hours); weather is checked at the two-hour generation interval. Both depend on eligible current reports and successful provider responses.

`connectors` holds three editable alternatives each for `intro`, `weather`, `news`, and `outro`. Only `{host_name}` and `{station_name}` are template placeholders. Prepare the persistent library explicitly under the usual daily budget, with the credentials loaded into the environment:

```sh
PYTHONPATH=/usr/local/lib/piradio python3 -m internet.worker prepare-connectors
```

The command caches every successful piece and can resume after reaching the daily limit. Prepare it before activation. A changed reference or voice requires preparing its new library; existing audio is keyed by script and reference identity. Connectors require 12 initial Fish calls; reuse makes zero calls. No separate LLM calls write connectors.

Playback selects a different available connector for each category than on the preceding completed bulletin, including across news refreshes. With three alternatives per category there are 81 possible four-connector combinations; content remains identical until refreshed. The music stays ducked across the entire assembly and its short internal pauses. Individual generated pieces are limited to `max_clip_seconds` (60 seconds); the locally assembled result can reach `max_bulletin_seconds` (180 seconds). The 60-second bound is our application setting, not a verified Fish provider limit. Oversize assemblies are rejected rather than silently truncated.

The first bulletin is eligible 30 seconds after boot (`first_bulletin_delay_seconds`). Twenty-minute scheduling targets 72 starts per 24 hours of continuous playback, measured from bulletin start; spoken song transitions, failures and lack of valid cached content can delay or skip a slot. At most 12 two-hour forecast updates plus four six-hour news updates require 16 Fish calls/day in steady operation, often fewer due to unchanged data. One Gemini request batches categories when both change, normally at most 12 scheduled text requests/day. Forecast period boundaries can cause additional early refreshes, still under the configured daily ceilings. The local ceilings of 24 voice calls/1440 reserved seconds and 16 text calls/80000 estimated allowance leave limited headroom for failures and commissioning; retries also consume allowance. Cached playback uses no model tokens.

`text_failure_fallback: true` reads source-attributed headlines and the exact forecast fields when Gemini returns 402/429/server failures or the local text budget is reached. No language model writes these fallback scripts. A payment error starts a 24-hour cooldown, cleared immediately when the credential changes, avoiding repeated failed requests. The current Gemini project reports depleted prepayment credit; commissioning uses this fallback without changing billing.

Fish publishes no numeric daily cap for `s2.1-pro-free`, subject to fair use and concurrency constraints. Its free window is currently stated to run through November 30, 2026; this is not a perpetual free-service guarantee. The header remains hard-pinned and there is no paid-model fallback. Speech requests stop after the confirmed November 30 deadline until free access has been reverified and the deadline explicitly updated; music continues. Sources: https://docs.fish.audio/developer-guide/models-pricing/pricing-and-rate-limits and https://fish.audio/blog/s2-1-pro-free-api/ .

Commissioning can use a separate state directory with `budget_state_dir` pointing to the main state directory so previews share the same daily ledger. This holds the complete bulletin off air while preparing a listening test.

Live deployment uses the 12-piece library, three existing pirate reference clips, a complete locally assembled weather/news bulletin, the foreground mixer, and enabled boot services. Local and Pi verification passes 30 tests. Full microphone/RF voice quality still depends on the listening test.

## Speech level and story priority

`fish_speech_gain: 1.25` raises generated speech by approximately 1.94 dB with a 0.98 peak limiter; music ducking is unchanged. The deployed existing speech pieces were processed to match, so the level change applies without restarting playback.

`news_topic_priorities` puts NC Triangle (90), astronomy (85), science and technology (80) above routine world news (10). Recent coverage rotates among local/science/tech topics while routine world reports remain behind those categories. `priority_override_patterns` are configurable regular expressions matching fresh breaking or major-event headlines. Matches within `priority_override_max_age_seconds` (four hours) receive `priority_override_score` (200), ahead of routine topics. These are conservative headline rules, not an LLM importance judgment or a guarantee of comprehensive breaking-news detection.

Feeds are polled at the ten-minute freshness check even while the normal generation interval has not elapsed. An unseen urgency match can bypass the two-hour generation and six-hour news spacing, under the same daily API ceilings. Source bans remain authoritative. Urgency checks make no additional LLM requests.

## Optional day-aware operation

`day_schedule.enabled` is true in this installation; set it false to return to the global intervals and main music pool. `day_schedule.timezone` is `America/New_York`, independent of the Pi display timezone and following daylight saving time automatically. The four periods cover every minute exactly once:

| Period | Local time | Music folder |
| --- | --- | --- |
| morning | 05:00–10:00 | `/pirateradio/morning` |
| day | 10:00–17:00 | `/pirateradio/day` |
| evening | 17:00–19:00 | `/pirateradio/evening` |
| night | 19:00–05:00 | `/pirateradio/night` |

Each period has four independent settings, in seconds: `news_play_interval_seconds`, `weather_play_interval_seconds`, `news_refresh_interval_seconds`, and `weather_refresh_interval_seconds`. All initially use the existing defaults: 1200, 1200, 21600, and 7200 respectively. Later changes reload during playback (within a minute) and on the next worker run; a restart is unnecessary for schedule settings. A music-pool change waits until the current song and any spoken transition have finished.

An occupied period folder supplies that period's music, including its subfolders. A folder with no supported nonempty audio files falls back to the main music library. Period folders and `/pirateradio/announce` are excluded from the main music scan, including when the day feature is disabled, so inactive periods never leak into the default pool. Supported extensions match the original player: AAC, MP3, WAV, FLAC and M4A. All existing music stays in place. New files inherit attributes from matching existing filenames when available, otherwise default to 50/50; CSV rows for every pool are retained. The original nearest-neighbour ordering function is used for each selected pool.

News and weather have separate playback clocks. When both are due they share one assembled bulletin; if only one is due, only its transition and content play, with the common introduction and sign-off. Period changes can shorten or lengthen the next interval. The existing music mixing and source policy remain in effect.

Refresh intervals control regular content updates independently: a news-only update does not fetch or regenerate weather before its interval, and unchanged fresh forecasts reuse their existing speech. Feed checks for breaking headlines remain every ten minutes; breaking updates and forecast-expiry safety checks can override the regular refresh spacing. Daily generation limits remain global and unchanged, not multiplied by four periods. A shorter requested interval cannot bypass source freshness, failed APIs or the daily ceilings.

### Per-folder song attributes

At each station boot, the main library and all configured period folders get
an independent `song_attributes.csv`. Existing rows and scores are preserved;
only missing songs are estimated and appended. The player reads the selected
folder's CSV for its original attribute-based ordering. Adding tracks also
triggers an incremental scan when that music pool changes.

The shared guesser analyses at most 45 seconds of mono audio with FFmpeg and
NumPy. Energy uses loudness, envelope changes and spectral brightness; organics
uses spectral tonality. These are heuristic estimates, not exact genre labels.
Fixed scales allow single-song additions without normalising against a batch.
It requires no network, tokens or librosa. Failed/invalid audio is logged and
left unscored for retry on the next scan; existing manual values are never
replaced automatically, including existing 50,50 values.

Choose a folder manually on the Pi:

```sh
sudo python3 /home/njm/piradio/scripts/auto_score.py --folder morning
sudo python3 /home/njm/piradio/scripts/auto_score.py --folder main
sudo python3 /home/njm/piradio/scripts/auto_score.py --folder all
```

`--folder` also accepts an absolute directory. Add `--rescore-all` only to
intentionally overwrite existing scores. Long first-time scans delay station
startup; later boots analyse only new songs. Announcement clips are excluded.

### Interactive YouTube importer

Run `sudo piradio-download` on the Pi. It extends `scripts/yt-mp3.py`:
choose main/morning/day/evening/night by number or name, paste a single-video
YouTube link, then enter energy and organics (0–100; Enter defaults to 50).
The selected folder is retained while links repeat indefinitely; an empty link
exits. Ctrl+C also exits. Download errors return to the link prompt.

The importer accepts watch, youtu.be, music, mobile, shorts, live and embed
links, removes tracking/playlist parameters, downloads one audio track and
converts to 192 kbps MP3. Completed audio is staged outside the library until
scores are saved to that folder's CSV, then published atomically. The radio
can pick it up between tracks without a restart. Filenames include the video
ID, and duplicates preserve the existing file and scores.

Dependencies are installed in `/home/njm/.local/share/piradio-downloader`,
with Deno at `/home/njm/.local/bin/deno`. Updating yt-dlp and its bundled
challenge solver: `/home/njm/.local/share/piradio-downloader/bin/pip install
-U 'yt-dlp[default]'`. YouTube may reject individual videos or require sign-in;
those errors are displayed without breaking the import loop.

News writing explains concrete developments from supplied summaries rather than
reading headlines. Obvious first-person recollection headlines are excluded.
The LLM prompt requests what happened and source-supported significance, with
restrained pirate vocabulary and respectful serious-news coverage. When text
API access is unavailable, the fallback reads bounded source summary sentences
with attribution and light pirate framing; it skips headline-only entries and
does not invent explanations. It uses the existing RSS excerpts, without extra
article-fetch or model calls. Cached retrospective bulletins are retired on
this deployment; unchanged connectors and weather recordings stay reusable.

Transitions also follow the day schedule. Each period's `transition_folder`
(default `/pirateradio/announce/morning`, `/day`, `/evening`, `/night`) is used
when populated; otherwise only the shared clips directly in the announcement
pool are used. Other period folders are excluded from the shared scan. Period
selection is checked before every transition. The long GTA/Fallout radio-stream MP3s belong in the main music library,
not the talking-transition folders. Their baked-in introductions are preserved;
the normal talking clip before each MP3 is accepted. Add morning-specific short clips to `/pirateradio/announce/morning`.

### Gemini or Grok text generation

`text_provider` selects `gemini` (default) or `grok`. Gemini uses `text_model`
and `GEMINI_API_KEY`; Grok uses `grok_text_model` (default `grok-4.7`),
`grok_max_tokens` (1536 including reasoning, configurable 64–4096), and
`XAI_API_KEY` in the existing root-only
`/etc/piradio-internet/credentials.env`. Never commit this credentials file.
The worker rereads settings on each run; switching requires no FM restart.

Grok uses xAI Chat Completions with low reasoning effort, JSON output and the
same source-constrained pirate prompts and source-ID validation as Gemini.
Only the selected provider is called; there is no automatic paid failover.
Both use the existing global daily text call/estimated-token allowances,
including failed calls. These allowances are not dollar billing limits.
Cooldowns are separate per provider; Gemini credit exhaustion does not block
Grok. News fetching remains bounded RSS/NWS without extra search-tool charges.
Fish voice generation and reusable audio caches are unchanged.

API billing is separate from app subscription usage. A Gemini HTTP 402 means
API prepayment credits are depleted, not a timeout. Inspect the key's project
and billing account in Google AI Studio. Grok likewise needs an xAI API key
and available API credits. Live Grok activation is pending credentials.

### Subscription CLI text generation (active deployment)

`text_provider: "grok-cli"` invokes the official native Grok CLI as `njm`,
using `grok login --device-auth` subscription credentials in `~/.grok/auth.json`.
No Grok or Gemini API keys are passed to the process. Existing prepared prompts,
RSS/NWS collection, source validation, intervals, daily allowances, Fish voice,
connector reuse and mixing remain in place. Each run is one turn in an empty
working directory with tools, web search, subagents and memory disabled.
Timeouts/nonzero exits fall back to source summaries and cool down for 15 minutes.
CLI diagnostics are not logged to avoid exposing login data. Subscription
quotas still apply; there is no automatic API-key fallback.

Install via the official `https://x.ai/cli/install.sh` script, sign in as njm,
and run `sudo python3 modules/internet/enable-cli.py`, then
`sudo systemctl daemon-reload`. The deployment adds a service override allowing
Grok to refresh its login files, and raises its memory ceiling to 256 MiB.
Music keeps playing. `grok_cli_path` and `cli_timeout_seconds` configure the
binary and timeout (15–240 seconds). Run `grok login --device-auth` without sudo.

The adapter also supports `text_provider: "gemini-cli"` using Gemini CLI's
Google OAuth login and JSON headless output; `gemini_cli_path` selects that
executable. Gemini CLI and its runtime are not installed by this Grok deployment.
Its OAuth/settings directory must be made available to the service if selected.
Do not commit CLI login files or credentials. Model output is still validated
before any voice is generated.

The editorial writer now receives up to `news_candidate_limit` (default 12)
fresh candidates rather than a three-story shortlist. The LLM chooses which
developments deserve airtime using topic priorities and the supplied summaries.
`news_target_seconds` (30) and `weather_target_seconds` (25) produce approximate
word budgets; actual audio remains constrained by the existing clip limits.
The prompt requests sustained pirate vernacular without invented adventures.
News and weather stay independent reusable sections. Playback order is intro,
news joint, news, weather joint, weather, outro; cached sections are reordered
without rerecording voice clips. Only sections due for playback are included.

`text_provider: "random-cli"` selects Grok CLI or Gemini CLI equally at random
for each new text request. This is not alternating and may pick the same writer
several times. Cooldowns are kept per selected CLI and daily allowances remain
shared. Gemini must first be signed in with its subscribed Google account.
Until that login is complete, the active writer stays Grok CLI. Gemini uses the
private Node runtime at `/home/njm/.local/share/piradio-node/bin`, with a bounded
heap and tool-free per-run settings in the isolated work directory.

Google returned `UNSUPPORTED_CLIENT` for the old Gemini CLI after successful
OAuth login. The Google subscription side now uses the official native
Antigravity CLI (`agy`) instead, via `gemini_cli_kind: "antigravity"`,
`gemini_cli_path: "/home/njm/.local/bin/agy"`, and
`gemini_cli_model: "gemini-3.8-flash-medium"`. Authenticate interactively as njm
using `agy`; SSH authentication displays a browser URL and requests its code.
The adapter parses the JSON envelope and requires SUCCESS before validating
bulletin sections. CLI random selection stays disabled until the new Google
backend is live-tested. `google_cli_verified` records that completed check;
old Gemini OAuth credential existence alone does not activate random selection.

Random CLI mode is now activated with both accounts authenticated. Google's
Gemini Flash Medium returned upstream 503 capacity errors; Flash Low is now
selected. Empty responses, including SUCCESS envelopes with empty response
text, are rejected. A CLI on a temporary cooldown is excluded from the random
choice while the other remains available. Google still needs a successful
live generated response after capacity recovers; authentication is complete.

Daily caps are global: 16 text requests combined across the CLIs, plus 80,000
conservative estimated units; the estimate is not a measured CLI token count
and may stop writing before 16 calls. Failed attempts reserve allowance too.
The ledger resets at midnight UTC. Provider subscription quotas are independent
and have not been verified. News typically refreshes 4 times/day and weather
12 times/day at the current per-period defaults. Simultaneous category changes
share one request returning two separately cached scripts. Connectors require
no routine text calls. Unchanged forecasts and reusable audio reduce calls;
urgency and forecast expiry can add refreshes within those caps. Fish retains
its separate 24-call daily cap for changed speech pieces.

### Current daily programming schedule

News and weather each request a new script every three hours in all four day
periods, targeting eight requests of each category per 24 hours. Explicit
`section_prompt_limits` cap each category at eight actual model attempts per
North Carolina local date, shared across Grok and Google. Weather is rewritten
even when its forecast facts are unchanged; fresh, correctly dated recent news
can be reconsidered when there are no unseen stories. Previously seen urgent
headlines do not repeatedly bypass the cadence. Availability/errors can reduce
successful updates; no unsupported facts are invented to fill missing sources.

`daily_connectors: true` adds one newly written intro, news joint, weather joint
and outro per local date. One text request creates all four, with recent cached
examples supplied and instructions to vary wording, imagery and rhythm.
Duplicate wording already anywhere in the library is rejected. Up to three
bounded attempts with 15-minute pauses are allowed after writing failures.
Successful scripts are saved before voicing, so partial Fish failures resume
without another writing request. Four separate new recordings are appended;
old recordings remain available and repeat mixing automatically uses the
expanded library. Daily state is in `daily-connectors.json`; per-category
request accounting is in `section-prompts.json` under the state directory.

The shared text cap is now 17 requests/day and 160,000 conservative estimated
units, accommodating 8 news + 8 weather + 1 daily set even when separate.
Simultaneous news/weather requests share one prompt, normally reducing the
baseline to 9 writing calls. The voice cap remains 24 calls/day: up to 16 new
content clips and 4 daily connectors leaves four calls of margin. Audio pieces
with identical text/voice still use the cache. Playback intervals remain 20
minutes; each time period's refresh intervals now default to 10800 seconds.
Existing global request budgets use UTC dates; category/connector dates use
station-local America/New_York. Install helper: `enable-daily-programming.py`.

### Resumable full-album batch import

The existing `scripts/yt-mp3.py` also supports noninteractive CSV queues:

```sh
sudo /home/njm/.local/share/piradio-downloader/bin/python scripts/yt-mp3.py \
  --batch reports/album-import-filtered.csv --folder main --energy 30 --organics 50
```

The CSV supplies `artist,title,youtube_url,duration,video_title`. Complete MP3s
are atomically published with scores already saved, just like interactive
imports. Artist-prefixed filenames retain YouTube IDs. Existing completed jobs
and files are skipped; a failure is logged and the next job proceeds. Use
`--retry-failed` on a later run to retry recorded failures. The default progress
file is `/var/lib/piradio-download/batch-progress.json`. Disk checks reserve
space for temporary input/output and keep a 2 GiB safety margin.

The `piradio-album-import.service` unit runs the queue independently of SSH,
with low CPU/I/O priority and a one-core/256 MiB ceiling. Start/restart the unit
to resume; it is a finite import task and is not enabled on boot. Check progress
with `journalctl -u piradio-album-import.service -f` and the JSON progress file.
The current queue excludes titles marked mix/mixtape/remix and limits YouTube
runtime to 30–120 minutes. Collections, compilations and remastered versions are excluded too.
EPs and releases classified as mixes/compilations in the official archive are excluded.
The final selected queue has 63 album candidates (37 Macroblank, 26 slowerpace). Unresolved public links are recorded separately.

### Individual cached news stories

Enable `news_story_pool` to cache standalone stories instead of replacing a whole
news report. The first successful refresh seeds two stories in one text request;
subsequent checks request a budget-sized batch of fresh stories and voice only new text. Weather
can share the same text request, and its audio remains separately cached. Existing
news/weather request caps and Fish budgets still apply. Each story is 25–55 words
and must identify the people/organisations and explain the event without assuming
prior context. Raw RSS teasers never substitute for model-written news.

Playback selects two distinct unexpired story recordings with recency-weighted randomness and
retains the reusable intro/news/weather/outro connectors. No text or voice calls
happen during playback. `news_story_ttl_seconds` defaults to 86400 (24 hours),
measured from source publication where available. The pool retains at most `news_story_pool_limit` (96)
stories; banned sources are excluded again at playback. If fewer than two valid
stories remain, playback waits for another budget-permitted refresh; it never pairs a
story with itself or broadcasts a lone story from the pool. Seeding or repairing
an expired pool can require two voice calls, while ordinary updates are limited to the available daily allowance.
