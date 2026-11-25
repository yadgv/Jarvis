"""Arduino over USB: names to pins, the line protocol, reconnecting."""
import types

import pytest

import config
from skills import arduino


class FakePort:
    def __init__(self, answers):
        self.answers, self.sent, self.is_open = list(answers), [], True

    def write(self, data):
        self.sent.append(data.decode().strip())

    def readline(self):
        return (self.answers.pop(0) + "\r\n").encode() if self.answers else b""

    def reset_input_buffer(self):
        pass

    def close(self):
        self.is_open = False


@pytest.fixture
def board(monkeypatch):
    ports = []

    def make(*answers):
        port = FakePort(answers)
        ports.append(port)
        return port
    fake_serial = types.SimpleNamespace(Serial=lambda dev, baud, timeout: ports.pop(0))
    monkeypatch.setattr(arduino, "_serial", lambda: fake_serial)
    monkeypatch.setattr(arduino, "find_port", lambda: "COM5")
    monkeypatch.setattr(arduino.time, "sleep", lambda s: None)
    monkeypatch.setattr(arduino, "_port", None)
    monkeypatch.setattr(config, "ARDUINO_DEVICES", {"Desk Lamp": 7, "fan": 9, "buzzer": 8})
    monkeypatch.setattr(config, "ARDUINO_SENSORS", {"light sensor": "A0"})
    return make


def test_named_devices_become_commands(board):
    port = board("OK", "OK", "OK", "OK 512", "OK")
    assert "ON 7 -> OK" in arduino.arduino({"action": "on", "target": "desk lamp"})
    assert "PWM 9 128" in arduino.arduino({"action": "level", "target": "fan", "value": "50"})
    assert "SERVO 3 90" in arduino.arduino({"action": "servo", "target": "3", "value": "90"})
    assert "OK 512" in arduino.arduino({"action": "read", "target": "light sensor"})
    arduino.arduino({"action": "beep", "target": "buzzer"})
    assert port.sent == ["ON 7", "PWM 9 128", "SERVO 3 90", "READ A0", "TONE 8 880 200"]


def test_unknown_names_and_refusals(board):
    board("ERR unknown command FAN")
    assert "don't know 'kettle'" in arduino.arduino({"action": "on", "target": "kettle"})
    assert "refused" in arduino.arduino({"action": "command", "value": "FAN 1"})


def test_status_and_reconnect_after_unplug(board):
    first = board()             # unplugged: no answer
    board("PONG jarvis-bridge 1")
    out = arduino.arduino({"action": "status"})
    assert "connected (PONG" in out and "desk lamp".lower() in out.lower()
    assert not first.is_open


def test_no_board(monkeypatch):
    monkeypatch.setattr(arduino, "_port", None)
    monkeypatch.setattr(arduino, "find_port", lambda: None)
    assert "No Arduino found" in arduino.arduino({"action": "status"})
