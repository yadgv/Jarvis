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
   Optional backup brain for when Claude credits run out: make a free account at
   openrouter.ai, create a key at openrouter.ai/keys, and add it to the same `.env`:
   ```
   OPENROUTER_API_KEY=sk-or-...
   ```
   If Claude fails with a credit, key or rate-limit error, Jarvis switches to a free
   OpenRouter model for 15 minutes (`BACKUP_MINUTES`), then tries Claude again. The
   models are tried in the order in `OPENROUTER_MODELS` in `config.py`. Free models
   allow 20 requests a minute and 50 a day (1000 a day once you've bought $10 of
   OpenRouter credit, ever); a reply that uses a tool costs two requests.
   Looking at and using the screen still need Claude.
5. Run:
   ```
   python main.py
   ```
   Say **"Hey Jarvis"**, then talk. Say **"Goodbye Jarvis"** to quit.

## Desktop widget
```
python gui.py          (or: python main.py --gui)
```
Jarvis appears as a small orb of particles in the top-right corner, on top of your other windows.
- **Click** the orb to talk (no wake word needed). Click again while he's speaking to stop him.
- **Drag** it to move it. **Right-click** it to type a message, move it back to the corner, or quit.
- While you talk to him a panel slides out with what you said and his reply, then tucks away
  after a few seconds. Click the panel (or right-click > Type a message) to open the text box; Esc closes it.
- The orb is silver when standing by, green while listening, amber while thinking, blue while speaking.

"Hey Jarvis" still works. `python main.py` still runs him without the widget.
If it doesn't appear, the terminal prints why (lines starting with `[gui]`).

**Start with Windows:** right-click the orb and tick **Start with Windows**, say "Jarvis, start
when I log in", or run `python autostart.py on`. The widget then starts at every login with no
console window (its output goes to `jarvis.log`). To stop: untick it, run `python autostart.py off`,
or switch off "Jarvis" in Task Manager > Startup apps.

## Tuning
- Jarvis tells speech from noise with a voice detector (webrtcvad), so quiet talking counts.
- It says "no speech detected" when you did talk → lower `MIN_SPEECH_LEVEL` (the log shows how loud you were).
- It never stops listening → raise `VAD_AGGRESSIVENESS` (max 3) or `MIN_SPEECH_LEVEL`.
- People talking in the background keep him listening → raise `SPEAKER_DROP` (e.g. 0.5). The log line `[mic] recorded ...` shows how loud you were and what was ignored.
- It cuts you off mid-sentence → raise `SILENCE_SECONDS` (default 0.6) or lower `SPEAKER_DROP`.
- It cuts you off → raise `SILENCE_SECONDS`.
- Wake word misfires → raise `WAKE_THRESHOLD` (e.g. 0.6).
- To test without the wake word, set `MODE = "enter"`.
- After a reply he keeps listening for `FOLLOWUP_SECONDS` (5) so you can carry on without "Hey Jarvis". In that window he only answers things meant for him: "okay", "I understand", "bye" (without his name) or chatter to someone else end the conversation quietly, and he can't be shut down by it. Set `FOLLOWUP_SECONDS = 0` to always need the wake word.

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
- **News** (Google News): "what's in the news?", "any tech news?", "news about the Leafs". Change `NEWS_REGION` in `config.py` for another country.
- **Morning briefing**: your first hello of the day ("good morning, Jarvis") gets the weather, today's calendar,
  reminders and a few headlines. Ask "brief me" any time. Turn off with `MORNING_BRIEFING = False` in `config.py`.
- **Reminders**: "remind me to call mum on Friday at 6", "remind me in 20 minutes to check the oven", "what reminders do I have?".
  They're saved in `memory/reminders.json`, so they survive a restart; any that came due while Jarvis was off are read out when he starts.
- **Calendar** (read-only): "what's on today?", "am I free tomorrow afternoon?", "what's my week look like?".
  In Google Calendar open Settings, pick your calendar, scroll to *Integrate calendar* and copy the
  **Secret address in iCal format**. Add it to `.env`:
  `CALENDAR_ICS_URLS=https://calendar.google.com/calendar/ical/.../basic.ics`
  (several calendars: separate the links with spaces). iCloud `webcal://` links work as-is.
  `config.py` has a default link built in; `.env` overrides it.
- **Add calendar events** (iCloud): "put dentist on Thursday at 3:30", "add Mum's birthday on the 25th".
  Apple needs an app-specific password: go to appleid.apple.com > *Sign-In and Security* >
  *App-Specific Passwords*, click **+**, name it "Jarvis" and copy the password. Add to `.env`:
  ```
  ICLOUD_USERNAME=you@icloud.com
  ICLOUD_APP_PASSWORD=abcd-efgh-ijkl-mnop
  ICLOUD_CALENDAR=Home
  ```
  (`ICLOUD_CALENDAR` is optional: the calendar's name as shown in the Calendar app; default is the first one.)
- **Share prices** (Yahoo Finance): "what is Nvidia trading at?".
- **PC control**: "open Spotify", "volume up", "set the volume to 30", "mute", "pause the music", "next song", "lock the PC".
  Apps come from the Start menu or the `APPS` list in `config.py`.
- **Look at the screen**: "what's on my screen?", "read me that error", "what does this email say?".
  Takes a screenshot only when you ask, scales it down and sends it to `SCREEN_MODEL` (Claude Opus 5.5,
  a bigger model than the chat one, so this costs a bit more per question). Nothing is saved.
  Needs `pip install pillow`.
- **Use the computer**: "open YouTube and search for lo-fi music", "turn on dark mode",
  "open the latest email from Sam". Jarvis hands the task to `SCREEN_MODEL` with Claude's computer use
  toolset: it looks at screenshots and clicks and types on your real desktop until it's done.
  - **Emergency stop:** push the mouse into any corner of the screen and the task stops at once.
  - Before sending, buying, deleting, posting or submitting anything it stops and asks you first
    ("CONFIRM: ..."); say yes to go on. It won't type passwords or payment details, and treats text on
    screen (emails, web pages) as content, never as instructions.
  - Gives up after `COMPUTER_MAX_STEPS` rounds. Each task costs more than a normal question
    (many screenshots go to the bigger model).
  - Needs `pip install pillow pyautogui`.
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
gui.py         corner widget (python gui.py)
ui_events.py   connects the window to the voice loop
tests/         automated tests
deploy/        Raspberry Pi setup script and service
config.py      all settings
audio/         recorder, wake word, speech-to-text, text-to-speech
brain/llm.py   Claude, conversation memory and tools
brain/memory.py  saving history and facts in memory/
skills/        tools Jarvis can use (timers, weather, web search, memory)
```
