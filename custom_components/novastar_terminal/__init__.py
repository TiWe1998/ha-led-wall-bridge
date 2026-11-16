"""NovaStar LED controller (Terminal Open API) for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    NovastarAuthError,
    NovastarCertificateError,
    NovastarError,
    NovastarTerminalApi,
    async_get_cert_fingerprint,
)
from .cloud import NovastarCloudCoordinator, VnnoxCloudApi
from .const import (
    CONF_APP_KEY,
    CONF_APP_SECRET,
    CONF_CERT_FINGERPRINT,
    CONF_CLOUD_DOMAIN,
    CONF_ENTRY_TYPE,
    CONF_PERSIST,
    CONF_SCAN_INTERVAL,
    CONF_SN,
    DEFAULT_CLOUD_DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENTRY_TYPE_CLOUD,
)
from .coordinator import NovastarCoordinator

_LOGGER = logging.getLogger(__name__)

DEVICE_PLATFORMS = [
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]
CLOUD_PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type NovastarConfigEntry = ConfigEntry[NovastarCoordinator | NovastarCloudCoordinator]


def is_cloud_entry(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_CLOUD


def _platforms(entry: ConfigEntry) -> list[Platform]:
    return CLOUD_PLATFORMS if is_cloud_entry(entry) else DEVICE_PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: NovastarConfigEntry) -> bool:
    if is_cloud_entry(entry):
        api = VnnoxCloudApi(
            async_get_clientsession(hass),
            entry.data[CONF_CLOUD_DOMAIN],
            entry.data[CONF_APP_KEY],
            entry.data[CONF_APP_SECRET],
        )
        coordinator = NovastarCloudCoordinator(hass, entry, api)
        await coordinator.async_config_entry_first_refresh()
    else:
        _migrate_legacy_cloud_options(hass, entry)
        _remove_legacy_cloud_entities(hass, entry)
        await _ensure_fingerprint(hass, entry)
        api = NovastarTerminalApi(
            async_get_clientsession(hass, verify_ssl=False),
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data.get(CONF_SN),
            entry.data.get(CONF_CERT_FINGERPRINT),
        )
        try:
            await api.async_fetch_device_info()
        except (NovastarAuthError, NovastarCertificateError) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NovastarError as err:
            raise ConfigEntryNotReady(str(err)) from err
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        coordinator = NovastarCoordinator(hass, entry, api, interval)
        coordinator.persist = entry.options.get(CONF_PERSIST, entry.data.get(CONF_PERSIST, True))
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _ensure_fingerprint(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Entries created before version 1.2.1 have no pinned certificate yet.

    Pin the certificate the device presents now (trust on first use).
    """
    if entry.data.get(CONF_CERT_FINGERPRINT):
        return
    try:
        fingerprint = await async_get_cert_fingerprint(
            entry.data[CONF_HOST], entry.data[CONF_PORT]
        )
    except NovastarError as err:
        raise ConfigEntryNotReady(str(err)) from err
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_CERT_FINGERPRINT: fingerprint}
    )
    _LOGGER.info("Pinned TLS certificate of %s", entry.data[CONF_HOST])


def _migrate_legacy_cloud_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Version 1.1 stored cloud credentials in the device options.

    Move them into a separate cloud account entry (once).
    """
    if not (entry.options.get(CONF_APP_KEY) and entry.options.get(CONF_APP_SECRET)):
        return
    data = {
        CONF_CLOUD_DOMAIN: entry.options.get(CONF_CLOUD_DOMAIN) or DEFAULT_CLOUD_DOMAIN,
        CONF_APP_KEY: entry.options[CONF_APP_KEY],
        CONF_APP_SECRET: entry.options[CONF_APP_SECRET],
    }
    new_options = {
        k: v
        for k, v in entry.options.items()
        if k not in (CONF_APP_KEY, CONF_APP_SECRET, CONF_CLOUD_DOMAIN)
    }
    hass.config_entries.async_update_entry(entry, options=new_options)
    hass.async_create_task(
        hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data=data)
    )
    _LOGGER.info("Moved VNNOX cloud credentials into a separate cloud account entry")


def _remove_legacy_cloud_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Version 1.1 created cloud entities on the device entry - remove them.

    They are now provided by the separate cloud account entry.
    """
    registry = er.async_get(hass)
    legacy = ("_cloud_online", "_cloud_last_online", "_cloud_version", "_cloud_ip")
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        if ent.unique_id.endswith(legacy) and not ent.unique_id.startswith("cloud_"):
            registry.async_remove(ent.entity_id)


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NovastarConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, _platforms(entry))
