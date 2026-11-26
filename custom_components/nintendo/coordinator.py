"""Coordinator: consoles, resumos diários, configurações e pareamento."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import logic
from .api import NintendoAuthError, NintendoClient, NintendoError
from .const import DOMAIN, LOGGER, SCAN_INTERVAL_SECONDS, SLOW_REFRESH_SECONDS

type NintendoConfigEntry = ConfigEntry[NintendoCoordinator]


class NintendoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Uma leitura a cada 2 min por conta."""

    config_entry: NintendoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: NintendoConfigEntry, client: NintendoClient
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self.trackers: dict[str, logic.PlayTracker] = {}
        self.pairing: dict[str, Any] | None = None
        self._slow: dict[str, Any] = {"me": {}, "monthly": {}}
        self._slow_at = 0.0

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._fetch()
        except NintendoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NintendoError as err:
            raise UpdateFailed(str(err)) from err

    async def _fetch(self) -> dict[str, Any]:
        now = time.time()
        owned = await self.client.async_devices()
        slow = now - self._slow_at > SLOW_REFRESH_SECONDS
        if slow:
            self._slow["me"] = {
                **await self.client.async_me(),
                "moon": await self.client.async_moon_user(),
            }
        devices: dict[str, Any] = {}
        for item in owned:
            dev_id = item["deviceId"]
            daily = await self.client.async_daily_summaries(dev_id)
            setting = await self.client.async_settings(dev_id)
            if slow:
                try:
                    self._slow["monthly"][
                        dev_id
                    ] = await self.client.async_latest_monthly(dev_id)
                except NintendoError as err:
                    LOGGER.debug("resumo mensal de %s indisponível: %s", dev_id, err)
            tracker = self.trackers.setdefault(dev_id, logic.PlayTracker())
            days = logic.summaries(daily)
            tracker.update(days[0] if days else None, now)
            if tracker.last_game is None:  # nada hoje: último dia com jogo
                tracker.last_game = next(
                    (
                        {**logic.games(d)[0], "data": d.get("date")}
                        for d in days
                        if logic.games(d)
                    ),
                    None,
                )
            devices[dev_id] = {
                "owned": item,
                "daily": daily,
                "setting": setting,
                "monthly": self._slow["monthly"].get(dev_id, {}),
            }
        if slow:
            self._slow_at = now
        if self.data and set(devices) - set(self.data["devices"]):
            # console novo (pareado aqui ou pelo app): recarrega p/ criar as entidades
            self.pairing = None
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        elif self.pairing and self.pairing.get("status") not in logic.PAIRING_DONE:
            await self._check_pairing(devices)
        return {"me": self._slow["me"], "devices": devices}

    async def _check_pairing(self, devices: dict[str, Any]) -> None:
        assert self.pairing is not None
        res = await self.client.async_check_pairing(self.pairing["deviceId"])
        self.pairing["status"] = res.get("pairingStatus", self.pairing["status"])
        if (
            self.pairing["status"] == "PAIRED"
            and self.pairing["deviceId"] not in devices
        ):
            LOGGER.info("console %s pareado, recarregando", self.pairing["deviceId"])
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)

    async def async_start_pairing(self) -> None:
        res = await self.client.async_start_pairing()
        self.pairing = {
            "deviceId": res.get("deviceId"),
            "pairingCode": res.get("pairingCode"),
            "status": "PAIRING",
            "criado_em": time.time(),
        }
        self.async_update_listeners()

    async def async_action(self, coro: Any) -> None:
        """Executa uma ação na API e atualiza já."""
        try:
            await coro
        except NintendoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NintendoError as err:
            raise HomeAssistantError(str(err)) from err
        await self.async_request_refresh()
