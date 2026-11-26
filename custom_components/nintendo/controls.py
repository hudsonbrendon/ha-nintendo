"""Helpers p/ editar a regra de hoje (limite/hora de dormir) sem perder o resto."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.util import dt as dt_util

from . import logic


def edited_regulations(setting: dict[str, Any], edit: Any) -> dict[str, Any]:
    """Copia o playTimerRegulations e aplica `edit(rule)` na regra que vale hoje."""
    ptr = copy.deepcopy(setting.get("playTimerRegulations") or {})
    if ptr.get("timerMode") == "EACH_DAY_OF_THE_WEEK":
        rule = ptr.setdefault("eachDayOfTheWeekRegulations", {}).setdefault(
            logic.WEEKDAYS[dt_util.now().weekday()], {}
        )
    else:
        rule = ptr.setdefault("dailyRegulations", {})
    edit(rule)
    return ptr
