"""Weird symbols on the whiteboard and in his voice (brain/textfix.py)."""
import requests

from brain import backup, textfix


def test_mangled_text_is_repaired():
    # Real lines from the log: UTF-8 read as Latin-1.
    bad = "Connect the servoâ\u0080\u0099s red lead to the Arduinoâ\u0080\u0099s 5â\u0080¯V pin"
    assert textfix.fix(bad) == "Connect the servo's red lead to the Arduino's 5 V pin"
    assert textfix.fix("a 220Î© resistor") == "a 220Ω resistor"
    assert textfix.fix("The wiring diagramâ\u0080\u0099s now updated") == "The wiring diagram's now updated"
    assert textfix.fix("café → done") == "café -> done"  # good text is left alone


def test_symbols_are_spoken_as_words():
    say = textfix.for_speech
    assert say("Use a 220Î© resistor") == "Use a 220 ohm resistor"
    assert say("It's -1°C outside") == "It's -1 degrees Celsius outside"
    assert say("red to 5 V, signal to a PWM pin (e.g., D9).") == "red to 5 volts, signal to a PWM pin (for example D9)."
    assert say("**Step 1:** connect `GND` → GND \U0001f50c") == "Step 1: connect GND to GND"
    assert say("See [the docs](https://x.y) now") == "See the docs now"


def test_model_streams_are_read_as_utf8():
    r = requests.Response()
    r.status_code = 200
    r.headers["Content-Type"] = "text/event-stream"
    chunk = '{"choices": [{"delta": {"content": "servo’s 220Ω"}}]}'
    r.raw = __import__("io").BytesIO(f"data: {chunk}\n\ndata: [DONE]\n\n".encode("utf-8"))
    got = list(backup._events(r))
    assert got[0]["choices"][0]["delta"]["content"] == "servo’s 220Ω"


def test_diagram_labels_are_clean():
    from skills import diagram
    assert diagram.plain("220Î© to pin 9") == "220 ohm to pin 9"
