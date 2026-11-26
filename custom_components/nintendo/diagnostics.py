"""Diagnóstico com dados sensíveis mascarados."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_SESSION_TOKEN
from .coordinator import NintendoConfigEntry

REDACT = {
    CONF_SESSION_TOKEN,
    "unlockCode",
    "synchronizedUnlockCode",
    "serialNumber",
    "birthday",
    "email",
    "screenName",
    "id",
    "nintendoAccountId",
    "imageUri",
    "playerId",
    "pairingCode",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NintendoConfigEntry
) -> dict[str, Any]:
    coord = entry.runtime_data
    return async_redact_data(
        {"entry": dict(entry.data), "data": coord.data, "pairing": coord.pairing},
        REDACT,
    )
