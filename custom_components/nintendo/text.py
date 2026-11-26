"""PIN do controle parental e nome do console."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

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
        for e in (PinText(coord, dev_id), LabelText(coord, dev_id))
    )


class PinText(NintendoDeviceEntity, TextEntity):
    _attr_mode = TextMode.PASSWORD
    _attr_pattern = r"^\d{4,8}$"
    _attr_native_min = 4
    _attr_native_max = 8
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coord, dev_id: str) -> None:
        super().__init__(coord, dev_id, "pin")

    @property
    def native_value(self) -> str | None:
        return self.dev["setting"].get("unlockCode")

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.async_action(
            self.coordinator.client.async_update_unlock_code(self.device_id, value)
        )


class LabelText(NintendoDeviceEntity, TextEntity):
    _attr_native_max = 20
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coord, dev_id: str) -> None:
        super().__init__(coord, dev_id, "nome")

    @property
    def native_value(self) -> str | None:
        return self.dev["owned"].get("label")

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.async_action(
            self.coordinator.client.async_update_label(self.device_id, value)
        )
