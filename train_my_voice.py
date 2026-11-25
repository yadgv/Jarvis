"""Teach "Hey Jarvis" your voice, so he ignores other people (and the TV)
saying it. Takes about 3 minutes:

    python train_my_voice.py

Needs: pip install scikit-learn scipy tqdm

It records you saying "Hey Jarvis" a few times, then some ordinary talking
and room noise, and trains openWakeWord's "custom verifier" on them
(github.com/dscripka/openWakeWord, docs/custom_verifier_models.md, Apache-2.0).
The result is memory/my_voice_verifier.pkl; Jarvis loads it at startup.
Delete that file to go back to waking for anyone. Run again to retrain
(for example after moving the mic or to a new room)."""
import os
import sys
import wave

import numpy as np
import sounddevice as sd

import config

POSITIVES = 8          # "Hey Jarvis" clips (openWakeWord suggests at least 3)
NEGATIVE_SECONDS = 6   # length of each ordinary-talking clip
SENTENCES = [
    "What's the weather like in Toronto tomorrow?",
    "I think I'll make pasta for dinner tonight.",
    "Can you send the file to my brother when you get a chance?",
    "Hey, how's it going? Did you watch the game last night?",
]
CLIP_DIR = os.path.join(config.MEMORY_DIR, "voice_clips")


def record(seconds: float) -> np.ndarray:
    audio = sd.rec(int(seconds * config.SAMPLE_RATE), samplerate=config.SAMPLE_RATE,
                   channels=1, dtype="int16", device=config.MIC_DEVICE)
    sd.wait()
    return audio[:, 0]


def save(name: str, audio: np.ndarray) -> str:
    path = os.path.join(CLIP_DIR, name)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(config.SAMPLE_RATE)
        f.writeframes(audio.tobytes())
    return path


def main():
    try:
        import sklearn  # noqa: F401
        import scipy  # noqa: F401
        import tqdm  # noqa: F401
    except ImportError:
        print(f'First install the trainer: "{sys.executable}" -m pip install scikit-learn scipy tqdm')
        return
    os.makedirs(CLIP_DIR, exist_ok=True)
    positives, negatives = [], []

    print(f"\nPart 1 of 3: say \"Hey Jarvis\" {POSITIVES} times, the way you normally would,"
          "\nfrom where you usually sit. Each recording is 2 seconds.")
    for i in range(POSITIVES):
        input(f"  [{i + 1}/{POSITIVES}] press Enter, then say \"Hey Jarvis\"...")
        positives.append(save(f"positive_{i}.wav", record(2.0)))

    print(f"\nPart 2 of 3: read each sentence aloud ({NEGATIVE_SECONDS} seconds each).")
    for i, sentence in enumerate(SENTENCES):
        input(f"  [{i + 1}/{len(SENTENCES)}] press Enter, then say: {sentence}")
        negatives.append(save(f"negative_{i}.wav", record(NEGATIVE_SECONDS)))

    print("\nPart 3 of 3: stay quiet for 5 seconds (or leave the TV/music on as it usually is).")
    input("  press Enter to start...")
    negatives.append(save("negative_room.wav", record(5.0)))

    print("\nTraining...")
    import openwakeword
    from openwakeword.model import Model
    def opts():  # fresh each time: openWakeWord rewrites the model list in place
        return {"wakeword_models": [config.WAKE_WORD_MODEL], "inference_framework": "onnx"}
    name = next(iter(Model(**opts()).models))  # "hey_jarvis"
    try:
        openwakeword.train_custom_verifier(
            positive_reference_clips=positives,
            negative_reference_clips=negatives,
            output_path=config.WAKE_VERIFIER,
            model_name=name,
            **opts(),
        )
    except ValueError as e:
        # Usually: none of the "Hey Jarvis" clips scored as the wake word.
        print(f"Training failed: {e}\nTry again a little closer to the mic.")
        return
    print(f"\nDone: {config.WAKE_VERIFIER}\nRestart Jarvis. He'll now only wake for your voice."
          "\nIf he stops hearing you, run this again (closer to how you normally talk) or delete that file.")


if __name__ == "__main__":
    main()
