import os
import re

import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Windows folders the OS sets itself, not settings for .env.
SYSTEM_VARS = {"APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramFiles",
               "ProgramFiles(x86)", "ProgramData", "ProgramW6432"}


def _vars_in_code():
    found = set()
    pattern = re.compile(r"os\.(?:getenv|environ\.get)\(\s*[\"']([A-Za-z0-9_()]+)[\"']")
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ("tests", ".git", "venv", "__pycache__")]
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    found |= set(pattern.findall(f.read()))
    return found - SYSTEM_VARS


def test_env_example_lists_every_setting():
    with open(os.path.join(ROOT, ".env.example"), encoding="utf-8") as f:
        listed = set(re.findall(r"^#?\s*([A-Z0-9_]+)=", f.read(), re.M))
    missing = _vars_in_code() - listed
    assert not missing, f"add these to .env.example: {sorted(missing)}"


def test_blank_env_lines_keep_defaults(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("JARVIS_TEST_BLANK=\nJARVIS_TEST_SET=\"abc\"\n# JARVIS_TEST_COMMENT=x\n", encoding="utf-8")
    for key in ("JARVIS_TEST_BLANK", "JARVIS_TEST_SET", "JARVIS_TEST_COMMENT"):
        monkeypatch.delenv(key, raising=False)
    config._load_env_file(str(env))
    assert "JARVIS_TEST_BLANK" not in os.environ
    assert os.environ["JARVIS_TEST_SET"] == "abc"
    assert "JARVIS_TEST_COMMENT" not in os.environ
    monkeypatch.delenv("JARVIS_TEST_SET")
