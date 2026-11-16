"""Binary sensors from the VNNOX cloud (one per player of the account)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NovastarConfigEntry, is_cloud_entry
from .entity import NovastarCloudEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: NovastarConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if not is_cloud_entry(entry):
        return
    c = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_players() -> None:
        new = [sn for sn in (c.data or {}) if sn not in known]
        known.update(new)
        async_add_entities(CloudOnline(c, sn) for sn in new)

    _add_new_players()
    entry.async_on_unload(c.async_add_listener(_add_new_players))


class CloudOnline(NovastarCloudEntity, BinarySensorEntity):
    """Online status of a player according to the VNNOX cloud."""

    _attr_translation_key = "cloud_online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, sn: str) -> None:
        super().__init__(coordinator, sn, "online")

    @property
    def is_on(self) -> bool | None:
        status = self.player.get("onlineStatus")
        return None if status is None else int(status) == 1

    @property
    def extra_state_attributes(self):
        return {"player_name": self.player.get("name")}
