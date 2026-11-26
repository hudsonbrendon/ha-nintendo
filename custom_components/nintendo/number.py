"""Limite diário de jogo (0 = sem limite)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
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
    async_add_entities(DailyLimit(coord, dev_id) for dev_id in coord.data["devices"])


class DailyLimit(NintendoDeviceEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 360
    _attr_native_step = 15
    _attr_mode = NumberMode.BOX
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coord, dev_id: str) -> None:
        super().__init__(coord, dev_id, "limite_diario")

    @property
    def native_value(self) -> float:
        return logic.limit_minutes(self.dev["setting"], dt_util.now().date()) or 0

    async def async_set_native_value(self, value: float) -> None:
        minutes = int(value)

        def edit(rule):
            rule["timeToPlayInOneDay"] = {
                "enabled": minutes > 0,
                "limitTime": minutes or None,
            }

        ptr = edited_regulations(self.dev["setting"], edit)
        await self.coordinator.async_action(
            self.coordinator.client.async_update_play_timer(self.device_id, ptr)
        )
