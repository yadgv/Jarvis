"""JARVIS - Phase 1: wake word -> listen -> think -> speak."""
import re

import config
from audio.recorder import calibrate, chime, open_stream, record_until_silence
from audio.stt import transcribe
from audio.tts import speak
from brain.llm import reset, think

if config.MODE == "wake":
    from audio.wakeword import wait_for_wake_word

# The whole sentence has to be one of these, so "don't shut down the PC"
# doesn't turn Jarvis off.
EXIT_PHRASES = {
    "goodbye jarvis", "bye jarvis", "goodbye",
    "shut down", "jarvis shut down", "shut down jarvis",
    "power down", "jarvis power down", "power down jarvis",
}
RESET_PHRASES = {"new conversation", "forget that", "forget everything", "start over"}


def normalize(text: str) -> str:
    text = re.sub(r"[^a-z' ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def main():
    print("JARVIS online.")
    speak("Jarvis online. At your service, sir.")

    with open_stream() as stream:
        if config.AUTO_CALIBRATE:
            calibrate(stream)

        need_wake = True
        while True:
            if need_wake:
                if config.MODE == "wake":
                    print("\n[waiting for 'Hey Jarvis'...]")
                    wait_for_wake_word(stream)
                else:
                    stream.stop()
                    input("\n[press Enter to talk]")
                    stream.start()
                chime(stream)
                print("[listening]")
                audio = record_until_silence(stream)
            else:
                print("[listening for a follow-up...]")
                audio = record_until_silence(stream, config.FOLLOWUP_SECONDS)

            # Pause the mic while we transcribe, think and speak, so stale
            # audio (and Jarvis's own voice) doesn't pile up in the buffer.
            stream.stop()

            text = transcribe(audio)
            if not text:
                if need_wake:
                    print("[heard nothing]")
                need_wake = True
                stream.start()
                continue
            print(f"You: {text}")

            said = normalize(text)
            if said in EXIT_PHRASES:
                speak("Powering down. Goodbye, sir.")
                break
            if said in RESET_PHRASES:
                reset()
                speak("Very well, sir. Fresh start.")
                need_wake = True
                stream.start()
                continue

            try:
                reply = think(text)
            except Exception as e:
                print(f"[brain error] {e}")
                reply = "I'm having trouble reaching my servers, sir."
            if reply:
                print(f"JARVIS: {reply}")
                speak(reply)

            stream.start()
            # Keep listening briefly so you can reply without the wake word.
            need_wake = config.FOLLOWUP_SECONDS <= 0


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nJARVIS offline.")
