"""With no internet Jarvis still does the basics (brain/offline.py)."""
from datetime import datetime

import socket
import time

import pytest
import requests

import config
import skills
from brain import network, offline
from tests.test_brain import end, llm, use_plan  # noqa: F401


@pytest.fixture
def no_wifi(monkeypatch):
    monkeypatch.setattr(network, "_check", lambda: False)
    monkeypatch.setattr(network, "_state", {"online": None, "until": 0.0})
    monkeypatch.setattr(offline, "_model_off_until", 0.0)


@pytest.fixture
def ran(monkeypatch):
    calls = []

    def run(name, args):
        calls.append((name, args))
        return f"{name} done."
    monkeypatch.setattr(skills, "run", run)
    return calls


def cmd(text):
    return offline._command(offline._clean(text))


def test_simple_commands_are_understood():
    assert cmd("Jarvis, what time is it?")[0] == "say"
    assert cmd("what's the date today")[0] == "say"
    assert cmd("set a timer for 5 minutes") == ("set_timer", {"seconds": 300})
    assert cmd("set a 10 minute timer for pasta") == ("set_timer", {"seconds": 600, "label": "pasta"})
    assert cmd("timer for an hour and a half") == ("set_timer", {"seconds": 5400})
    assert cmd("start a timer for half an hour") == ("set_timer", {"seconds": 1800})
    assert cmd("set an alarm for 6:45 am") == ("set_alarm", {"time": "06:45"})
    assert cmd("wake me up at 7 pm") == ("set_alarm", {"time": "19:00"})
    assert cmd("remind me to call mona in 20 minutes") == (
        "set_reminder", {"text": "call mona", "in_minutes": 20.0})
    assert cmd("remind me in 2 hours to take the bins out") == (
        "set_reminder", {"text": "take the bins out", "in_minutes": 120.0})
    assert cmd("turn it up") == ("set_volume", {"action": "up"})
    assert cmd("volume down please") == ("set_volume", {"action": "down"})
    assert cmd("set the volume to 30") == ("set_volume", {"action": "set", "level": 30})
    assert cmd("mute") == ("set_volume", {"action": "mute"})
    assert cmd("pause the music") == ("media", {"action": "play_pause"})
    assert cmd("next song") == ("media", {"action": "next"})
    assert cmd("open spotify") == ("open_app", {"name": "spotify"})
    assert cmd("can you open the calculator app") == ("open_app", {"name": "calculator"})
    assert cmd("lock the computer") == ("lock_screen", {})
    assert cmd("Open up YouTube for me.") == ("open_app", {"name": "youtube"})  # open_app opens the site
    assert cmd("max volume") == ("set_volume", {"action": "set", "level": 100})
    assert cmd("volume to max") == ("set_volume", {"action": "set", "level": 100})
    assert cmd("half volume") == ("set_volume", {"action": "set", "level": 50})


def test_other_things_are_not_guessed():
    for text in ("what's the weather", "open google.com", "cancel the pasta timer",
                 "tell me a joke", "remind me about it", "set a timer"):
        assert cmd(text) is None, text


def test_reminder_at_a_time():
    name, args = cmd("remind me to stretch at 11:59 pm")
    assert name == "set_reminder" and args["text"] == "stretch"
    assert args["when"].endswith("23:59")
    assert datetime.fromisoformat(args["when"]) > datetime.now()


def test_offline_command_runs_without_any_model(llm, no_wifi, ran, monkeypatch):
    use_plan(llm, monkeypatch, lambda m: pytest.fail("Claude was asked while offline"))
    monkeypatch.setattr(llm.backup, "stream_round", lambda *a, **k: pytest.fail("a model was asked"))
    assert list(llm.think_stream("set a timer for 5 minutes")) == ["set_timer done."]
    assert ran == [("set_timer", {"seconds": 300})]
    assert "set_timer" in llm._history[-1]["content"]


def test_time_offline(llm, no_wifi, monkeypatch):
    reply = list(llm.think_stream("what time is it"))
    assert reply[0].startswith("It's ") and reply[0].endswith("sir.")


def test_other_questions_go_to_the_local_model_with_offline_tools(llm, no_wifi, monkeypatch):
    seen = []

    def stream_round(messages, exclude=(), target=None):
        seen.append((target, set(exclude)))
        yield "text", "Cancelled your pasta timer, sir."
        yield "done", ("Cancelled your pasta timer, sir.", [], target["model"])
    monkeypatch.setattr(llm.backup, "stream_round", stream_round)
    use_plan(llm, monkeypatch, lambda m: pytest.fail("Claude was asked while offline"))
    assert list(llm.think_stream("cancel the pasta timer")) == ["Cancelled your pasta timer, sir."]
    target, excluded = seen[0]
    assert target["model"] == config.OFFLINE_MODEL and "localhost" in target["url"]
    assert "get_weather" in excluded and "use_computer" in excluded
    assert "cancel_timer" not in excluded


def test_no_local_model_says_what_still_works(llm, no_wifi, monkeypatch):
    def refused(*a, **k):
        raise requests.ConnectionError("Ollama isn't running")
        yield
    monkeypatch.setattr(llm.backup, "stream_round", refused)
    assert list(llm.think_stream("tell me a joke")) == [offline.BASICS]
    # Not retried every turn.
    assert not offline.model_ready()


def test_overheard_chatter_offline_is_ignored(llm, no_wifi, monkeypatch):
    monkeypatch.setattr(offline, "_model_off_until", 1e18)
    assert list(llm.think_stream("pause the music", followup=True)) == []
    assert llm.last_ignored and not llm._history


def test_wifi_drops_mid_request(llm, monkeypatch, ran):
    def plan(m):
        raise requests.ConnectionError("Failed to establish a new connection: Network is unreachable")
    use_plan(llm, monkeypatch, plan)
    assert list(llm.think_stream("turn the volume up")) == ["set_volume done."]
    assert not network.online()


def test_server_errors_are_not_mistaken_for_offline():
    assert network.is_network_error(requests.ConnectionError("x"))
    assert network.is_network_error(type("APIConnectionError", (Exception,), {})("Connection error."))
    assert not network.is_network_error(RuntimeError("Groq error 429: rate limit"))


def test_online_only_tools_say_so_offline(no_wifi):
    assert "internet is down" in skills.run("get_weather", {})


def test_offline_mode_setting(monkeypatch):
    monkeypatch.setattr(config, "OFFLINE_MODE", True)
    assert not network.online()


def test_check_is_remembered(monkeypatch):
    checks = []
    monkeypatch.setattr(network, "_check", lambda: checks.append(1) or True)
    assert network.online() and network.online()
    assert len(checks) == 1


def test_internet_questions_are_spotted():
    for text in ("what's the weather like", "Jarvis, is it going to rain tomorrow?",
                 "what's in the news", "search for arduino nano pinout", "check my email",
                 "what's on my calendar today", "how much is bitcoin", "who won the leafs game",
                 "look at my screen", "draw me how to wire an LED to my arduino"):
        assert offline.needs_internet(text), text
    for text in ("what time is it", "remind me to check the weather", "set a timer",
                 "tell me a joke", "open spotify", "cancel the pasta timer", ""):
        assert not offline.needs_internet(text), text


def test_internet_question_offline_is_answered_at_once(llm, no_wifi, monkeypatch):
    def slow_model(*a, **k):
        time.sleep(5)
        pytest.fail("the local model was asked")
        yield
    monkeypatch.setattr(llm.backup, "stream_round", slow_model)
    use_plan(llm, monkeypatch, lambda m: pytest.fail("Claude was asked while offline"))
    t0 = time.perf_counter()
    assert list(llm.think_stream("what's the weather like today?")) == [offline.NEEDS_INTERNET]
    assert time.perf_counter() - t0 < 0.5


def test_offline_check_is_quick_with_no_internet(monkeypatch):
    def hangs(host, timeout):
        time.sleep(0.5)
        raise socket.timeout("timed out")
    monkeypatch.setattr(socket, "create_connection", hangs)
    monkeypatch.setattr(network, "TIMEOUT", 0.6)
    t0 = time.perf_counter()
    assert network._reach_any() is False
    assert time.perf_counter() - t0 < 1.0  # all hosts at once, not one after another


def test_local_model_is_not_waited_on_for_a_minute(monkeypatch):
    seen = {}

    def post(url, **k):
        seen.update(k)
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(requests, "post", post)
    from brain import backup
    with pytest.raises(requests.ConnectionError):
        list(backup.stream_round([{"role": "user", "content": "hi"}], target=offline.target()))
    assert seen["timeout"][0] <= 2 and seen["timeout"][1] <= 30
