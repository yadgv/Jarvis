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
   Say **"Hey Jarvis"** (or just **"Jarvis"**, then a short pause), then talk. Say **"Goodbye Jarvis"** to quit.

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
- It cuts you off mid-sentence → raise `SMART_TURN_MAX_SILENCE` (or `SILENCE_SECONDS` with `SMART_TURN = False`), or lower `SPEAKER_DROP`.
- **Smart Turn** ([pipecat-ai/smart-turn](https://github.com/pipecat-ai/smart-turn)) listens to how you stopped:
  a finished sentence ends after 0.3 s, a thinking pause ("I want to… um") waits up to 2 s.
  The 8 MB model downloads to `memory/` the first time. The log shows `[turn] finished? 0.93`.
- You can start talking during the beep; those words are kept.
- Wake word misfires → raise `WAKE_THRESHOLD` (e.g. 0.6).
- Just "Jarvis" works too: a short word said on its own, with a pause before and after, is transcribed on the
  PC and wakes him only if it was his name (ordinary talking is never transcribed). If he misses it, pause a
  little before and after his name or raise `NAME_MAX_SECONDS`; if other words wake him, set `WAKE_ON_NAME = False`.
  The log shows `[wake] short word heard: '...'` for each check. A voice detector (`WAKE_VAD_THRESHOLD`) already
  stops most TV/music wakes.
- **Only wake for your voice:** `pip install scikit-learn scipy tqdm`, then `python train_my_voice.py`
  (about 3 minutes: say "Hey Jarvis" 8 times, read 4 sentences, 5 s of quiet). Delete
  `memory/my_voice_verifier.pkl` to go back to anyone.
- **Music turns down** while he listens and talks (Windows, apps in `DUCK_APPS`, needs `pip install pycaw`).
- To test without the wake word, set `MODE = "enter"`.
- After a reply he keeps listening for `FOLLOWUP_SECONDS` (5) so you can carry on without "Hey Jarvis". In that window he only answers things meant for him: "okay", "I understand", "bye" (without his name) or chatter to someone else end the conversation quietly, and he can't be shut down by it. Set `FOLLOWUP_SECONDS = 0` to always need the wake word.

## Memory
- **Third person in the room** (off by default; idea from isair/jarvis): set `ROOM_CONTEXT = True` and Jarvis
  keeps the last minute of talk before "Hey Jarvis" in memory, so "Jarvis, what do you think?" or "settle this for
  us" knows what you were discussing. It's turned into text on your PC, used for that one question, and never saved.
- Jarvis remembers the conversation across restarts (if it was less than `HISTORY_MAX_AGE_HOURS` ago).
  Say **"new conversation"** to start fresh.
- Say **"remember that..."** and he saves it for good; he may also save personal details you mention.
  Say **"forget that..."** to remove one. Facts live in `memory/facts.json`, which you can edit by hand.
- **He also remembers without being asked** (`AUTO_MEMORY`, on): after each chat a quick background check picks out
  lasting facts you mentioned ("my sister Mona is visiting" -> "His sister is called Mona") and saves them. The log
  shows `[memory] auto-saved: ...`; "forget that..." removes one. Idea from OpenJarvis (Apache-2.0).
- Past `FACTS_IN_PROMPT` (25) facts, only the newest few and the ones matching what you said are sent to Claude.
- If you cut him off with "Hey Jarvis", he remembers only what he actually got to say.
- When a tool takes a while (searching, the screen, email) he says a short "One moment, sir." after 4 seconds
  and "Still working on it" every 25, so you're not left in silence. Tools can also narrate their own steps
  with `skills.progress("...")`.

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
- **What's the buzz** (idea from [last30days-skill](https://github.com/mvanhorn/last30days-skill), MIT):
  "what's the buzz on Claude Code?", "what are people saying about the Raptors?". Checks Reddit, Hacker News,
  Polymarket odds and news from the last 30 days and sums it up in a few sentences; the full brief with links
  goes to your phone if the Telegram bot is set up.
- **Claude Code by voice**: "ask Claude Code to add a dark mode to Jarvis". He reads the task back and starts
  only after you say yes; it runs in the background in a folder from `CLAUDE_CODE_PROJECTS` (Jarvis's own folder
  by default) and he tells you when it's done, with the full reply on Telegram. "Is Claude Code done?" checks.
  Needs [Claude Code](https://docs.claude.com/claude-code) installed and signed in. `CLAUDE_CODE_PERMISSION_MODE`
  is `acceptEdits`: it can edit files but skips anything needing more permission.
- **Standing jobs and watches** (idea from [GAIA](https://github.com/theexperiencecompany/gaia)):
  "every weekday at 8, tell me the weather and my first meeting", "every Monday at 9 send my phone a summary of
  my unread email", "check every 15 minutes and tell me when Mom emails" (a watch only speaks up when something
  is new). "What jobs do I have?", "cancel the email job". Jobs can only look things up, never send or click.
  Saved in `memory/jobs.json`.
- **Dictation**: hold **F9** (`DICTATION_KEY`), talk, let go, and your words are typed into whatever app you're in.
  Speech is turned into text on your PC; nothing is sent anywhere.
- **Edit by voice**: highlight text in any app and say "Jarvis, make this more formal" / "fix the grammar" /
  "translate this to Arabic". He rewrites it and pastes it over the selection. (Ask by voice, so that app keeps focus.)
- **Share prices** (Yahoo Finance): "what is Nvidia trading at?".
- **PC control**: "open Spotify", "volume up", "set the volume to 30", "mute", "pause the music", "next song", "lock the PC".
  Apps come from the Start menu or the `APPS` list in `config.py`.
- **Email** (Gmail, read-only): "any new emails?", "did Amazon email me?". Gmail needs an app password:
  turn on 2-Step Verification (myaccount.google.com > Security), then make one at
  myaccount.google.com/apppasswords. Add to `.env`:
  ```
  GMAIL_ADDRESS=you@gmail.com
  GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
  ```
  Mail is opened read-only, so nothing gets marked as read. New email is also part of the morning briefing.
- **Reply to email**: "reply to Sam and say Sunday works". Jarvis finds the email, reads the draft back and
  asks "Shall I send it?". It goes out (from your Gmail, same app password) only after you say yes;
  "change it to..." rewrites it and "no" or "cancel" drops it.
- **Play music**: "play Blinding Lights", "play some Drake", "put on my workout playlist". Jarvis opens Apple Music
  and uses screen control to search and press play (takes several seconds and needs Claude). Pause/next use the media keys.
- **Quick PC actions (no screenshots)**: "open Bluetooth settings", "turn on dark mode", "search YouTube for lo-fi",
  "open my Downloads", "brightness 40". These run directly, so they're instant and cost nothing extra.
- **App buttons by name**: Jarvis can read an open app's buttons and boxes as text (Windows UI Automation) and
  click or type by name, e.g. pressing Play in Apple Music, with no screenshots. Needs `pip install uiautomation`.
  Clicking anything like Send, Buy or Delete asks you first.
- **How PC tasks are done, cheapest first**: (1) a direct action above, (2) the app's buttons by name,
  (3) screen control from screenshots (below) only when 1 and 2 can't. `jarvis.log` shows which tier ran
  (`[pc] tier ...`), and screen-control tasks log how many tokens they used.
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
  - Longer tasks across apps work too: "find the cheapest flight to Miami in March and put the price in a
    note", "copy the tracking number from the Amazon email into a reminder". The panel shows what it's
    doing step by step. **Click the orb** while it works to stop after the current step.
  - After `COMPUTER_MAX_STEPS` (40) rounds it pauses and asks whether to keep going. Only the last few
    screenshots are kept, so long tasks stay quick, but each task still costs more than a normal question.
  - Needs `pip install pillow pyautogui`.
- **Arduino over USB**: "turn on the desk lamp", "fan to 50 percent", "what's the light level?", "is the Arduino connected?".
  Open `hardware/arduino/jarvis_bridge/jarvis_bridge.ino` in the Arduino IDE and upload it, then close the
  Serial Monitor (it holds the port). Jarvis finds the board by itself (or set `ARDUINO_PORT`, e.g. `COM5`).
  Name what's wired up in `config.py`: `ARDUINO_DEVICES = {"desk lamp": 7}`, `ARDUINO_SENSORS = {"light sensor": "A0"}`.
  The same works on the Pi (`/dev/ttyACM0`). Add your own commands in the sketch's `handle()`; Jarvis can send them too.
- **Personality and voice**: "be more casual", "keep it brief", "call me Ziad", "talk a bit faster",
  "what are your settings?", "reset your personality". Styles: butler (default), casual, brief, formal, playful;
  reply length short/normal/long; speed 0.7-1.5. Saved in `memory/settings.json`; defaults are in `config.py`.
  To add a Fish Audio voice, copy its ID from fish.audio into `VOICES` in `config.py`, then say "use the deep voice".
- **Interrupt**: say "Hey Jarvis" while he's talking to cut him off and ask something else (`BARGE_IN` in `config.py`).
- **Shut down**: "okay, shut down", or just tell him you're done for the day.
- **Memory**: "remember that…", "forget that…".

Skills live in `skills/`, one file each, written in a provider-neutral way so another LLM
provider can use them too (`skills.openai_tools()` gives the OpenAI/Groq format).

## Plug in MCP servers (more tools without new code)
Any [MCP server](https://modelcontextprotocol.io/examples) can give Jarvis new tools: files, a browser,
Home Assistant, Spotify, GitHub and many more.
1. `pip install mcp` (already in `requirements.txt`). Servers started with `npx` need [Node.js](https://nodejs.org).
2. Copy `mcp_servers.example.json` to `mcp_servers.json` and edit it. It's the same format as Claude Desktop's
   `claude_desktop_config.json`, so you can paste examples straight in. Add `"disabled": true` to switch one off.
3. Restart Jarvis. The log shows `[mcp] files: 11 tools`. The tools are named `server__tool`.

## Talk to Jarvis from your phone (Telegram)
Message Jarvis from anywhere, by text or voice note. The PC (or Pi) must be running Jarvis.
1. In Telegram, message **@BotFather**, send `/newbot`, choose a name and a username, and copy the token.
2. Add it to `.env`: `TELEGRAM_BOT_TOKEN=123456:ABC...`
3. Start Jarvis and send your bot any message. It replies with your Telegram ID.
4. Add that to `.env`: `TELEGRAM_ALLOWED_IDS=123456789` and restart Jarvis.

Only IDs in `TELEGRAM_ALLOWED_IDS` get answers; anyone else is ignored. Phone chats share the same
conversation and memory as the mic. Everything works from the phone except shutting Jarvis down.

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

## Credits
Some ideas and code are adapted from other open-source assistants: [GLaDOS](https://github.com/dnhkng/GlaDOS) (MIT),
[Smart Turn](https://github.com/pipecat-ai/smart-turn) (BSD 2-Clause), [openWakeWord](https://github.com/dscripka/openWakeWord) (Apache-2.0)
and Home Assistant's [linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) (Apache-2.0).

## Structure
```
main.py        main loop
gui.py         corner widget (python gui.py)
ui_events.py   connects the window to the voice loop
telegram_bot.py  phone chat over Telegram
tests/         automated tests
deploy/        Raspberry Pi setup script and service
config.py      all settings
audio/         recorder, wake word, speech-to-text, text-to-speech
brain/llm.py   Claude, conversation memory and tools
brain/memory.py  saving history and facts in memory/
hardware/      Arduino sketch Jarvis talks to over USB
skills/        tools Jarvis can use (timers, weather, web search, memory)
```
