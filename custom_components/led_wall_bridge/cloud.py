"""Optional access to the VNNOX / NovaCloud OpenAPI (AppKey + AppSecret).

One cloud account entry serves all players of the account.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import hashlib
import json
import logging
import secrets
import time
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CLOUD_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class VnnoxCloudError(Exception):
    """Generic cloud error."""


class VnnoxCloudAuthError(VnnoxCloudError):
    """AppKey/AppSecret rejected."""


def normalize_domain(domain: str) -> str:
    return domain.strip().removeprefix("https://").removeprefix("http://").strip("/")


class VnnoxCloudApi:
    """Minimal client for the synchronous NovaCloud endpoints."""

    def __init__(self, session: aiohttp.ClientSession, domain: str, app_key: str, app_secret: str) -> None:
        self._session = session
        self._base = f"https://{normalize_domain(domain)}"
        self._key = app_key.strip()
        self._secret = app_secret.strip()

    def _headers(self) -> dict[str, str]:
        nonce = secrets.token_hex(16)
        cur_time = str(int(time.time()))
        checksum = hashlib.sha256((self._secret + nonce + cur_time).encode()).hexdigest()
        return {
            "AppKey": self._key,
            "Nonce": nonce,
            "CurTime": cur_time,
            "CheckSum": checksum,
            "Content-Type": "application/json; charset=utf-8",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = self._headers()
        if method == "GET":
            headers.pop("Content-Type", None)
        try:
            async with self._session.request(
                method,
                self._base + path,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
                **kwargs,
            ) as resp:
                text = await resp.text()
                _LOGGER.debug("VNNOX %s %s -> HTTP %s %s", method, path, resp.status, text[:500])
                if resp.status in (401, 403):
                    raise VnnoxCloudAuthError(f"HTTP {resp.status} from {self._base}: {text[:300]}")
                if resp.status == 429:
                    raise VnnoxCloudError("Rate limit reached (429)")
                if resp.status >= 400:
                    raise VnnoxCloudError(f"HTTP {resp.status} from {self._base}: {text[:300]}")
                try:
                    return json.loads(text) if text else None
                except ValueError as err:
                    raise VnnoxCloudError(f"No JSON response from {self._base}: {text[:200]}") from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise VnnoxCloudError(str(err)) from err

    async def async_list_players(self) -> list[dict[str, Any]]:
        """Return all players of the account."""
        players: list[dict[str, Any]] = []
        start, count = 0, 100
        while True:
            data = await self._request(
                "GET", "/v2/player/list", params={"start": start, "count": count}
            )
            rows = (data or {}).get("rows") or []
            players.extend(r for r in rows if isinstance(r, dict))
            total = int((data or {}).get("total") or 0)
            start += count
            if not rows or start >= total:
                return players

    async def async_online_status(self, sns: list[str]) -> dict[str, dict[str, Any]]:
        """Return online status per serial number (uppercase)."""
        result: dict[str, dict[str, Any]] = {}
        for i in range(0, len(sns), 100):
            data = await self._request(
                "POST", "/v2/player/current/online-status", json={"playerSns": sns[i : i + 100]}
            )
            for row in data if isinstance(data, list) else []:
                if isinstance(row, dict) and row.get("sn"):
                    result[str(row["sn"]).upper()] = row
        return result


class NovastarCloudCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls all players of a cloud account. Data: {SN (upper): player dict}."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: VnnoxCloudApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_cloud",
            update_interval=timedelta(seconds=CLOUD_SCAN_INTERVAL),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            players = await self.api.async_list_players()
            sns = [str(p["sn"]) for p in players if p.get("sn")]
            status = await self.api.async_online_status(sns) if sns else {}
        except VnnoxCloudAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VnnoxCloudError as err:
            raise UpdateFailed(f"VNNOX cloud: {err}") from err
        data: dict[str, dict[str, Any]] = {}
        for player in players:
            sn = str(player.get("sn", "")).upper()
            if sn:
                data[sn] = {**player, **status.get(sn, {})}
        return data
