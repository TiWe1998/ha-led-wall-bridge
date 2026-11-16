"""Config flow for NovaStar Terminal."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import (
    NovastarAuthError,
    NovastarConnectionError,
    NovastarError,
    NovastarNotSupported,
    NovastarTerminalApi,
)
from .cloud import VnnoxCloudApi, VnnoxCloudAuthError, VnnoxCloudError, normalize_domain
from .const import (
    CONF_APP_KEY,
    CONF_APP_SECRET,
    CONF_CLOUD_DOMAIN,
    CONF_ENTRY_TYPE,
    CONF_SCAN_INTERVAL,
    CONF_SCREENSHOT_INTERVAL,
    CONF_SN,
    DEFAULT_CLOUD_DOMAIN,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCREENSHOT_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    ENTRY_TYPE_CLOUD,
    ENTRY_TYPE_DEVICE,
    PORTAL_URL_EU,
    PORTAL_URL_US,
)

_LOGGER = logging.getLogger(__name__)
PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
PLACEHOLDERS = {"portal_eu": PORTAL_URL_EU, "portal_us": PORTAL_URL_US}


def _device_schema(d: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=d.get(CONF_HOST, "")): str,
            vol.Required(CONF_SN, default=d.get(CONF_SN, "")): str,
            vol.Required(CONF_USERNAME, default=d.get(CONF_USERNAME, DEFAULT_USERNAME)): str,
            vol.Required(CONF_PASSWORD): PASSWORD,
            vol.Required(CONF_PORT, default=d.get(CONF_PORT, DEFAULT_PORT)): int,
        }
    )


def _cloud_schema(d: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CLOUD_DOMAIN, default=d.get(CONF_CLOUD_DOMAIN, DEFAULT_CLOUD_DOMAIN)): str,
            vol.Required(CONF_APP_KEY, default=d.get(CONF_APP_KEY, "")): str,
            vol.Required(CONF_APP_SECRET): PASSWORD,
        }
    )


async def _validate_device(
    hass: HomeAssistant, data: Mapping[str, Any]
) -> tuple[NovastarTerminalApi | None, str | None]:
    api = NovastarTerminalApi(
        async_get_clientsession(hass, verify_ssl=False),
        data[CONF_HOST].strip(),
        data[CONF_PORT],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data[CONF_SN].strip().upper(),
    )
    try:
        await api.async_login()
        await api.async_get_brightness()
    except NovastarConnectionError as err:
        _LOGGER.warning("Connection failed: %s", err)
        return None, "cannot_connect"
    except NovastarAuthError as err:
        _LOGGER.warning("Login failed: %s", err)
        return None, "invalid_auth"
    except NovastarNotSupported as err:
        _LOGGER.warning("API not supported: %s", err)
        return None, "not_supported"
    except NovastarError:
        _LOGGER.exception("Unexpected error")
        return None, "unknown"
    return api, None


async def _validate_cloud(hass: HomeAssistant, data: Mapping[str, Any]) -> str | None:
    api = VnnoxCloudApi(
        async_get_clientsession(hass),
        data[CONF_CLOUD_DOMAIN],
        data[CONF_APP_KEY],
        data[CONF_APP_SECRET],
    )
    try:
        await api.async_list_players()
    except VnnoxCloudAuthError as err:
        _LOGGER.warning("VNNOX cloud rejected the credentials: %s", err)
        return "cloud_auth"
    except VnnoxCloudError as err:
        _LOGGER.warning("VNNOX cloud not reachable: %s", err)
        return "cloud_connect"
    return None


class NovastarConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["device", "cloud"])

    # ---------------------------------------------------------------- device

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api, error = await _validate_device(self.hass, user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(api.sn)
                self._abort_if_unique_id_configured(updates={CONF_HOST: api.host})
                title = "LED Wall"
                try:
                    info = await api.async_fetch_device_info()
                    title = info.get("aliasName") or info.get("productName") or title
                except NovastarError:
                    pass
                return self.async_create_entry(
                    title=title,
                    data={
                        **user_input,
                        CONF_ENTRY_TYPE: ENTRY_TYPE_DEVICE,
                        CONF_HOST: api.host,
                        CONF_SN: api.sn,
                    },
                )
        return self.async_show_form(
            step_id="device", data_schema=_device_schema(user_input or {}), errors=errors
        )

    # ---------------------------------------------------------------- cloud

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_CLOUD_DOMAIN] = normalize_domain(user_input[CONF_CLOUD_DOMAIN])
            user_input[CONF_APP_KEY] = user_input[CONF_APP_KEY].strip()
            user_input[CONF_APP_SECRET] = user_input[CONF_APP_SECRET].strip()
            error = await _validate_cloud(self.hass, user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(f"cloud_{user_input[CONF_APP_KEY]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"VNNOX ({user_input[CONF_CLOUD_DOMAIN]})",
                    data={**user_input, CONF_ENTRY_TYPE: ENTRY_TYPE_CLOUD},
                )
        return self.async_show_form(
            step_id="cloud",
            data_schema=_cloud_schema(user_input or {}),
            errors=errors,
            description_placeholders=PLACEHOLDERS,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Cloud credentials migrated from an older version."""
        await self.async_set_unique_id(f"cloud_{import_data[CONF_APP_KEY]}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"VNNOX ({normalize_domain(import_data[CONF_CLOUD_DOMAIN])})",
            data={**import_data, CONF_ENTRY_TYPE: ENTRY_TYPE_CLOUD},
        )

    # ---------------------------------------------------------------- reauth / reconfigure

    def _is_cloud(self, entry: ConfigEntry) -> bool:
        return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_CLOUD

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        cloud = self._is_cloud(entry)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            if cloud:
                error = await _validate_cloud(self.hass, data)
            else:
                _, error = await _validate_device(self.hass, data)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        if cloud:
            schema = vol.Schema(
                {
                    vol.Required(CONF_APP_KEY, default=entry.data[CONF_APP_KEY]): str,
                    vol.Required(CONF_APP_SECRET): PASSWORD,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD): PASSWORD,
                }
            )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders=PLACEHOLDERS,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        cloud = self._is_cloud(entry)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            if cloud:
                data[CONF_CLOUD_DOMAIN] = normalize_domain(data[CONF_CLOUD_DOMAIN])
                error = await _validate_cloud(self.hass, data)
            else:
                _, error = await _validate_device(self.hass, data)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        if cloud:
            schema = vol.Schema(
                {vol.Required(CONF_CLOUD_DOMAIN, default=entry.data[CONF_CLOUD_DOMAIN]): str}
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                    vol.Required(CONF_PORT, default=entry.data[CONF_PORT]): int,
                }
            )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NovastarOptionsFlow()


class NovastarOptionsFlow(OptionsFlow):
    """Options of a local device (the cloud entry has no options)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self.config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_CLOUD:
            return self.async_abort(reason="no_options")
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                    vol.Required(
                        CONF_SCREENSHOT_INTERVAL,
                        default=opts.get(CONF_SCREENSHOT_INTERVAL, DEFAULT_SCREENSHOT_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
                }
            ),
        )
