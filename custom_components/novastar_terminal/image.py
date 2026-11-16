"""Screenshot of the content currently shown, as an image entity."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import NovastarConfigEntry, is_cloud_entry
from .api import NovastarError
from .const import CONF_SCREENSHOT_INTERVAL, DEFAULT_SCREENSHOT_INTERVAL
from .entity import NovastarEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: NovastarConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if is_cloud_entry(entry):
        return
    c = entry.runtime_data
    if c.supports("screenshot"):
        async_add_entities([NovastarScreenshot(hass, c, entry)])


def _content_type(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return "image/png"


class NovastarScreenshot(NovastarEntity, ImageEntity):
    _attr_translation_key = "screenshot"

    def __init__(self, hass: HomeAssistant, coordinator, entry: NovastarConfigEntry) -> None:
        NovastarEntity.__init__(self, coordinator, "screenshot")
        ImageEntity.__init__(self, hass)
        self._interval = int(
            entry.options.get(CONF_SCREENSHOT_INTERVAL, DEFAULT_SCREENSHOT_INTERVAL)
        )
        self._image = coordinator.screenshot
        if self._image:
            self._attr_content_type = _content_type(self._image)
            self._attr_image_last_updated = dt_util.utcnow()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.screenshot_entity = self
        if self._interval > 0:
            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._scheduled, timedelta(seconds=self._interval)
                )
            )

    @callback
    def _scheduled(self, _now) -> None:
        self.hass.async_create_task(self.async_refresh_screenshot())

    async def async_refresh_screenshot(self) -> None:
        try:
            data = await self.coordinator.api.async_screenshot()
        except NovastarError as err:
            _LOGGER.debug("Screenshot failed: %s", err)
            return
        self._image = data
        self._attr_content_type = _content_type(data)
        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return self._image
