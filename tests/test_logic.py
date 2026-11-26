"""Testes das regras puras com JSON real (anonimizado) da API Moon."""

import importlib.util
import json
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "logic", ROOT / "custom_components/nintendo/logic.py"
)
logic = importlib.util.module_from_spec(spec)
sys.modules["logic"] = logic
spec.loader.exec_module(logic)

FIX = json.loads((ROOT / "tests/fixtures/moon.json").read_text())
DAILY, SETTING = FIX["daily"], FIX["setting"]


def test_games_and_minutes():
    day = logic.summary_for(DAILY, date(2026, 11, 21))
    assert logic.minutes(day) == 5
    g = logic.games(day)
    assert g[0]["titulo"] == "The Legend of Zelda: Breath of the Wild"
    assert g[0]["minutos"] == 5 and g[0]["jogadores"] == ["99hud"]
    assert logic.players(day) == {"99hud": 5}
    assert logic.minutes_since(DAILY, date(2026, 11, 26), 7) == 5
    assert logic.minutes_since(DAILY, date(2026, 11, 26), 30) == 15


def test_limit_and_remaining():
    assert logic.limit_minutes(SETTING, date(2026, 11, 26)) is None
    s = json.loads(json.dumps(SETTING))
    s["playTimerRegulations"]["dailyRegulations"]["timeToPlayInOneDay"] = {
        "enabled": True,
        "limitTime": 60,
    }
    day = {"playingTime": 45}
    assert logic.remaining_minutes(s, day, date(2026, 11, 26)) == 15
    assert logic.remaining_minutes(s, day, date(2026, 11, 26), extra=30) == 45
    s["playTimerRegulations"]["timerMode"] = "EACH_DAY_OF_THE_WEEK"
    assert logic.limit_minutes(s, date(2026, 11, 26)) is None  # quinta sem limite


def test_tracker():
    t = logic.PlayTracker()

    def mk(m):
        return {
            "date": "2026-11-26",
            "players": [
                {
                    "profile": {"nickname": "a"},
                    "playedGames": [
                        {
                            "meta": {"applicationId": "X", "title": "Jogo"},
                            "playingTime": m,
                        }
                    ],
                }
            ],
        }

    t.update(mk(5), 0)
    assert not t.playing(0) and t.last_game["titulo"] == "Jogo"
    t.update(mk(5), 600)
    assert not t.playing(600)
    t.update(mk(9), 1200)
    assert t.playing(1300) and not t.playing(1200 + 21 * 60)
    assert logic.model({"device": {"platformGeneration": "P01"}}) == "Nintendo Switch 2"
