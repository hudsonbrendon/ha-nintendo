"""Nível de restrição e modo do timer."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controls import edited_regulations
from .coordinator import NintendoConfigEntry
from .entity import NintendoDeviceEntity

LEVELS = ["none", "children", "young_teens", "older_teens", "custom"]
MODES = ["daily", "each_day_of_the_week"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NintendoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coord = entry.runtime_data
    async_add_entities(
        e
        for dev_id in coord.data["devices"]
        for e in (RestrictionSelect(coord, dev_id), TimerModeSelect(coord, dev_id))
    )


class RestrictionSelect(NintendoDeviceEntity, SelectEntity):
    _attr_options = LEVELS

    def __init__(self, coord, dev_id: str) -> None:
        super().__init__(coord, dev_id, "nivel_restricao")

    @property
    def current_option(self) -> str | None:
        return (
            self.dev["setting"].get("functionalRestrictionLevel") or ""
        ).lower() or None

    async def async_select_option(self, option: str) -> None:
        # ponytail: "custom" só reaplica o customSettings atual; editar regra a regra fica no app oficial.
        await self.coordinator.async_action(
            self.coordinator.client.async_update_restriction_level(
                self.device_id, self.dev["setting"], option.upper()
            )
        )


class TimerModeSelect(NintendoDeviceEntity, SelectEntity):
    _attr_options = MODES

    def __init__(self, coord, dev_id: str) -> None:
        super().__init__(coord, dev_id, "modo_timer")

    @property
    def current_option(self) -> str | None:
        return (
            (self.dev["setting"].get("playTimerRegulations") or {}).get("timerMode")
            or ""
        ).lower() or None

    async def async_select_option(self, option: str) -> None:
        ptr = edited_regulations(self.dev["setting"], lambda rule: None)
        ptr["timerMode"] = option.upper()
        await self.coordinator.async_action(
            self.coordinator.client.async_update_play_timer(self.device_id, ptr)
        )
