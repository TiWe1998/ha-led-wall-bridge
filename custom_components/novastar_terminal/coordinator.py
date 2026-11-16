"""Data update coordinator for a local device, with automatic feature detection."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    NovastarAuthError,
    NovastarCertificateError,
    NovastarError,
    NovastarNotSupported,
    NovastarTerminalApi,
)
from .const import DOMAIN, FEATURE_PATHS

_LOGGER = logging.getLogger(__name__)

# Values that rarely change are only refreshed every n-th poll
SLOW_EVERY = 10
# The device sometimes reports 'appService is null' for a few seconds.
# Keep the last values for this many consecutive failed polls before
# marking the entities unavailable.
TOLERATED_FAILURES = 3


class NovastarCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls all supported endpoints of one device."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: NovastarTerminalApi, interval: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.persist = True  # controlled by the "persist" switch entity
        self.screenshot: bytes | None = None
        self.screenshot_entity = None
        self.features: dict[str, bool] = {}  # True = supported by the firmware
        self._cycle = 0
        self._failures = 0

    def supports(self, feature: str) -> bool:
        return self.features.get(feature, False)

    async def async_detect_features(self) -> None:
        """Check once which endpoints the firmware implements."""
        for feature, path in FEATURE_PATHS.items():
            try:
                if feature == "volume":
                    await self.api.async_get_volume()  # tries both known paths
                else:
                    await self.api.async_get(path)
                self.features[feature] = True
            except NovastarNotSupported:
                self.features[feature] = False
            except (NovastarAuthError, NovastarCertificateError):
                raise
            except NovastarError as err:
                _LOGGER.debug("Feature %s not usable: %s", feature, err)
                self.features[feature] = False
        try:
            self.screenshot = await self.api.async_screenshot()
            self.features["screenshot"] = True
        except (NovastarAuthError, NovastarCertificateError):
            raise
        except NovastarError as err:
            _LOGGER.debug("Screenshot not usable: %s", err)
            self.features["screenshot"] = False
        _LOGGER.info(
            "NovaStar %s: supported features: %s",
            self.api.host,
            ", ".join(k for k, v in self.features.items() if v) or "none",
        )

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = dict(self.data or {})
        slow = self._cycle % SLOW_EVERY == 0
        self._cycle += 1
        try:
            if not self.features:
                await self.async_detect_features()

            # Brightness is mandatory - a failure here makes the device unavailable
            data["brightness"] = await self.api.async_get_brightness()

            async def optional(key: str, coro) -> None:
                try:
                    data[key] = await coro
                except (NovastarAuthError, NovastarCertificateError):
                    raise
                except NovastarError as err:
                    _LOGGER.debug("Polling %s failed: %s", key, err)

            if self.supports("volume"):
                await optional("volume", self.api.async_get_volume())
            if self.supports("screen"):
                await optional("screen_on", self.api.async_get_screen_on())
            if self.supports("relay"):
                await optional("relay", self.api.async_get(FEATURE_PATHS["relay"]))
            if slow or "info" not in data:
                await optional("info", self.api.async_fetch_device_info())
            for key in ("time", "brightness_policy", "power_policy"):
                if self.supports(key) and (slow or key not in data):
                    await optional(key, self.api.async_get(FEATURE_PATHS[key]))
            self._failures = 0
            return data
        except NovastarCertificateError as err:
            # Ask the user to confirm the new certificate (re-authentication flow)
            _LOGGER.error("%s", err)
            raise ConfigEntryAuthFailed(str(err)) from err
        except NovastarAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NovastarError as err:
            self._failures += 1
            if self.data and self._failures <= TOLERATED_FAILURES:
                _LOGGER.debug("Poll failed (%s/%s), keeping last values: %s",
                              self._failures, TOLERATED_FAILURES, err)
                return self.data
            raise UpdateFailed(str(err)) from err

    async def async_refresh_policies(self) -> None:
        """Reload immediately after a schedule or time change."""
        self._cycle = 0
        await self.async_request_refresh()
