"""Buttons: restart, time sync, screenshot refresh."""
from __future__ import annotations

import time

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NovastarConfigEntry, is_cloud_entry
from .api import NovastarError
from .entity import NovastarEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: NovastarConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if is_cloud_entry(entry):
        return
    c = entry.runtime_data
    entities: list[ButtonEntity] = [RebootButton(c)]
    if c.supports("time"):
        entities.append(SyncTimeButton(c))
    if c.supports("screenshot"):
        entities.append(ScreenshotButton(c))
    async_add_entities(entities)


class RebootButton(NovastarEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reboot")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.async_reboot()
        except NovastarError as err:
            raise HomeAssistantError(str(err)) from err


class SyncTimeButton(NovastarEntity, ButtonEntity):
    """Send time and time zone of Home Assistant to the device."""

    _attr_translation_key = "sync_time"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "sync_time")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.async_set_time(
                self.hass.config.time_zone, int(time.time() * 1000)
            )
        except NovastarError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_refresh_policies()


class ScreenshotButton(NovastarEntity, ButtonEntity):
    """Fetch a new screenshot immediately."""

    _attr_translation_key = "refresh_screenshot"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "refresh_screenshot")

    async def async_press(self) -> None:
        entity = self.coordinator.screenshot_entity
        if entity is None:
            raise HomeAssistantError("Screenshot entity not available")
        await entity.async_refresh_screenshot()
