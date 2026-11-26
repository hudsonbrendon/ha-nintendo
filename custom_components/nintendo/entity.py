"""Entidades base: conta e console."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import logic
from .const import DOMAIN
from .coordinator import NintendoCoordinator


class NintendoAccountEntity(CoordinatorEntity[NintendoCoordinator]):
    """Entidade da conta Nintendo."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NintendoCoordinator, key: str) -> None:
        super().__init__(coordinator)
        uid = coordinator.config_entry.unique_id
        self._attr_unique_id = f"{uid}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name=f"Conta Nintendo {coordinator.config_entry.title}",
            manufacturer="Nintendo",
            model="Conta Nintendo",
            configuration_url="https://accounts.nintendo.com/",
        )


class NintendoDeviceEntity(CoordinatorEntity[NintendoCoordinator]):
    """Entidade de um console."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: NintendoCoordinator, device_id: str, key: str
    ) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_translation_key = key
        owned = self.dev["owned"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=owned.get("label") or owned.get("device", {}).get("externalNickname"),
            manufacturer="Nintendo",
            model=logic.model(owned),
            serial_number=owned.get("device", {}).get("serialNumber"),
        )

    @property
    def dev(self) -> dict[str, Any]:
        return self.coordinator.data["devices"].get(self.device_id) or {
            "owned": {},
            "daily": {},
            "setting": {},
            "monthly": {},
        }

    @property
    def available(self) -> bool:
        return super().available and self.device_id in self.coordinator.data["devices"]
