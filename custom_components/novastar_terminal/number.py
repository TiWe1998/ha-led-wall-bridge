"""Number entities: brightness (percent) and volume."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NovastarConfigEntry, is_cloud_entry
from .api import NovastarError, NovastarTerminalApi
from .entity import NovastarEntity


@dataclass(frozen=True, kw_only=True)
class NovastarNumberDescription(NumberEntityDescription):
    feature: str
    value_fn: Callable[[dict[str, Any]], float | None]
    set_fn: Callable[[NovastarTerminalApi, float, bool], Awaitable[None]]


NUMBERS: tuple[NovastarNumberDescription, ...] = (
    NovastarNumberDescription(
        key="brightness_level",
        translation_key="brightness_level",
        feature="brightness",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        value_fn=lambda d: (d.get("brightness") or {}).get("percent"),
        set_fn=lambda api, v, p: api.async_set_brightness(v, p),
    ),
    NovastarNumberDescription(
        key="volume",
        translation_key="volume",
        feature="volume",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        value_fn=lambda d: d.get("volume"),
        set_fn=lambda api, v, p: api.async_set_volume(v, p),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NovastarConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if is_cloud_entry(entry):
        return
    c = entry.runtime_data
    async_add_entities(NovastarNumber(c, d) for d in NUMBERS if c.supports(d.feature))


class NovastarNumber(NovastarEntity, NumberEntity):
    entity_description: NovastarNumberDescription

    def __init__(self, coordinator, description: NovastarNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        value = self.entity_description.value_fn(self.coordinator.data or {})
        return None if value is None else round(value)

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.entity_description.set_fn(
                self.coordinator.api, value, self.coordinator.persist
            )
        except NovastarError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
