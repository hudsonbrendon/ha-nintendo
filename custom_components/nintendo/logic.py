"""Regras puras sobre os JSONs da API Moon (sem Home Assistant, testáveis)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

MODELS = {"P00": "Nintendo Switch", "P01": "Nintendo Switch 2"}
WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
PAIRING_DONE = (
    "PAIRED",
    "EXPIRED",
)  # outros status (PENDING, PAIRING) = aguardando o console
RESTRICTION_LEVELS = ["NONE", "CHILDREN", "YOUNG_TEENS", "OLDER_TEENS", "CUSTOM"]
# ponytail: "jogando" = tempo do dia subiu nos últimos 20 min; o console só manda
# resumo de tempos em tempos, então liga/desliga com atraso. Sem presença real na nuvem.
PLAYING_WINDOW_S = 20 * 60


def model(device: dict[str, Any]) -> str:
    return MODELS.get(
        device.get("device", {}).get("platformGeneration", ""), "Nintendo Switch"
    )


def summaries(daily: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        daily.get("dailySummaries", []), key=lambda d: d.get("date", ""), reverse=True
    )


def summary_for(daily: dict[str, Any], day: date) -> dict[str, Any] | None:
    iso = day.isoformat()
    return next((d for d in summaries(daily) if d.get("date") == iso), None)


def minutes(summary: dict[str, Any] | None) -> int:
    return int((summary or {}).get("playingTime") or 0)


def minutes_since(daily: dict[str, Any], today: date, days: int) -> int:
    """Soma do tempo de jogo dos últimos `days` dias, hoje incluso."""
    first = (today - timedelta(days=days - 1)).isoformat()
    return sum(
        minutes(d)
        for d in summaries(daily)
        if first <= d.get("date", "") <= today.isoformat()
    )


def games(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Jogos do dia somando todos os jogadores, mais jogado primeiro."""
    out: dict[str, dict[str, Any]] = {}
    for player in (summary or {}).get("players", []):
        nick = player.get("profile", {}).get("nickname")
        for game in player.get("playedGames", []):
            meta = game.get("meta", {})
            app = meta.get("applicationId")
            if not app:
                continue
            item = out.setdefault(
                app,
                {
                    "id": app,
                    "titulo": meta.get("title"),
                    "minutos": 0,
                    "imagem": (meta.get("imageUri") or {}).get("large"),
                    "loja": meta.get("shopUri"),
                    "jogadores": [],
                },
            )
            item["minutos"] += int(game.get("playingTime") or 0)
            if nick and nick not in item["jogadores"]:
                item["jogadores"].append(nick)
    return sorted(out.values(), key=lambda g: g["minutos"], reverse=True)


def players(summary: dict[str, Any] | None) -> dict[str, int]:
    return {
        p.get("profile", {}).get("nickname", "?"): int(p.get("playingTime") or 0)
        for p in (summary or {}).get("players", [])
    }


def regulation_today(setting: dict[str, Any], today: date) -> dict[str, Any]:
    """Regra (limite + hora de dormir) que vale hoje, respeitando o modo por dia da semana."""
    ptr = setting.get("playTimerRegulations") or {}
    if ptr.get("timerMode") == "EACH_DAY_OF_THE_WEEK":
        return (ptr.get("eachDayOfTheWeekRegulations") or {}).get(
            WEEKDAYS[today.weekday()], {}
        )
    return ptr.get("dailyRegulations") or {}


def limit_minutes(setting: dict[str, Any], today: date) -> int | None:
    rule = regulation_today(setting, today).get("timeToPlayInOneDay") or {}
    return rule.get("limitTime") if rule.get("enabled") else None


def remaining_minutes(
    setting: dict[str, Any],
    today_summary: dict[str, Any] | None,
    today: date,
    extra: int = 0,
) -> int | None:
    limit = limit_minutes(setting, today)
    if limit is None:
        return None
    return max(0, limit + extra - minutes(today_summary))


class PlayTracker:
    """Detecta "jogando agora" e o último jogo pelo crescimento entre leituras."""

    def __init__(self) -> None:
        self._last: dict[str, int] = {}
        self._day: str | None = None
        self.changed_at: float | None = None
        self.last_game: dict[str, Any] | None = None

    def update(self, summary: dict[str, Any] | None, now: float) -> None:
        if not summary:
            return
        day = summary.get("date")
        current = {g["id"]: g["minutos"] for g in games(summary)}
        if day != self._day:
            self._day, self._last = day, {}
        grown = [g for g in games(summary) if g["minutos"] > self._last.get(g["id"], 0)]
        if grown and self._last:
            self.changed_at = now
            self.last_game = max(
                grown, key=lambda g: g["minutos"] - self._last.get(g["id"], 0)
            )
        elif self.last_game is None and current:
            self.last_game = games(summary)[0]
        self._last = current

    def playing(self, now: float) -> bool:
        return self.changed_at is not None and now - self.changed_at < PLAYING_WINDOW_S
