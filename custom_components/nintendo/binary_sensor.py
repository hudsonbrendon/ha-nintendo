"""Jogando agora (inferido pelo crescimento do tempo de jogo)."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    async_add_entities(PlayingSensor(coord, dev_id) for dev_id in coord.data["devices"])


class PlayingSensor(NintendoDeviceEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coord, dev_id: str) -> None:
        super().__init__(coord, dev_id, "jogando")

    @property
    def is_on(self) -> bool:
        tracker = self.coordinator.trackers.get(self.device_id)
        return bool(tracker and tracker.playing(time.time()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tracker = self.coordinator.trackers.get(self.device_id)
        game = (tracker.last_game or {}) if tracker else {}
        return {"jogo": game.get("titulo"), "imagem": game.get("imagem")}
