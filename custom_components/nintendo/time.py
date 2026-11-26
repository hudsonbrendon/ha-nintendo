"""Hora de dormir (alarme 16–23h) e fim da hora de dormir (05–09h)."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import logic
from .controls import edited_regulations
from .coordinator import NintendoConfigEntry
from .entity import NintendoDeviceEntity

# chave da entidade -> (campo na API, hora mínima, hora máxima)
FIELDS = {
    "hora_de_dormir": ("endingTime", 16, 23),
    "fim_hora_de_dormir": ("startingTime", 5, 9),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NintendoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coord = entry.runtime_data
    async_add_entities(
        BedtimeTime(coord, dev_id, key)
        for dev_id in coord.data["devices"]
        for key in FIELDS
    )


class BedtimeTime(NintendoDeviceEntity, TimeEntity):
    def __init__(self, coord, dev_id: str, key: str) -> None:
        super().__init__(coord, dev_id, key)
        self._field, self._min, self._max = FIELDS[key]

    @property
    def native_value(self) -> time | None:
        bed = (
            logic.regulation_today(self.dev["setting"], dt_util.now().date()).get(
                "bedtime"
            )
            or {}
        )
        t = bed.get(self._field)
        return time(t["hour"], t["minute"]) if t else None

    async def async_set_value(self, value: time) -> None:
        if not self._min <= value.hour <= self._max or (
            value.hour == self._max and value.minute
        ):
            raise ServiceValidationError(
                f"Horário precisa estar entre {self._min:02d}:00 e {self._max:02d}:00"
            )

        def edit(rule):
            bed = rule.setdefault("bedtime", {})
            bed[self._field] = {"hour": value.hour, "minute": value.minute}
            if self._field == "endingTime":
                bed["enabled"] = True

        ptr = edited_regulations(self.dev["setting"], edit)
        await self.coordinator.async_action(
            self.coordinator.client.async_update_play_timer(self.device_id, ptr)
        )
