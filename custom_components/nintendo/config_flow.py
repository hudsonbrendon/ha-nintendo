"""Config flow: login oficial da Nintendo (com o código enviado por e-mail) + link do botão."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    NintendoAuthError,
    NintendoClient,
    NintendoError,
    build_auth_url,
    parse_session_token_code,
    token_subject,
)
from .const import CONF_SESSION_TOKEN, DOMAIN, LOGGER

CONF_LINK = "link"


class NintendoConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._url, self._verifier = build_auth_url()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._login("user", user_input)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._login("reauth_confirm", user_input)

    async def _login(
        self, step: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                code = parse_session_token_code(user_input[CONF_LINK])
                token = await NintendoClient.async_exchange_code(
                    session, code, self._verifier
                )
            except ValueError:
                errors[CONF_LINK] = "invalid_link"
            except NintendoAuthError as err:
                LOGGER.debug("login recusado: %s", err)
                errors["base"] = "invalid_auth"
                self._url, self._verifier = build_auth_url()  # code é de uso único
            except NintendoError as err:
                LOGGER.debug("falha de conexão: %s", err)
                errors["base"] = "cannot_connect"
                self._url, self._verifier = build_auth_url()
            else:
                # o code já foi consumido: daqui pra frente nada pode falhar por rede
                title = token_subject(token)
                try:
                    title = (await NintendoClient(session, token).async_me()).get(
                        "nickname"
                    ) or title
                except NintendoError as err:
                    LOGGER.debug("perfil indisponível, título = id: %s", err)
                await self.async_set_unique_id(token_subject(token))
                data = {CONF_SESSION_TOKEN: token}
                if self.source == "reauth":
                    self._abort_if_unique_id_mismatch(reason="wrong_account")
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data=data
                    )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=title, data=data)
        return self.async_show_form(
            step_id=step,
            data_schema=vol.Schema({vol.Required(CONF_LINK): str}),
            description_placeholders={"url": self._url},
            errors=errors,
        )
