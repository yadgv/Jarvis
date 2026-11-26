"""The exact calculator with units."""
import pytest

import skills
from skills.calculator import calculate


@pytest.mark.parametrize("expr, want", [
    ("3.2 kN * 45 mm in N m", "144 N m"),
    ("2.5 kW * 3 h in kWh", "7.5 kWh"),
    ("100 km / 2 h in m/s", "13.8889 m/s"),
    ("5 ft 3 inch in cm", "160.02 cm"),
    ("12 in to cm", "30.48 cm"),
    ("1 atm in psi", "14.6959 psi"),
    ("9.81 m/s^2 * 70 kg", "686.7 N"),
    ("10 kohm * 2 mA", "20 V"),
    ("1/(2*pi*10 kHz*100 nF)", "159.155 Ω"),
    ("0.5 * 1200 kg * (25 m/s)^2 in kJ", "375 kJ"),
    ("sqrt(2)*sin(30 deg)", "0.707107"),
    ("1.5e-3 m in mm", "1.5 mm"),
    ("3 times 4 plus 2", "14"),
    ("350 kelvin to fahrenheit", "350 K = 170.33 °F"),
    ("20 °C to K", "20 °C = 293.15 K"),
])
def test_sums(expr, want):
    assert calculate({"expression": expr}) == want


@pytest.mark.parametrize("expr, says", [
    ("5 m + 3 s", "can't add m and s"),
    ("1/0", "division by zero"),
    ("__import__('os').system('x')", "only do arithmetic"),
    ("2 ** 99999", "too big"),
    ("3 kg in m", "Can't convert"),
    ("", "What should I"),
])
def test_refuses_nonsense(expr, says):
    assert says in calculate({"expression": expr})


def test_maths_words_bring_the_calculator():
    assert "calculate" in skills.pick_tools("what's 3.2 kN times 45 mm", limit=3)
