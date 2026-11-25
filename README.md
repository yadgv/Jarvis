# JARVIS — Phase 1

Wake word → Whisper → Claude → Piper voice. Runs on Windows now and on a Raspberry Pi later.

## Windows setup
1. Install Python 3.11 (tick "Add to PATH").
2. In the `jarvis` folder:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Get the British voice:
   ```
   mkdir voices
   python -m piper.download_voices en_GB-alan-medium --data-dir voices
   ```
4. Set your API key (from console.anthropic.com). Easiest: create a file named `.env`
   in the `jarvis` folder containing:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
   (It's git-ignored. Or use `setx ANTHROPIC_API_KEY "sk-ant-..."` and restart your terminal/VS Code.)
   If you run Jarvis with a different Python than the one you installed packages into,
   install them with that Python: `"path\to\python.exe" -m pip install -r requirements.txt`.
   Set your Fish Audio key (fish.audio → API Keys) for the main voice:
   ```
   setx FISH_API_KEY "your-fish-key"
   ```
   Close and reopen the terminal afterwards.
   If Fish Audio fails (no key, no internet, no credits), Jarvis falls back to the
   local Piper "Alan" voice, then to the Windows system voice.
5. Run:
   ```
   python main.py
   ```
   Say **"Hey Jarvis"**, then talk. Say **"Goodbye Jarvis"** to quit.

## Desktop window
```
python gui.py          (or: python main.py --gui)
```
Opens a window with a glowing orb of particles that shows what Jarvis is doing: slow cyan drift
when standing by, green and rippling with your voice while he listens, swirling amber while he
thinks, and pulsing with his voice while he speaks. Below it is the conversation.
Type a message and press Enter, or press **Talk** to speak without the wake word.
While he's speaking the button becomes **Stop** (or press Esc). "Hey Jarvis" still works.
Closing the window turns Jarvis off. `python main.py` still runs him without a window.
If the window doesn't appear, the terminal prints why (lines starting with `[gui]`).

## Tuning
- Jarvis tells speech from noise with a voice detector (webrtcvad), so quiet talking counts.
- It says "no speech detected" when you did talk → lower `MIN_SPEECH_LEVEL` (the log shows how loud you were).
- It never stops listening → raise `VAD_AGGRESSIVENESS` (max 3) or `MIN_SPEECH_LEVEL`.
- People talking in the background keep him listening → raise `SPEAKER_DROP` (e.g. 0.5). The log line `[mic] recorded ...` shows how loud you were and what was ignored.
- It cuts you off mid-sentence → raise `SILENCE_SECONDS` (default 0.6) or lower `SPEAKER_DROP`.
- It cuts you off → raise `SILENCE_SECONDS`.
- Wake word misfires → raise `WAKE_THRESHOLD` (e.g. 0.6).
- To test without the wake word, set `MODE = "enter"`.

## Memory
- Jarvis remembers the conversation across restarts (if it was less than `HISTORY_MAX_AGE_HOURS` ago).
  Say **"new conversation"** to start fresh.
- Say **"remember that..."** and he saves it for good; he may also save personal details you mention.
  Say **"forget that..."** to remove one. Facts live in `memory/facts.json`, which you can edit by hand.

## Skills
Jarvis can use tools (all free, no extra API keys):
- **Timers and alarms**: "set a 10 minute tea timer", "wake me at 7:30", "how long left?", "cancel the timer".
- **Weather** (Open-Meteo): "what's the weather?", "will it rain this week?". Set `HOME_CITY` in `config.py`.
- **Web search** (DuckDuckGo): "who won the match last night?".
- **Calendar** (read-only): "what's on today?", "am I free tomorrow afternoon?", "what's my week look like?".
  In Google Calendar open Settings, pick your calendar, scroll to *Integrate calendar* and copy the
  **Secret address in iCal format**. Add it to `.env`:
  `CALENDAR_ICS_URLS=https://calendar.google.com/calendar/ical/.../basic.ics`
  (several calendars: separate the links with spaces). iCloud `webcal://` links work as-is.
  `config.py` has a default link built in; `.env` overrides it.
- **Share prices** (Yahoo Finance): "what is Nvidia trading at?".
- **PC control**: "open Spotify", "volume up", "set the volume to 30", "mute", "pause the music", "next song", "lock the PC".
  Apps come from the Start menu or the `APPS` list in `config.py`.
- **Interrupt**: say "Hey Jarvis" while he's talking to cut him off and ask something else (`BARGE_IN` in `config.py`).
- **Shut down**: "okay, shut down", or just tell him you're done for the day.
- **Memory**: "remember that…", "forget that…".

Skills live in `skills/`, one file each, written in a provider-neutral way so another LLM
provider can use them too (`skills.openai_tools()` gives the OpenAI/Groq format).

## Raspberry Pi
Use a Pi 4 (4 GB) or Pi 5 with Raspberry Pi OS 64-bit, a USB mic and a speaker.
```
git clone https://github.com/yadgv/Jarvis.git jarvis && cd jarvis
bash deploy/install_pi.sh
```
The script installs everything, asks for your API key, lists your microphones, and can set
Jarvis to start on boot (and restart if he crashes). On a Pi, Jarvis uses the faster
`tiny.en` speech model automatically. If he doesn't hear you, set `MIC_DEVICE` in `config.py`.

## Logs and tests
- Everything Jarvis prints also goes to `jarvis.log`, with times, including how long each reply took.
- `pip install pytest` then `pytest` runs the tests (no mic or API key needed). GitHub runs them on every PR.

## Structure
```
main.py        main loop
gui.py         desktop window (python gui.py)
ui_events.py   connects the window to the voice loop
tests/         automated tests
deploy/        Raspberry Pi setup script and service
config.py      all settings
audio/         recorder, wake word, speech-to-text, text-to-speech
brain/llm.py   Claude, conversation memory and tools
brain/memory.py  saving history and facts in memory/
skills/        tools Jarvis can use (timers, weather, web search, memory)
```
