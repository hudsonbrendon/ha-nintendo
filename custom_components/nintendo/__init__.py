"""Integração Nintendo: consoles, tempo de jogo e controle parental via API oficial dos apps."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NintendoClient
from .const import CONF_SESSION_TOKEN
from .coordinator import NintendoConfigEntry, NintendoCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.TIME,
]


async def async_setup_entry(hass: HomeAssistant, entry: NintendoConfigEntry) -> bool:
    lang = hass.config.language if "-" in hass.config.language else "pt-BR"
    client = NintendoClient(
        async_get_clientsession(hass),
        entry.data[CONF_SESSION_TOKEN],
        str(hass.config.time_zone),
        lang,
    )
    coordinator = NintendoCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NintendoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
