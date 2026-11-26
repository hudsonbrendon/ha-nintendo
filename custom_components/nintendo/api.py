"""Cliente da conta Nintendo (OAuth dos apps) e da API Moon (Controle Parental).

Mapeado por engenharia reversa do app Nintendo Switch Parental Controls 2.7.0:
- login: OAuth `session_token_code` + PKCE no accounts.nintendo.com (a pessoa
  entra na página oficial, onde a Nintendo pede o código enviado por e-mail);
- tokens: `session_token` (longo) -> `id_token` / `access_token` (15 min);
- Moon v2/v3 só aceita o **id_token** como Bearer (o access_token dá 403).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode

import aiohttp

CLIENT_ID = "54789befb391a838"
REDIRECT_URI = f"npf{CLIENT_ID}://auth"
SCOPE = (
    "openid user user.mii moonUser:administration moonDevice:create "
    "moonOwnedDevice:administration moonParentalControlSetting "
    "moonParentalControlSetting:update moonParentalControlSettingState "
    "moonPairingState moonSmartDevice:administration moonDailySummary moonMonthlySummary"
)
ACCOUNTS = "https://accounts.nintendo.com"
ACCOUNTS_API = "https://api.accounts.nintendo.com"
MOON = "https://app.lp1.znma.srv.nintendo.net"
APP_VERSION, APP_BUILD = "2.7.0", "740"
USER_AGENT = (
    f"moon_ANDROID/{APP_VERSION} (com.nintendo.znma; build:{APP_BUILD}; ANDROID 34)"
)
TIMEOUT = aiohttp.ClientTimeout(total=30)


class NintendoError(Exception):
    """Erro genérico da API."""


class NintendoAuthError(NintendoError):
    """Sessão inválida/expirada: precisa entrar de novo."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def build_auth_url() -> tuple[str, str]:
    """URL de autorização + verifier PKCE."""
    verifier = _b64(secrets.token_bytes(32))
    query = {
        "state": _b64(secrets.token_bytes(36)),
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "scope": SCOPE,
        "response_type": "session_token_code",
        "session_token_code_challenge": _b64(
            hashlib.sha256(verifier.encode()).digest()
        ),
        "session_token_code_challenge_method": "S256",
        "theme": "login_form",
    }
    return f"{ACCOUNTS}/connect/1.0.0/authorize?{urlencode(query)}", verifier


def parse_session_token_code(link: str) -> str:
    """Extrai o session_token_code do link do botão "Usar esta conta"."""
    link = link.strip()
    if "#" not in link:
        raise ValueError("link sem fragmento")
    code = parse_qs(link.split("#", 1)[1]).get("session_token_code")
    if not code:
        raise ValueError("link sem session_token_code")
    return code[0]


def token_subject(token: str) -> str:
    """ID da conta (sub) do JWT do session_token, sem chamar a rede."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))[
        "sub"
    ]


class NintendoClient:
    """Cliente assíncrono. Renova id/access token sozinho a partir do session_token."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        session_token: str,
        tz: str = "UTC",
        lang: str = "pt-BR",
    ) -> None:
        self._http = session
        self.session_token = session_token
        self._tz = tz
        self._lang = lang
        self._tokens: dict[str, Any] = {}
        self._exp = 0.0

    @staticmethod
    async def async_exchange_code(
        session: aiohttp.ClientSession, code: str, verifier: str
    ) -> str:
        """session_token_code + verifier -> session_token."""
        # O code é de uso único: só repete quando a conexão nem abriu (DNS/TCP),
        # aí a Nintendo não chegou a consumi-lo.
        for attempt in range(4):
            try:
                async with session.post(
                    f"{ACCOUNTS}/connect/1.0.0/api/session_token",
                    data={
                        "client_id": CLIENT_ID,
                        "session_token_code": code,
                        "session_token_code_verifier": verifier,
                    },
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "NASDKAPI; Android",
                    },
                    timeout=TIMEOUT,
                ) as resp:
                    data = await resp.json(content_type=None)
                break
            except aiohttp.ClientConnectorError as err:
                if attempt == 3:
                    raise NintendoError(f"session_token: {err}") from err
                await asyncio.sleep(2)
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise NintendoError(f"session_token: {err}") from err
        if resp.status != 200 or "session_token" not in data:
            raise NintendoAuthError(
                data.get("error_description") or data.get("error") or str(resp.status)
            )
        return data["session_token"]

    async def _async_tokens(self) -> dict[str, Any]:
        if self._tokens and time.time() < self._exp:
            return self._tokens
        try:
            async with self._http.post(
                f"{ACCOUNTS}/connect/1.0.0/api/token",
                json={
                    "client_id": CLIENT_ID,
                    "session_token": self.session_token,
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer-session-token",
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": "NASDKAPI; Android",
                },
                timeout=TIMEOUT,
            ) as resp:
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NintendoError(f"token: {err}") from err
        if resp.status in (400, 401) or "id_token" not in data:
            raise NintendoAuthError(
                data.get("error_description") or data.get("error") or str(resp.status)
            )
        self._tokens = data
        self._exp = time.time() + int(data.get("expires_in", 900)) - 60
        return data

    async def async_me(self) -> dict[str, Any]:
        """Perfil da conta Nintendo (apelido, país, Mii...)."""
        tok = await self._async_tokens()
        return await self._request(
            "GET", f"{ACCOUNTS_API}/2.0.0/users/me", tok["access_token"], {}
        )

    async def _moon(
        self, method: str, path: str, body: dict[str, Any] | None = None, **params: Any
    ) -> dict[str, Any]:
        tok = await self._async_tokens()
        headers = {
            "User-Agent": USER_AGENT,
            "X-Moon-App-Id": "com.nintendo.znma",
            "X-Moon-Os": "ANDROID",
            "X-Moon-Os-Version": "34",
            "X-Moon-Model": "Home Assistant",
            "X-Moon-TimeZone": self._tz,
            "X-Moon-Os-Language": self._lang,
            "X-Moon-App-Language": self._lang,
            "X-Moon-App-Display-Version": APP_VERSION,
            "X-Moon-App-Internal-Version": APP_BUILD,
        }
        return await self._request(
            method, MOON + path, tok["id_token"], headers, body, params
        )

    async def _request(
        self,
        method: str,
        url: str,
        bearer: str,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {
            **headers,
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
        }
        try:
            async with self._http.request(
                method,
                url,
                json=body,
                params=params or None,
                headers=headers,
                timeout=TIMEOUT,
            ) as resp:
                data = (
                    await resp.json(content_type=None)
                    if resp.content_length != 0
                    else {}
                )
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise NintendoError(f"{url}: {err}") from err
        if resp.status == 401:
            self._tokens = {}
            raise NintendoAuthError(f"{url}: 401")
        if resp.status >= 400:
            raise NintendoError(f"{url}: {resp.status} {data}")
        return data or {}

    # --- leitura -------------------------------------------------------
    async def async_moon_user(self) -> dict[str, Any]:
        return (await self._moon("GET", "/v2/actions/user/fetchUser")).get("user", {})

    async def async_devices(self) -> list[dict[str, Any]]:
        return (await self._moon("GET", "/v3/actions/user/fetchOwnedDevices")).get(
            "ownedDevices", []
        )

    async def async_daily_summaries(self, device_id: str) -> dict[str, Any]:
        return await self._moon(
            "GET", "/v2/actions/playSummary/fetchDailySummaries", deviceId=device_id
        )

    async def async_settings(self, device_id: str) -> dict[str, Any]:
        data = await self._moon(
            "GET",
            "/v3/actions/parentalControlSetting/fetchParentalControlSetting",
            deviceId=device_id,
        )
        return data.get("parentalControlSetting", {})

    async def async_latest_monthly(self, device_id: str) -> dict[str, Any]:
        return await self._moon(
            "GET",
            "/v2/actions/playSummary/fetchLatestMonthlySummary",
            deviceId=device_id,
        )

    # --- ações ---------------------------------------------------------
    async def async_update_play_timer(
        self, device_id: str, regulations: dict[str, Any]
    ) -> dict[str, Any]:
        keys = (
            "timerMode",
            "restrictionMode",
            "dailyRegulations",
            "eachDayOfTheWeekRegulations",
        )
        body = {
            "deviceId": device_id,
            "playTimerRegulations": {k: regulations.get(k) for k in keys},
        }
        return await self._moon(
            "POST", "/v3/actions/parentalControlSetting/updatePlayTimer", body
        )

    async def async_update_restriction_level(
        self, device_id: str, setting: dict[str, Any], level: str
    ) -> dict[str, Any]:
        custom = setting.get("customSettings", {})
        body = {
            "deviceId": device_id,
            "customSettings": custom,
            "parentalControlSettingEtag": setting.get("etag"),
            "vrRestrictionEtag": custom.get("vrRestrictionEtag"),
            "whitelistedApplicationList": setting.get("whitelistedApplicationList"),
            "functionalRestrictionLevel": level,
        }
        return await self._moon(
            "POST", "/v2/actions/parentalControlSetting/updateRestrictionLevel", body
        )

    async def async_update_unlock_code(
        self, device_id: str, code: str
    ) -> dict[str, Any]:
        return await self._moon(
            "POST",
            "/v2/actions/parentalControlSetting/updateUnlockCode",
            {"deviceId": device_id, "unlockCode": code},
        )

    async def async_extra_time(
        self, device_id: str, status: str, minutes: int | None = None
    ) -> dict[str, Any]:
        """status: TO_ADDED (com minutes), TO_INFINITY ou TO_CANCELED."""
        body: dict[str, Any] = {"deviceId": device_id, "status": status}
        if minutes is not None:
            body["additionalTime"] = minutes
        data = await self._moon(
            "POST", "/v2/actions/device/updateExtraPlayingTime", body
        )
        if data.get("status") in (
            "NO_EFFECT",
            "OVERTIME_ERROR",
            "DURING_LATE_NIGHT_ERROR",
            "FAILED",
        ):
            raise NintendoError(f"tempo extra recusado: {data.get('status')}")
        return data

    async def async_update_label(self, device_id: str, label: str) -> dict[str, Any]:
        return await self._moon(
            "POST",
            "/v3/actions/device/updateDeviceLabel",
            {"deviceId": device_id, "label": label},
        )

    async def async_start_pairing(self) -> dict[str, Any]:
        """Gera código de registro p/ digitar no console (Config. → Controle parental)."""
        return await self._moon(
            "POST", "/v2/actions/deviceFederation/startDeviceFederation"
        )

    async def async_check_pairing(self, device_id: str) -> dict[str, Any]:
        return await self._moon(
            "GET",
            "/v3/actions/deviceFederation/checkDeviceFederation",
            deviceId=device_id,
        )
