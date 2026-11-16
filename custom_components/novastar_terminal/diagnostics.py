"""Diagnostics download (Settings -> Device -> Download diagnostics)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import NovastarConfigEntry, is_cloud_entry
from .api import redact
from .const import CONF_APP_KEY, CONF_APP_SECRET, CONF_SN

TO_REDACT = {
    CONF_PASSWORD, CONF_SN, CONF_APP_KEY, CONF_APP_SECRET,
    "mac", "registerAddress", "sn", "ip", "playerId",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NovastarConfigEntry
) -> dict[str, Any]:
    c = entry.runtime_data
    result: dict[str, Any] = {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": async_redact_data(dict(entry.options), TO_REDACT),
    }
    if is_cloud_entry(entry):
        result["players"] = [async_redact_data(p, TO_REDACT) for p in (c.data or {}).values()]
    else:
        result["features"] = c.features
        result["persist"] = c.persist
        result["data"] = async_redact_data(redact(c.data or {}), TO_REDACT)
    return result
