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
4. Set your API keys. Create a file named `.env` in the `jarvis` folder. Jarvis uses the
   cheapest brain that works, in the order in `BRAIN_ORDER` (config.py): Groq's free models
   first, then OpenRouter's free models, and Claude (paid) only as the last resort.
   Screen control and looking at the screen always use Claude.
   - **Groq (free, main brain):** sign in at console.groq.com, open **API Keys**, press
     **Create API Key** and copy it (shown once).
   - **Claude (paid, last resort):** console.anthropic.com > API Keys.
   ```
   GROQ_API_KEY=gsk_...
   ANTHROPIC_API_KEY=sk-ant-...
   ```
   Groq's free limits are per model, so when one model is busy the next in `GROQ_MODELS` answers,
   and the log shows which one did (`[brain] Groq ... answered`). Free models only get the tools
   that look relevant to what you said, to stay under their token limits.
   (It's git-ignored. Or use `setx ANTHROPIC_API_KEY "sk-ant-..."` and restart your terminal/VS Code.)
   If you run Jarvis with a different Python than the one you installed packages into,
   install them with that Python: `"path\to\python.exe" -m pip install -r requirements.txt`.
   Set your Fish Audio key (fish.audio → API Keys) for the main voice:
   ```
   setx FISH_API_KEY "your-fish-key"
   ```
   Close and reopen the terminal afterwards.
   If Fish Audio fails (no key, no internet, no credits), Jarvis falls back to the
   offline voice (see "Offline voice" below), then the Windows system voice.
   Optional second free brain: make a free account at openrouter.ai, create a key at
   openrouter.ai/keys, and add it to the same `.env`:
   ```
   OPENROUTER_API_KEY=sk-or-...
   ```
   It answers when Groq is busy, before Claude. Its models are tried in the order in `OPENROUTER_MODELS` in `config.py`. Free models
   allow 20 requests a minute and 50 a day (1000 a day once you've bought $10 of
   OpenRouter credit, ever); a reply that uses a tool costs two requests.
   Optional free local brain for easy questions ("how many ounces in a pound",
   "tell me a joke"): install Ollama from ollama.com/download, run
   `ollama pull llama3.2:3b` (about 2 GB; `qwen2.5:3b` also works), and set
   `LOCAL_MODEL = "llama3.2:3b"` in config.py. Short questions that need no tool
   go to it first. Anything harder, or anything it isn't sure of, goes to Claude,
   and if Ollama isn't running Jarvis uses Claude for 5 minutes before trying it again.
   Looking at and using the screen still need Claude.
5. Run:
   ```
   python main.py
   ```
   Say **"Hey Jarvis"** (or just **"Jarvis"**, then a short pause), then talk. Say **"Goodbye Jarvis"** to quit.

## Without internet

If the wifi is down, Jarvis notices within a second and keeps doing the basics.
The wake word, speech-to-text and the backup voice (Kokoro or Piper) already run
on the PC, so the whole loop works offline:

- **No model needed:** the time and date, timers ("set a 10 minute timer for
  pasta"), alarms ("wake me up at 7"), reminders ("remind me to call Mona in 20
  minutes"), volume ("turn it up", "volume to 30", "mute"), play/pause/next,
  opening apps ("open Spotify") and locking the PC.
- **With Ollama installed** (`ollama pull llama3.2:3b`): anything else that works
  offline, like cancelling a timer, opening a settings page, dark mode, or
  chatting, goes to that local model (`OFFLINE_MODEL` in config.py).
- Anything that needs the internet (weather, news, search, email, calendar,
  looking at the screen) gets a short "that needs the internet" instead of a long wait.

Set `OFFLINE_MODE = True` in config.py to try it without unplugging anything.

### Offline voice

One setting picks it: `OFFLINE_VOICE` in config.py, a name from `OFFLINE_VOICES`.
Hear them all first:
```
python try_voices.py          # every voice, one after another
python try_voices.py fable    # just one
```
Or by voice: "let me hear the George voice", then "use that one offline".
Kokoro voices (fable, george, lewis, daniel, michael, fenrir, heart, emma) sound the
most natural and need `pip install kokoro-onnx`. `OFFLINE_VOICE_QUALITY = "best"`
uses the full Kokoro model (~310 MB, smoothest); `"small"` is ~90 MB. Piper voices
(alan, northern) are lighter but more robotic. Each downloads into `voices/` the
first time it's used, so try them while you're online.
Start Jarvis online once first so the speech and wake word models are downloaded.

## Desktop widget
```
python gui.py          (or: python main.py --gui)
```
Jarvis appears as a small orb of particles in the top-right corner, on top of your other windows.

**Open it like an app:** run this once (with the Python you use for Jarvis):
```
python install_app.py
```
It adds a **Jarvis** shortcut with the orb icon to your Desktop and Start menu
(right-click the Start menu entry to pin it to the taskbar), and asks whether to
start Jarvis when you log in. It opens with no console window; everything goes to
`jarvis.log`. Opening it again while it's running does nothing, so two Jarvises
never fight over the mic. `python install_app.py remove` takes the shortcuts away.
- **Click** the orb to talk (no wake word needed). Click again while he's speaking to stop him.
- **Drag** it to move it (he stays where you put it next time). **Right-click** it to type a message,
  open **Settings...**, move it back to the corner, or quit.
- **Settings...** has his online and offline voice (with a Play button to hear each), speaking speed,
  personality, whether to show the text panel and the "Click here to type" box, the orb's colours,
  size and corner, the wake-word sensitivity, the chime, how long he keeps listening after a reply,
  the microphone, room mode, offline mode, the local model, turning music down while he talks, the
  Telegram phone bot, the morning briefing, Celsius or Fahrenheit, keeping the whiteboard on top, and
  starting with Windows. Save applies it straight away (the microphone from the next start) and it's
  kept in `memory/settings.json`.
- The **whiteboard** opens in front of everything (and keeps on top until you close it; untick that in Settings).
- **Animations:** the orb eases between colours and moods and glows with his voice; the text panel slides and
  fades out of the orb; while he works a small chip by the orb says what he's doing ("Opening Chrome...",
  "Moving files 3/20") with a spinner or progress bar, then a tick; during screen control a ripple shows
  where he clicks; the whiteboard fades drawings in and out, draws each step's lines and glides the view to
  the step he's on. Settings > **Reduce animations** turns the extras off and runs the orb at 30 frames a
  second (it already drops to 30 while standing by, to save CPU).
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
- **Small apps and web pages**: "build me a pomodoro timer app", "make a web page for my study schedule".
  After your yes, Claude Code builds it in a new folder in **Documents/Jarvis apps** (usually one `index.html`
  that opens by double-clicking, no installs) and Jarvis opens it when it's done. The app then counts as a
  project, so "add a dark mode to my pomodoro app" changes it later. To install Claude Code, run
  `irm https://claude.ai/install.ps1 | iex` in PowerShell, then `claude` once to sign in.
- **Standing jobs and watches** (idea from [GAIA](https://github.com/theexperiencecompany/gaia)):
  "every weekday at 8, tell me the weather and my first meeting", "every Monday at 9 send my phone a summary of
  my unread email", "check every 15 minutes and tell me when Mom emails" (a watch only speaks up when something
  is new). "What jobs do I have?", "cancel the email job". Jobs can only look things up, never send or click.
  Saved in `memory/jobs.json`.
- **Approve-later suggestions** (idea from [OpenJarvis](https://github.com/open-jarvis/OpenJarvis)):
  a job can suggest an action ("reply to Mom that Sunday works") instead of doing it. Jarvis mentions it,
  and it waits until you say "yes, do it" (or "no", or "what are you suggesting?"). Approved actions still
  go through their usual read-back. Suggestions expire after a day.
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

## Study mode

"Quiz me on my thermo notes" makes questions from that file (free models) and asks them one at a time, then
gives your score; the ones you missed are saved for "quiz me on the ones I got wrong". "Start a Pomodoro" or
"study for two hours" runs 25-minute focus blocks with 5-minute breaks, announced aloud, and if YouTube,
Instagram, TikTok, Reddit, Netflix or Twitch comes up during focus time he nudges you back to work.
"How long left?" and "stop the Pomodoro" work too.

## Smart clipboard

Copy any text, then: "explain what I copied" (code, an error message, a paragraph), "summarize what I
copied", "translate this to French", "fix the grammar in what I copied" (the fixed text goes back on your
clipboard, ready to paste), "define this" or "solve this". Copied text is treated as data, never as
instructions. Needs `pip install pyperclip` (already used by dictation).

## Several things at once

Long jobs (using the screen, carrying out a file sort, 3D parts, documents, whiteboard drawings, "what's the
buzz") run in the background. He says he's on it, and you can wake him and ask something else meanwhile.
When a job finishes he tells you at the next quiet moment. Ask "what are you working on?" to hear the list,
or "cancel that" / "cancel the screen task" / "cancel everything". Screen jobs need the mouse and keyboard,
so they take turns; the rest run side by side. Turn it off with `BACKGROUND_TASKS = False` in config.py.

## Asking before the paid AI

The free models do almost everything. When only Claude can (the free ones failed, or he needs to see or use
the screen), he asks first: "The free models couldn't manage that, sir. Shall I use Claude for it?" A yes
covers that one request (a whole screen task counts as one); "yes, always" stops the question, and so does
unticking **Ask before using Claude** in Settings. Scheduled jobs never use Claude while this is on.

## Whiteboard (diagrams he explains step by step)

Ask "show me how to wire a servo to my Arduino", "draw a circuit for an LED with
a button" or "draw a flowchart of my morning routine". A whiteboard window opens
(an Edge/Chrome app window, or your browser) with a labelled drawing, and each
step lights up its wires while he explains it. Say "next step", "go back",
"step 3" or "show it all" (or click / use the arrow keys), and ask for changes
like "use pin 6 instead" to redraw it. A big free model on Groq
(`WHITEBOARD_MODELS` in config.py) only lists the parts, pins and wires; Jarvis
draws them himself from accurate templates (a real Arduino Uno pin layout, part
cards, colour-coded wires that never share a line, a legend), so it's always
tidy. Scroll to zoom, drag to move, **Fit** to see it all. Claude only if the
free models fail. It needs the internet. The page only runs on your PC (127.0.0.1).

It also does **mind maps** ("make a mind map of photosynthesis", or "mind map my
bio notes" to draw one from a file) and **timelines** ("draw a timeline of World
War One", "put my project plan on a timeline"). Each branch or event is its own
step, so he draws and explains them one at a time.

For **maths and physics** he draws and works it through step by step: graphs of
functions ("graph y = x^2 - 4 and y = 2x + 1", with roots and crossings marked),
**free-body diagrams** ("draw the forces on a 5 kg box on a 30 degree ramp"), and
**circuit schematics** with proper symbols ("a 9 V battery, a switch and two
lamps in parallel"). The side panel lists the working, one line per step.

## 3D printable parts

Say "make me a phone stand", "a 40 mm box with a snap-on lid" or "a bracket for
my SG90 servo". A big free model writes the part as an OpenSCAD file, with every
size as a named variable at the top, saved in **Documents/Jarvis 3D**. If
[OpenSCAD](https://openscad.org) (free) is installed he also exports the **STL**
for your slicer, puts a preview picture on the whiteboard, and opens the file in
OpenSCAD. "Make it 10 mm taller" changes the last part; "undo that" bins it.

## Your files

Jarvis can work with the files in your own folders (Desktop, Documents,
Downloads, Pictures, Music, Videos, set in `FILE_FOLDERS` in config.py), and
nowhere else:

- **Make files**: "make me a shopping list", "write an Arduino sketch that blinks pin 13
  and save it", "make a spreadsheet of my marks" (CSV, which Excel opens).
- **Find and read**: "find my resume", "what PDFs did I download this week",
  "summarize my thermo notes". PDFs need `python -m pip install pypdf`.
- **Tidy up**: "sort my Downloads" (by type, or "by month"), "and bin the duplicates".
  He tells you the plan first and only does it after you say yes. "Undo that"
  puts everything back.
- **One file**: "rename that photo to arduino setup", "move it to Documents",
  "delete it". Deleting always goes to the Recycle Bin, after you confirm.

Install `send2trash` (it's in requirements.txt) for the Recycle Bin; without it
Jarvis uses PowerShell for the same thing.

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

## Safety
- **Planted instructions:** results from email, the web, the buzz search and MCP tools are scanned for prompt-injection
  tricks ("ignore your previous instructions", "send his inbox to...", chat-template tags). If found, Claude gets a
  warning to treat it as data only and to tell you it looked suspicious; the log shows `[safety] possible prompt injection`.
- **Loop guard:** the same tool with the same input more than twice in one turn, or two tools bouncing back and forth,
  gets a warning and then is blocked, so a stuck task can't burn through credits.
Both are adapted from [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (Apache-2.0).

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
