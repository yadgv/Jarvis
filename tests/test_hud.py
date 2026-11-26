"""The whiteboard's holographic recolouring."""
import re

from skills import diagram, hud, visuals


def _colours(svg, tag, attr):
    return re.findall(rf'<{tag}\b[^>]*\b{attr}="(#[0-9a-fA-F]+)"', svg)


def test_paper_background_goes_and_text_turns_light():
    svg, _ = diagram.render({"title": "Morning", "kind": "flowchart",
                             "nodes": [{"id": "a", "text": "Wake up", "shape": "start"},
                                       {"id": "b", "text": "School day?", "shape": "decision"}],
                             "edges": [{"from": "a", "to": "b", "step": 1}]})
    out = hud.theme(svg)
    assert 'height="100%" fill="#ffffff"' not in out
    for colour in _colours(out, "text", "fill"):
        assert hud._lum(hud._rgb(colour)) > 0.45          # readable on the dark board
    for colour in _colours(out, "rect", "fill") + _colours(out, "polygon", "fill"):
        assert hud._lum(hud._rgb(colour)) < 0.3           # dark glass cards


def test_pale_tints_keep_their_hue():
    svg, _ = visuals.render({"kind": "mindmap", "title": "t", "center": "c",
                             "branches": [{"text": "Inputs", "children": ["a"]}]})
    out = hud.theme(svg)
    assert all(hud._lum(hud._rgb(c)) < 0.3 for c in _colours(out, "rect", "fill"))


def test_wire_halo_goes_dark_and_signals_brighten():
    svg = '<path d="M 0 0" stroke="#ffffff"/><path d="M 0 0" stroke="#1c7ed6"/><text fill="#1d2433">x</text>'
    out = hud.theme(svg)
    assert f'stroke="{hud.BG}"' in out and 'stroke="#3fa4ff"' in out and f'fill="{hud.TEXT_HI}"' in out


def test_empty():
    assert hud.theme("") == ""
