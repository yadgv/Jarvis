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
4. Set your API key (from console.anthropic.com):
   ```
   setx ANTHROPIC_API_KEY "sk-ant-..."
   ```
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
- It never stops listening → raise `SILENCE_THRESHOLD` in `config.py`.
- It cuts you off → lower `SILENCE_THRESHOLD` or raise `SILENCE_SECONDS`.
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
