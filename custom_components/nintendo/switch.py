"""Suspender software no limite e ligar/desligar hora de dormir."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import logic
from .controls import edited_regulations
from .coordinator import NintendoConfigEntry
from .entity import NintendoDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NintendoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coord = entry.runtime_data
    async_add_entities(
        e
        for dev_id in coord.data["devices"]
        for e in (SuspendSwitch(coord, dev_id), BedtimeSwitch(coord, dev_id))
    )


class SuspendSwitch(NintendoDeviceEntity, SwitchEntity):
    """Ligado = suspende o jogo ao estourar o limite; desligado = só alarme."""

    def __init__(self, coord, dev_id: str) -> None:
        super().__init__(coord, dev_id, "suspender_software")

    @property
    def is_on(self) -> bool:
        return (self.dev["setting"].get("playTimerRegulations") or {}).get(
            "restrictionMode"
        ) == "FORCED_TERMINATION"

    async def _set(self, on: bool) -> None:
        ptr = edited_regulations(self.dev["setting"], lambda rule: None)
        ptr["restrictionMode"] = "FORCED_TERMINATION" if on else "ALARM"
        await self.coordinator.async_action(
            self.coordinator.client.async_update_play_timer(self.device_id, ptr)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class BedtimeSwitch(NintendoDeviceEntity, SwitchEntity):
    def __init__(self, coord, dev_id: str) -> None:
        super().__init__(coord, dev_id, "hora_de_dormir_ativa")

    @property
    def is_on(self) -> bool:
        return bool(
            (
                logic.regulation_today(self.dev["setting"], dt_util.now().date()).get(
                    "bedtime"
                )
                or {}
            ).get("enabled")
        )

    async def _set(self, on: bool) -> None:
        def edit(rule):
            bed = rule.setdefault("bedtime", {})
            bed["enabled"] = on
            if on and not bed.get("endingTime"):
                bed["endingTime"] = {"hour": 22, "minute": 0}

        ptr = edited_regulations(self.dev["setting"], edit)
        await self.coordinator.async_action(
            self.coordinator.client.async_update_play_timer(self.device_id, ptr)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
