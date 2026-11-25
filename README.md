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

## Tuning
- Jarvis tells speech from noise with a voice detector (webrtcvad), so quiet talking counts.
- It says "no speech detected" when you did talk → lower `MIN_SPEECH_LEVEL` (the log shows how loud you were).
- It never stops listening → raise `VAD_AGGRESSIVENESS` (max 3) or `MIN_SPEECH_LEVEL`.
- It cuts you off → raise `SILENCE_SECONDS`.
- Wake word misfires → raise `WAKE_THRESHOLD` (e.g. 0.6).
- To test without the wake word, set `MODE = "enter"`.

## Raspberry Pi port (later)
```
sudo apt install python3-venv portaudio19-dev espeak-ng
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
```
Then in `config.py`: `WHISPER_MODEL = "tiny.en"`, and set `MIC_DEVICE` to your USB mic
(find its index with `python -c "import sounddevice; print(sounddevice.query_devices())"`).
Use a Pi 4 (4 GB) or Pi 5 with a USB mic and a speaker.

## Structure
```
main.py        main loop
config.py      all settings
audio/         recorder, wake word, speech-to-text, text-to-speech
brain/llm.py   Claude + conversation memory (tools go here in Phase 2)
```
