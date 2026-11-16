"""Sensors: brightness, device information and cloud data."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NovastarConfigEntry, is_cloud_entry
from .api import find_key
from .entity import NovastarCloudEntity, NovastarEntity


def _info(*keys: str) -> Callable[[dict[str, Any]], Any]:
    return lambda d: find_key(d.get("info") or {}, keys)


def _round(value: Any) -> float | None:
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _resolution(d: dict[str, Any]) -> str | None:
    info = d.get("info") or {}
    w, h = find_key(info, ("width",)), find_key(info, ("height",))
    return f"{w}×{h}" if w and h else None


@dataclass(frozen=True, kw_only=True)
class NovastarSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    feature: str | None = None
    only_if_present: bool = False  # create only if the device reports a value


SENSORS: tuple[NovastarSensorDescription, ...] = (
    NovastarSensorDescription(
        key="brightness",
        translation_key="brightness",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _round((d.get("brightness") or {}).get("percent")),
    ),
    NovastarSensorDescription(
        key="brightness_raw",
        translation_key="brightness_raw",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: (d.get("brightness") or {}).get("raw"),
    ),
    NovastarSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_info("mainVersion", "osVersion"),
    ),
    NovastarSensorDescription(
        key="android_version",
        translation_key="android_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        only_if_present=True,
        value_fn=_info("androidVersion"),
    ),
    NovastarSensorDescription(
        key="fpga_version",
        translation_key="fpga_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        only_if_present=True,
        value_fn=_info("fpga"),
    ),
    NovastarSensorDescription(
        key="resolution",
        translation_key="resolution",
        entity_category=EntityCategory.DIAGNOSTIC,
        only_if_present=True,
        value_fn=_resolution,
    ),
    NovastarSensorDescription(
        key="device_time",
        translation_key="device_time",
        feature="time",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: find_key(d.get("time") or {}, ("currentTime",)),
    ),
    NovastarSensorDescription(
        key="time_zone",
        translation_key="time_zone",
        feature="time",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: find_key(d.get("time") or {}, ("timeZone",)),
    ),
)

CLOUD_SENSORS: tuple[tuple[str, str], ...] = (
    ("cloud_last_online", "lastOnlineTime"),
    ("cloud_version", "version"),
    ("cloud_ip", "ip"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NovastarConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    c = entry.runtime_data
    if is_cloud_entry(entry):
        known: set[str] = set()

        @callback
        def _add_new_players() -> None:
            new = [sn for sn in (c.data or {}) if sn not in known]
            known.update(new)
            async_add_entities(
                CloudSensor(c, sn, key, field) for sn in new for key, field in CLOUD_SENSORS
            )

        _add_new_players()
        entry.async_on_unload(c.async_add_listener(_add_new_players))
        return

    async_add_entities(
        NovastarSensor(c, d)
        for d in SENSORS
        if (d.feature is None or c.supports(d.feature))
        and (not d.only_if_present or d.value_fn(c.data or {}) is not None)
    )


class NovastarSensor(NovastarEntity, SensorEntity):
    entity_description: NovastarSensorDescription

    def __init__(self, coordinator, description: NovastarSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        value = self.entity_description.value_fn(self.coordinator.data or {})
        return None if value in (None, "") else value


class CloudSensor(NovastarCloudEntity, SensorEntity):
    """Value reported by the VNNOX cloud."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, sn: str, key: str, field: str) -> None:
        super().__init__(coordinator, sn, key)
        self._attr_translation_key = key
        self._field = field

    @property
    def native_value(self) -> Any:
        value = self.player.get(self._field)
        return None if value in (None, "") else str(value)
