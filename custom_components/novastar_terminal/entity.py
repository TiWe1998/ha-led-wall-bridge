"""Base entities."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import find_key
from .cloud import NovastarCloudCoordinator
from .const import DOMAIN
from .coordinator import NovastarCoordinator


def _opt(value: Any) -> str | None:
    return str(value) if value else None


class NovastarEntity(CoordinatorEntity[NovastarCoordinator]):
    """Entity of a locally connected device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NovastarCoordinator, key: str) -> None:
        super().__init__(coordinator)
        base = (coordinator.config_entry.unique_id or coordinator.config_entry.entry_id).upper()
        self._attr_unique_id = f"{base}_{key}"
        info = coordinator.api.device_info
        mac = find_key(info, ("mac",))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, base)},
            connections={(CONNECTION_NETWORK_MAC, str(mac))} if mac else set(),
            manufacturer="NovaStar",
            model=str(find_key(info, ("productName",)) or "LED controller"),
            model_id=_opt(find_key(info, ("model",))),
            name=str(find_key(info, ("aliasName",)) or "LED Wall"),
            sw_version=_opt(find_key(info, ("mainVersion", "osVersion"))),
            hw_version=(lambda v: f"FPGA {v}" if v else None)(find_key(info, ("fpga",))),
            serial_number=coordinator.api.sn,
            configuration_url=f"https://{coordinator.api.host}:{coordinator.api.port}",
        )


class NovastarCloudEntity(CoordinatorEntity[NovastarCloudCoordinator]):
    """Entity of a player reported by the VNNOX cloud.

    Uses the same device identifier as the local entry (serial number), so the
    cloud entities appear on the same device when the wall is also set up locally.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: NovastarCloudCoordinator, sn: str, key: str) -> None:
        super().__init__(coordinator)
        self._sn = sn
        self._attr_unique_id = f"cloud_{sn}_{key}"
        player = coordinator.data.get(sn, {})
        # If the wall is also set up locally, reuse its name and model. Depending on
        # the Home Assistant version the cloud entities then either appear on the same
        # device or on a linked device with the same name.
        existing = dr.async_get(coordinator.hass).async_get_device(identifiers={(DOMAIN, sn)})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, sn)},
            manufacturer=(existing.manufacturer if existing else None) or "NovaStar",
            model=(existing.model if existing else None) or "VNNOX player",
            name=(existing.name if existing else None) or str(player.get("name") or sn),
            serial_number=sn,
        )

    @property
    def player(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self._sn, {})

    @property
    def available(self) -> bool:
        return super().available and bool(self.player)
