"""Switches: persist values, screen, device schedules, relay."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import NovastarConfigEntry, is_cloud_entry
from .api import NovastarError, find_key
from .entity import NovastarEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: NovastarConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if is_cloud_entry(entry):
        return
    c = entry.runtime_data
    entities: list[SwitchEntity] = [PersistSwitch(c)]
    if c.supports("screen"):
        entities.append(ScreenSwitch(c))
    if c.supports("brightness_policy"):
        entities.append(BrightnessScheduleSwitch(c))
    if c.supports("power_policy"):
        entities.append(PowerScheduleSwitch(c))
    if c.supports("relay"):
        entities.append(RelaySwitch(c))
    async_add_entities(entities)


class PersistSwitch(NovastarEntity, SwitchEntity, RestoreEntity):
    """Whether brightness/volume changes are stored permanently on the device.

    On:  the device keeps the value after a restart or power loss.
    Off: the value only applies until the next restart (saves flash write cycles,
         useful when an automation changes the brightness very often).
    """

    _attr_translation_key = "persist"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "persist")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            self.coordinator.persist = state.state != STATE_OFF

    @property
    def is_on(self) -> bool:
        return self.coordinator.persist

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.persist = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.persist = False
        self.async_write_ha_state()


class _Base(NovastarEntity, SwitchEntity):
    async def _run(self, coro) -> None:
        try:
            await coro
        except NovastarError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_refresh_policies()


class ScreenSwitch(_Base):
    _attr_translation_key = "screen"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "screen")

    @property
    def is_on(self) -> bool | None:
        return (self.coordinator.data or {}).get("screen_on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._run(self.coordinator.api.async_set_screen_on(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._run(self.coordinator.api.async_set_screen_on(False))


class BrightnessScheduleSwitch(_Base):
    """Enable/disable all brightness schedules stored on the device."""

    _attr_translation_key = "brightness_schedule"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "brightness_schedule")

    @property
    def _conditions(self) -> list[dict]:
        policy = (self.coordinator.data or {}).get("brightness_policy") or {}
        return [c for c in policy.get("conditions", []) if isinstance(c, dict)]

    @property
    def available(self) -> bool:
        return super().available and bool(self._conditions)

    @property
    def is_on(self) -> bool:
        return any(c.get("enable") for c in self._conditions)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "schedule": [
                {
                    "cron": c.get("cron"),
                    "brightness_percent": round(float(c.get("brightness", 0)) * 100 / 255),
                    "enable": c.get("enable"),
                }
                for c in self._conditions
            ]
        }

    async def _set(self, enable: bool) -> None:
        conditions = [
            {
                "cron": c.get("cron", []),
                "brightness": c.get("brightness", 0),
                "enable": enable,
                **({"type": c["type"]} if "type" in c else {}),
            }
            for c in self._conditions
        ]
        await self._run(self.coordinator.api.async_set_brightness_policy(conditions))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class PowerScheduleSwitch(_Base):
    """Enable/disable the screen on/off schedule stored on the device."""

    _attr_translation_key = "power_schedule"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "power_schedule")

    @property
    def _policy(self) -> dict:
        return (self.coordinator.data or {}).get("power_policy") or {}

    @property
    def is_on(self) -> bool:
        return bool(self._policy.get("enable"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"conditions": self._policy.get("conditions", [])}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._run(
            self.coordinator.api.async_set_power_policy(True, self._policy.get("conditions", []))
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._run(
            self.coordinator.api.async_set_power_policy(False, self._policy.get("conditions", []))
        )


class RelaySwitch(_Base):
    _attr_translation_key = "relay"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "relay")

    @property
    def _relay(self) -> Any:
        return (self.coordinator.data or {}).get("relay")

    @property
    def is_on(self) -> bool | None:
        status = find_key(self._relay, ("status",))
        return None if status is None else int(status) == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._run(self.coordinator.api.async_set_relay(True, find_key(self._relay, ("type",))))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._run(self.coordinator.api.async_set_relay(False, find_key(self._relay, ("type",))))
