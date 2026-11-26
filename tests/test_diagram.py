"""Diagrams are drawn from a description, the same tidy way every time."""
import re

from skills import diagram


def spec(*wires, parts=None):
    return {"title": "t", "kind": "wiring",
            "parts": parts or [{"id": "uno", "type": "arduino_uno"}, {"id": "r1", "type": "resistor"},
                               {"id": "led", "type": "led"}],
            "wires": [{"from": a, "to": b, "step": i + 1} for i, (a, b) in enumerate(wires)]}


def test_arduino_pin_names():
    assert diagram.norm_uno_pin("pin 9") == "D9"
    assert diagram.norm_uno_pin("~10") == "D10"
    assert diagram.norm_uno_pin("5v") == "5V"
    assert diagram.norm_uno_pin("3v3") == "3.3V"
    assert diagram.norm_uno_pin("a0") == "A0"
    assert diagram.norm_uno_pin("ground") == "GND"
    assert diagram.norm_uno_pin("D20") is None


def test_wire_colours():
    assert diagram.wire_colour("uno.GND", "led.-", 0) == diagram.GROUND
    assert diagram.wire_colour("uno.5V", "servo.V+", 0) == diagram.POWER
    # The LED's + through a resistor from a pin is a signal, not power.
    assert diagram.wire_colour("r1.2", "led.+", 0) in diagram.SIGNALS
    assert diagram.wire_colour("uno.D9", "r1.1", 1) != diagram.wire_colour("uno.D9", "r1.1", 2)


def test_every_wire_has_its_own_lane():
    svg, skipped = diagram.render(spec(("uno.D13", "r1.1"), ("r1.2", "led.+"), ("led.-", "uno.GND"),
                                       ("uno.D2", "led.x")))
    assert not skipped
    paths = re.findall(r'<path d="([^"]+)" fill="none" stroke="(?!#ffffff)[^"]+" stroke-width="6"', svg)
    assert len(paths) == 4
    verticals = set()
    for d in paths:
        pts = [tuple(map(float, p.split())) for p in d[2:].split(" L ")]
        xs = {x1 for (x1, y1), (x2, y2) in zip(pts, pts[1:]) if x1 == x2 and x1 > 700}
        assert not xs & verticals   # no two wires share a vertical lane
        verticals |= xs


def test_parts_get_the_pins_their_wires_use():
    svg, skipped = diagram.render(spec(("uno.D2", "dht.DATA"),
                                       parts=[{"id": "uno", "type": "arduino_uno"},
                                              {"id": "dht", "type": "generic", "label": "DHT11"}]))
    assert not skipped and ">DATA<" in svg and ">DHT11<" in svg


def test_flowchart():
    svg, skipped = diagram.render({"title": "Morning", "kind": "flowchart",
                                   "nodes": [{"id": "a", "text": "Wake up", "shape": "start"},
                                             {"id": "b", "text": "School day?", "shape": "decision"},
                                             {"id": "c", "text": "Leave", "shape": "end"}],
                                   "edges": [{"from": "a", "to": "b", "step": 1},
                                             {"from": "b", "to": "c", "label": "no", "step": 2},
                                             {"from": "a", "to": "c", "step": 3},
                                             {"from": "a", "to": "zzz", "step": 3}]})
    assert "<polygon" in svg and 'id="step-3"' in svg and ">no<" in svg
    assert skipped == ["a -> zzz"]
