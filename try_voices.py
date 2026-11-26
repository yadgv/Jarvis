"""Hear the offline voices (used when there's no internet) and pick one.

    python try_voices.py            every voice in OFFLINE_VOICES, one after another
    python try_voices.py fable      just one
    python try_voices.py fable george "Your custom line, sir."

Then set OFFLINE_VOICE in config.py to the one you like (or tell Jarvis
"use the fable voice offline"). The first run downloads each voice into voices/.
"""
import sys

import config
from audio import tts


def main(args):
    names = [a for a in args if a.lower() in config.OFFLINE_VOICES or "_" in a or "-" in a]
    text = next((a for a in args if a not in names), tts.SAMPLE)
    for name in names or list(config.OFFLINE_VOICES):
        print(f"\n== {name} ({config.OFFLINE_VOICES.get(name.lower(), name)})")
        print("  ", tts.preview(name, text))
    print(f"\nNow using: {config.OFFLINE_VOICE}. To change it, set OFFLINE_VOICE in config.py.")


if __name__ == "__main__":
    main(sys.argv[1:])
