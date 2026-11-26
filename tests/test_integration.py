"""Config flow e setup com a API mockada pelos JSONs reais (anonimizados)."""

import base64
import json
import pathlib
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nintendo.const import CONF_SESSION_TOKEN, DOMAIN

FIX = json.loads((pathlib.Path(__file__).parent / "fixtures/moon.json").read_text())
DEV = {
    "deviceId": "dev0000000000001",
    "label": "Switch de 99hud",
    "parentalControlSettingStatus": "SYNCHRONIZED",
    "device": {
        "id": "dev0000000000001",
        "region": "USA",
        "serialNumber": "XTW0",
        "platformGeneration": "P00",
        "extraPlayingTime": None,
    },
}
API = "custom_components.nintendo.api.NintendoClient"


def _mock_client():
    return {
        "async_me": AsyncMock(
            return_value={"id": "naid1", "nickname": "99hud", "country": "BR"}
        ),
        "async_moon_user": AsyncMock(
            return_value={"miiUri": {"large": "https://x/mii.png"}}
        ),
        "async_devices": AsyncMock(return_value=[DEV]),
        "async_daily_summaries": AsyncMock(return_value=FIX["daily"]),
        "async_settings": AsyncMock(return_value=FIX["setting"]),
        "async_latest_monthly": AsyncMock(
            return_value={
                "year": 2026,
                "month": 6,
                "summary": {
                    "overall": {
                        "stat": {"totalDays": 1},
                        "dailyStats": [{"totalTime": 7}],
                    }
                },
            }
        ),
        "async_update_play_timer": AsyncMock(return_value={}),
        "async_extra_time": AsyncMock(return_value={"status": "SUCCESS"}),
        "async_start_pairing": AsyncMock(
            return_value={"deviceId": "new", "pairingCode": "123456"}
        ),
    }


async def test_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert (
        "accounts.nintendo.com/connect/1.0.0/authorize"
        in result["description_placeholders"]["url"]
    )
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"link": "lixo"}
    )
    assert bad["errors"] == {"link": "invalid_link"}
    st = (
        "x."
        + base64.urlsafe_b64encode(json.dumps({"sub": "naid1"}).encode())
        .decode()
        .rstrip("=")
        + ".y"
    )
    with (
        patch(f"{API}.async_exchange_code", AsyncMock(return_value=st)),
        patch(
            f"{API}.async_me",
            AsyncMock(return_value={"id": "naid1", "nickname": "99hud"}),
        ),
        patch(
            "custom_components.nintendo.async_setup_entry", AsyncMock(return_value=True)
        ),
    ):
        ok = await hass.config_entries.flow.async_configure(
            bad["flow_id"],
            {"link": "npf54789befb391a838://auth#session_token_code=abc&state=x"},
        )
    assert ok["type"] is FlowResultType.CREATE_ENTRY
    assert ok["title"] == "99hud" and ok["data"] == {CONF_SESSION_TOKEN: st}
    assert ok["result"].unique_id == "naid1"


async def test_setup_entities_and_actions(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="naid1", title="99hud", data={CONF_SESSION_TOKEN: "st"}
    )
    entry.add_to_hass(hass)
    mocks = _mock_client()
    with patch.multiple(API, **mocks):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        reg = er.async_get(hass)

        def eid(plat, key, uid="dev0000000000001"):
            return reg.async_get_entity_id(plat, DOMAIN, f"{uid}_{key}")

        assert len(er.async_entries_for_config_entry(reg, entry.entry_id)) == 31
        assert hass.states.get(eid("sensor", "tempo_jogo_mes")).state == "7"
        assert hass.states.get(eid("sensor", "tempo_jogo_7_dias")).state in ("0", "5")
        consoles = hass.states.get(eid("sensor", "consoles", "naid1"))
        assert (
            consoles.state == "1"
            and consoles.attributes["entity_picture"] == "https://x/mii.png"
        )
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": eid("number", "limite_diario"), "value": 60},
            blocking=True,
        )
        sent = mocks["async_update_play_timer"].call_args.args[1]
        assert sent["dailyRegulations"]["timeToPlayInOneDay"] == {
            "enabled": True,
            "limitTime": 60,
        }
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": eid("button", "tempo_extra_30")},
            blocking=True,
        )
        assert mocks["async_extra_time"].call_args.args[1:] == ("TO_ADDED", 30)
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": eid("button", "gerar_codigo_registro", "naid1")},
            blocking=True,
        )
        code = eid("sensor", "codigo_registro", "naid1")
        assert hass.states.get(code).state == "123456"
