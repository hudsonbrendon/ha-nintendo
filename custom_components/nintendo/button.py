"""Tempo extra hoje e gerar código de registro de console."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NintendoConfigEntry
from .entity import NintendoAccountEntity, NintendoDeviceEntity

# chave -> (status da API, minutos)
EXTRA = {
    "tempo_extra_15": ("TO_ADDED", 15),
    "tempo_extra_30": ("TO_ADDED", 30),
    "tempo_extra_60": ("TO_ADDED", 60),
    "tempo_ilimitado_hoje": ("TO_INFINITY", None),
    "cancelar_tempo_extra": ("TO_CANCELED", None),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NintendoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coord = entry.runtime_data
    entities: list[ButtonEntity] = [
        ExtraTimeButton(coord, dev_id, key)
        for dev_id in coord.data["devices"]
        for key in EXTRA
    ]
    entities.append(PairingButton(coord))
    async_add_entities(entities)


class ExtraTimeButton(NintendoDeviceEntity, ButtonEntity):
    def __init__(self, coord, dev_id: str, key: str) -> None:
        super().__init__(coord, dev_id, key)
        self._status, self._minutes = EXTRA[key]

    async def async_press(self) -> None:
        await self.coordinator.async_action(
            self.coordinator.client.async_extra_time(
                self.device_id, self._status, self._minutes
            )
        )


class PairingButton(NintendoAccountEntity, ButtonEntity):
    """Gera o código de 6 dígitos p/ registrar um console (ex.: Switch 2)."""

    def __init__(self, coord) -> None:
        super().__init__(coord, "gerar_codigo_registro")

    async def async_press(self) -> None:
        await self.coordinator.async_action(self.coordinator.async_start_pairing())
