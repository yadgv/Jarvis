import pytest

import config

config.MODE = "enter"  # don't load the wake-word model
import main  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("Okay, shut down", True),
    ("shut down please", True),
    ("Jarvis, power off", True),
    ("ok you can go to sleep now", True),
    ("Goodbye Jarvis", True),
    ("don't shut down the PC", False),
    ("can I shut down", False),
    ("shut down the computer", False),
    ("okay", False),
])
def test_exit_phrases(text, expected):
    assert main.is_exit(main.normalize(text)) is expected
