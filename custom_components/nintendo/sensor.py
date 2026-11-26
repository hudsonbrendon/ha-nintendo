"""Sensores: tempo de jogo, jogos, limites, resumo mensal e código de registro."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import logic
from .coordinator import NintendoConfigEntry, NintendoCoordinator
from .entity import NintendoAccountEntity, NintendoDeviceEntity


@dataclass(frozen=True, kw_only=True)
class DevSensor(SensorEntityDescription):
    value: Callable[[dict[str, Any], Any], Any]
    attrs: Callable[[dict[str, Any], Any], dict[str, Any]] | None = None


def _today() -> Any:
    return dt_util.now().date()


def _day(d: dict[str, Any], offset: int = 0) -> dict[str, Any] | None:
    return logic.summary_for(d["daily"], _today() - timedelta(days=offset))


def _monthly_total(d: dict[str, Any]) -> int | None:
    stats = (d["monthly"].get("summary") or {}).get("overall", {}).get("dailyStats")
    return None if stats is None else sum(int(s.get("totalTime") or 0) for s in stats)


def _extra(d: dict[str, Any]) -> int:
    extra = d["owned"].get("device", {}).get("extraPlayingTime") or {}
    return (
        int(extra.get("inOneDay", {}).get("duration") or 0)
        if isinstance(extra, dict)
        else 0
    )


def _infinite(d: dict[str, Any]) -> bool:
    extra = d["owned"].get("device", {}).get("extraPlayingTime") or {}
    return bool(isinstance(extra, dict) and extra.get("inOneDay", {}).get("isInfinity"))


MIN = {
    "native_unit_of_measurement": UnitOfTime.MINUTES,
    "device_class": SensorDeviceClass.DURATION,
}

DEVICE_SENSORS: tuple[DevSensor, ...] = (
    DevSensor(
        key="tempo_jogo_hoje",
        **MIN,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d, t: logic.minutes(_day(d)),
        attrs=lambda d, t: {
            "jogadores": logic.players(_day(d)),
            "jogos": logic.games(_day(d)),
        },
    ),
    DevSensor(
        key="tempo_jogo_ontem",
        **MIN,
        value=lambda d, t: logic.minutes(_day(d, 1)),
        attrs=lambda d, t: {"jogos": logic.games(_day(d, 1))},
    ),
    DevSensor(
        key="tempo_jogo_7_dias",
        **MIN,
        value=lambda d, t: logic.minutes_since(d["daily"], _today(), 7),
    ),
    DevSensor(
        key="tempo_jogo_30_dias",
        **MIN,
        value=lambda d, t: logic.minutes_since(d["daily"], _today(), 30),
    ),
    DevSensor(
        key="tempo_jogo_mes",
        **MIN,
        value=lambda d, t: _monthly_total(d),
        attrs=lambda d, t: {
            "ano": d["monthly"].get("year"),
            "mes": d["monthly"].get("month"),
            "dias_jogados": (
                (d["monthly"].get("summary") or {}).get("overall", {}).get("stat") or {}
            ).get("totalDays"),
        },
    ),
    DevSensor(
        key="ultimo_jogo",
        value=lambda d, t: (t.last_game or {}).get("titulo"),
        attrs=lambda d, t: {
            k: v for k, v in (t.last_game or {}).items() if k != "titulo"
        },
    ),
    DevSensor(
        key="jogos_hoje",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda d, t: len(logic.games(_day(d))),
        attrs=lambda d, t: {"jogos": [g["titulo"] for g in logic.games(_day(d))]},
    ),
    DevSensor(
        key="limite_hoje",
        **MIN,
        value=lambda d, t: logic.limit_minutes(d["setting"], _today()),
    ),
    DevSensor(
        key="tempo_restante",
        **MIN,
        value=lambda d, t: None
        if _infinite(d)
        else logic.remaining_minutes(d["setting"], _day(d), _today(), _extra(d)),
        attrs=lambda d, t: {
            "tempo_extra": d["owned"].get("device", {}).get("extraPlayingTime")
        },
    ),
    DevSensor(
        key="hora_de_dormir_hoje",
        value=lambda d, t: (
            lambda b: f"{b['endingTime']['hour']:02d}:{b['endingTime']['minute']:02d}"
            if b.get("enabled") and b.get("endingTime")
            else None
        )(logic.regulation_today(d["setting"], _today()).get("bedtime") or {}),
    ),
    DevSensor(
        key="status_sincronizacao",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=["synchronized", "not_synchronized", "pending"],
        value=lambda d, t: (
            d["owned"].get("parentalControlSettingStatus") or ""
        ).lower()
        or None,
    ),
    DevSensor(
        key="ultima_atualizacao",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda d, t: datetime.fromtimestamp(d["daily"]["lastUpdatedAt"], UTC)
        if d["daily"].get("lastUpdatedAt")
        else None,
    ),
    DevSensor(
        key="regiao",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d, t: d["owned"].get("device", {}).get("region"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NintendoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coord = entry.runtime_data
    entities: list[SensorEntity] = [
        NintendoDeviceSensor(coord, dev_id, desc)
        for dev_id in coord.data["devices"]
        for desc in DEVICE_SENSORS
    ]
    entities += [ConsolesSensor(coord), PairingCodeSensor(coord)]
    async_add_entities(entities)


class NintendoDeviceSensor(NintendoDeviceEntity, SensorEntity):
    entity_description: DevSensor

    def __init__(
        self, coord: NintendoCoordinator, dev_id: str, desc: DevSensor
    ) -> None:
        super().__init__(coord, dev_id, desc.key)
        self.entity_description = desc

    @property
    def _tracker(self) -> logic.PlayTracker:
        return self.coordinator.trackers.setdefault(self.device_id, logic.PlayTracker())

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.dev, self._tracker)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs
        return fn(self.dev, self._tracker) if fn else None

    @property
    def entity_picture(self) -> str | None:
        if self.entity_description.key == "ultimo_jogo":
            return (self._tracker.last_game or {}).get("imagem")
        return None


class ConsolesSensor(NintendoAccountEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord: NintendoCoordinator) -> None:
        super().__init__(coord, "consoles")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data["devices"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        me = self.coordinator.data.get("me") or {}
        return {
            "consoles": [
                d["owned"].get("label")
                for d in self.coordinator.data["devices"].values()
            ],
            "apelido": me.get("nickname"),
            "pais": me.get("country"),
            "fuso_horario": (me.get("timezone") or {}).get("name"),
        }

    @property
    def entity_picture(self) -> str | None:
        return (
            (self.coordinator.data.get("me") or {}).get("moon", {}).get("miiUri") or {}
        ).get("large")


class PairingCodeSensor(NintendoAccountEntity, SensorEntity):
    def __init__(self, coord: NintendoCoordinator) -> None:
        super().__init__(coord, "codigo_registro")

    @property
    def native_value(self) -> str | None:
        p = self.coordinator.pairing
        return (
            p["pairingCode"]
            if p and p.get("status") not in logic.PAIRING_DONE
            else None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self.coordinator.pairing or {}
        return {"status": p.get("status"), "console": p.get("deviceId")}
