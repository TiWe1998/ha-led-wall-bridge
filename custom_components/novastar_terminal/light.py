"""The LED wall as a light entity (brightness + on/off)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import NovastarConfigEntry, is_cloud_entry
from .api import NovastarError
from .entity import NovastarEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: NovastarConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if not is_cloud_entry(entry):
        async_add_entities([NovastarLight(entry.runtime_data)])


class NovastarLight(NovastarEntity, LightEntity, RestoreEntity):
    _attr_name = None  # the entity is named like the device
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_translation_key = "led_wall"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "light")
        self._last_percent: float = 100.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) and (
            pct := state.attributes.get("last_on_percent")
        ):
            self._last_percent = float(pct)

    @property
    def _percent(self) -> float | None:
        return ((self.coordinator.data or {}).get("brightness") or {}).get("percent")

    @property
    def _screen_api(self) -> bool:
        return self.coordinator.supports("screen") and (
            self.coordinator.data or {}
        ).get("screen_on") is not None

    @property
    def brightness(self) -> int | None:
        pct = self._percent
        return None if pct is None else round(pct * 255 / 100)

    @property
    def is_on(self) -> bool | None:
        if self._screen_api:
            return self.coordinator.data["screen_on"]
        pct = self._percent
        return None if pct is None else pct > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        b = (self.coordinator.data or {}).get("brightness") or {}
        policy = (self.coordinator.data or {}).get("brightness_policy") or {}
        return {
            "brightness_percent": None if b.get("percent") is None else round(b["percent"], 1),
            "brightness_raw": b.get("raw"),
            "last_on_percent": self._last_percent,
            "device_schedule_active": any(
                c.get("enable") for c in policy.get("conditions", []) if isinstance(c, dict)
            ),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        api = self.coordinator.api
        try:
            if self._screen_api and not self.coordinator.data.get("screen_on"):
                await api.async_set_screen_on(True)
            if ATTR_BRIGHTNESS in kwargs:
                await api.async_set_brightness(
                    kwargs[ATTR_BRIGHTNESS] * 100 / 255, self.coordinator.persist
                )
            elif not self._screen_api and not (self._percent or 0) > 0:
                await api.async_set_brightness(self._last_percent, self.coordinator.persist)
        except NovastarError as err:
            raise HomeAssistantError(f"LED wall: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        api = self.coordinator.api
        try:
            if self._screen_api:
                await api.async_set_screen_on(False)
            else:
                if (self._percent or 0) > 0:
                    self._last_percent = self._percent
                await api.async_set_brightness(0, self.coordinator.persist)
        except NovastarError as err:
            raise HomeAssistantError(f"LED wall: {err}") from err
        await self.coordinator.async_request_refresh()
