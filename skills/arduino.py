"""Talking to an Arduino over USB (works the same on Windows and the Pi).

Flash hardware/arduino/jarvis_bridge/jarvis_bridge.ino, plug the board in and
Jarvis finds it. Name what's wired to it in config.py (ARDUINO_DEVICES for
things to switch, ARDUINO_SENSORS for things to read), then say
"turn on the desk lamp" or "what's the light level?".

The protocol is one line of text each way, so it's easy to add your own
commands to the sketch:
    PING                -> PONG jarvis-bridge 1
    ON 7 / OFF 7        -> OK
    PWM 9 128           -> OK            (0-255, PWM pins only)
    SERVO 9 90          -> OK            (0-180 degrees)
    TONE 8 880 200      -> OK            (frequency Hz, milliseconds)
    READ A0 / READ 4    -> OK 512        (analog 0-1023, digital 0/1)
    anything else       -> whatever your sketch answers (ERR ... for unknown)
"""
import threading
import time

import config

BAUD = 115200
# USB chips found on Arduinos and clones: Arduino, CH340, FTDI, CP210x.
USB_VENDORS = {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4}
_lock = threading.Lock()
_port = None  # the open serial.Serial


def _serial():
    import serial  # pyserial; imported here so Jarvis runs without it
    return serial


def find_port():
    """The configured port, or the first USB serial device that looks like an Arduino."""
    if getattr(config, "ARDUINO_PORT", None):
        return config.ARDUINO_PORT
    from serial.tools import list_ports
    ports = list(list_ports.comports())
    for p in ports:
        if p.vid in USB_VENDORS or any(w in (p.description or "") for w in ("Arduino", "CH340", "USB Serial")):
            return p.device
    return None


def _open():
    global _port
    if _port is not None and _port.is_open:
        return _port
    device = find_port()
    if not device:
        raise ConnectionError("No Arduino found. Plug it in over USB (and close the Arduino IDE's Serial "
                              "Monitor, which holds the port), or set ARDUINO_PORT in config.py.")
    port = _serial().Serial(device, getattr(config, "ARDUINO_BAUD", BAUD), timeout=2)
    time.sleep(2)  # opening the port resets most boards; give it time to boot
    port.reset_input_buffer()
    _port = port
    print(f"[arduino] connected on {device}")
    return port


def _close():
    global _port
    try:
        if _port is not None:
            _port.close()
    except Exception:
        pass
    _port = None


def send(line: str) -> str:
    """Send one command line and return the board's one-line answer."""
    with _lock:
        for attempt in (1, 2):
            try:
                port = _open()
                port.write((line.strip() + "\n").encode("ascii", "replace"))
                answer = port.readline().decode("ascii", "replace").strip()
                if not answer:
                    raise TimeoutError("the Arduino didn't answer")
                return answer
            except ConnectionError:
                raise
            except Exception:
                _close()  # unplugged or reset: reconnect once
                if attempt == 2:
                    raise


def _pin(name, table):
    """A pin from a name in config ("desk lamp" -> 7) or a pin given directly ("7", "A0")."""
    devices = {k.lower(): v for k, v in (getattr(config, table, {}) or {}).items()}
    key = str(name or "").strip().lower()
    if key in devices:
        return str(devices[key])
    if key.isdigit() or (key[:1] == "a" and key[1:].isdigit()):
        return key.upper()
    return None


def arduino(a):
    action = (a.get("action") or "status").lower()
    target = a.get("target") or ""
    value = a.get("value")
    try:
        if action == "status":
            answer = send("PING")
            names = ", ".join(list(getattr(config, "ARDUINO_DEVICES", {}) or {}) +
                              list(getattr(config, "ARDUINO_SENSORS", {}) or {}))
            return f"Arduino connected ({answer}). Named things: {names or 'none yet (see config.py)'}."
        if action == "command":
            answer = send(str(value or target))
            return f"The Arduino refused: {answer}" if answer.startswith("ERR") else f"Arduino answered: {answer}"
        table = "ARDUINO_SENSORS" if action == "read" else "ARDUINO_DEVICES"
        pin = _pin(target, table) or _pin(target, "ARDUINO_DEVICES" if action == "read" else "ARDUINO_SENSORS")
        if pin is None:
            known = ", ".join(getattr(config, table, {}) or {}) or "none"
            return f"I don't know '{target}'. Named in config.py: {known}. A pin number also works."
        if action in ("on", "off"):
            line = f"{action.upper()} {pin}"
        elif action == "level":
            line = f"PWM {pin} {max(0, min(255, round(float(value) * 255 / 100)))}"
        elif action == "servo":
            line = f"SERVO {pin} {max(0, min(180, int(float(value))))}"
        elif action == "beep":
            line = f"TONE {pin} {int(float(value or 880))} 200"
        elif action == "read":
            line = f"READ {pin}"
        else:
            return f"Unknown action {action}."
        answer = send(line)
        return f"{line} -> {answer}" if not answer.startswith("ERR") else f"The Arduino refused: {answer}"
    except ConnectionError as e:
        return str(e)
    except ImportError:
        return "pyserial isn't installed. Run: pip install pyserial"
    except Exception as e:
        return f"Couldn't talk to the Arduino: {e}"


SKILLS = [
    {
        "name": "arduino",
        "description": (
            "Control things wired to his Arduino over USB. actions: status (is it connected, what's named), "
            "on/off (a device), level (brightness/speed 0-100 on a PWM pin), servo (angle 0-180), "
            "beep (value = frequency), read (a sensor: analog 0-1023 or digital 0/1), "
            "command (send value as a raw line for commands he added to the sketch himself). "
            "target is a name from config.py (e.g. 'desk lamp', 'light sensor') or a pin like 7 or A0."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "enum": ["status", "on", "off", "level", "servo", "beep", "read", "command"]},
                "target": {"type": "string", "description": "Device or sensor name, or pin"},
                "value": {"type": "string", "description": "Level 0-100, angle, frequency or raw command"},
            },
            "required": ["action"],
        },
        "run": arduino,
    },
]
