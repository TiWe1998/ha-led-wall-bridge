"""Async client for the local NovaStar Terminal Open API (HTTPS, port 16674)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import ssl
from typing import Any

import aiohttp

from .const import MAX_JSON_BYTES, MAX_SCREENSHOT_BYTES

_LOGGER = logging.getLogger(__name__)

CODE_TRANSIENT = 2
CODE_NOT_IMPLEMENTED = 12
CODE_NOT_LOGGED_IN = 18
CODE_TOKEN_EXPIRED = 39

SENSITIVE_KEYS = {"password", "token", "Authorization"}


class NovastarError(Exception):
    """Generic error."""


class NovastarConnectionError(NovastarError):
    """Device not reachable."""


class NovastarAuthError(NovastarError):
    """Login failed."""


class NovastarCertificateError(NovastarError):
    """The TLS certificate of the device does not match the stored fingerprint."""


class NovastarNotSupported(NovastarError):
    """Endpoint not implemented by the firmware (code 12)."""


class _Transient(NovastarError):
    """Temporary device error (e.g. code 2 'appService is null')."""


class _TokenExpired(NovastarError):
    """Token expired or not logged in."""


def redact(obj: Any) -> Any:
    """Mask passwords and tokens for logs and diagnostics."""
    if isinstance(obj, dict):
        return {k: ("**REDACTED**" if k in SENSITIVE_KEYS else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def find_key(obj: Any, keys: tuple[str, ...]) -> Any:
    """Recursively return the first non-empty value of one of the given keys."""
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] not in (None, ""):
                return obj[key]
        for value in obj.values():
            found = find_key(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_key(item, keys)
            if found is not None:
                return found
    return None


def _no_verify_context() -> ssl.SSLContext:
    """TLS context without CA verification (the device uses a self-signed certificate).

    Authenticity is ensured by certificate pinning instead (see fingerprint).
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def async_get_cert_fingerprint(host: str, port: int, timeout: float = 10) -> str:
    """Return the SHA-256 fingerprint (hex) of the device's TLS certificate."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=_no_verify_context()), timeout
        )
    except (OSError, asyncio.TimeoutError) as err:
        raise NovastarConnectionError(f"{host}:{port}: {err}") from err
    try:
        der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
    finally:
        writer.close()
    if not der:
        raise NovastarError("Device did not present a certificate")
    return hashlib.sha256(der).hexdigest()


def _limits() -> tuple[int, int]:
    return MAX_JSON_BYTES, MAX_SCREENSHOT_BYTES


async def _read_limited(resp: aiohttp.ClientResponse, limit: int) -> bytes:
    """Read a response body, refusing anything larger than limit."""
    length = getattr(resp, "content_length", None)
    if length is not None and length > limit:
        raise NovastarError(f"Response too large ({length} bytes)")
    body = bytearray()
    async for chunk in resp.content.iter_chunked(65536):
        body.extend(chunk)
        if len(body) > limit:
            raise NovastarError(f"Response too large (> {limit} bytes)")
    return bytes(body)


def to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class NovastarTerminalApi:
    """Client for a NovaStar player/controller (Taurus, T series, ...)."""

    VOLUME_PATHS = ("/core/v1/device/volume", "/core/v1/volume")

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        username: str,
        password: str,
        sn: str | None = None,
        fingerprint: str | None = None,
    ) -> None:
        self._session = session
        self.fingerprint = fingerprint
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sn = sn or None
        self.device_info: dict[str, Any] = {}
        self._token: str | None = None
        self._login_lock = asyncio.Lock()

    @property
    def _base(self) -> str:
        return f"https://{self.host}:{self.port}/terminal"

    @property
    def _ssl(self) -> aiohttp.Fingerprint | bool:
        """Pin the device certificate if a fingerprint is known."""
        if self.fingerprint:
            return aiohttp.Fingerprint(bytes.fromhex(self.fingerprint))
        return False

    # ------------------------------------------------------------------ internal

    async def _raw(
        self, method: str, path: str, payload: dict | None = None, auth: bool = True
    ) -> dict:
        headers = {"Content-Type": "application/json"}
        if auth and self._token:
            headers["Authorization"] = self._token
        url = self._base + path
        try:
            async with self._session.request(
                method,
                url,
                json=payload,
                headers=headers,
                ssl=self._ssl,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                text = (await _read_limited(resp, _limits()[0])).decode("utf-8", "replace")
                if resp.status in (401, 403):
                    raise _TokenExpired(f"HTTP {resp.status}")
                if resp.status >= 400:
                    raise NovastarError(f"HTTP {resp.status} for {path}: {text[:200]}")
        except aiohttp.ServerFingerprintMismatch as err:
            raise NovastarCertificateError(
                f"Certificate of {self.host} has changed - possible man-in-the-middle attack"
            ) from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise NovastarConnectionError(f"{url}: {err}") from err

        try:
            data = json.loads(text)
        except ValueError as err:
            raise NovastarError(f"No JSON response from {path}: {text[:200]}") from err
        _LOGGER.debug("%s %s -> %s", method, path, redact(data))
        if not isinstance(data, dict):
            raise NovastarError(f"Unexpected response from {path}: {data!r}")
        return data

    @staticmethod
    def _check(data: dict, path: str) -> Any:
        code = data.get("code", 0)
        if code == 0:
            return data.get("data")
        msg = data.get("message", "")
        if code in (CODE_TOKEN_EXPIRED, CODE_NOT_LOGGED_IN):
            raise _TokenExpired(msg)
        if code == CODE_NOT_IMPLEMENTED:
            raise NovastarNotSupported(f"{path}: {msg}")
        if code == CODE_TRANSIENT:
            raise _Transient(f"{path}: code {code} {msg}")
        raise NovastarError(f"{path}: code {code} {msg}")

    async def _ensure_login(self) -> None:
        if not self._token:
            async with self._login_lock:
                if not self._token:
                    await self.async_login()

    async def _request(self, method: str, path: str, payload: dict | None = None) -> Any:
        """Request with automatic (re-)login and retries on transient errors."""
        last_err: NovastarError | None = None
        for attempt in range(4):
            await self._ensure_login()
            try:
                data = await self._raw(method, path, payload)
                return self._check(data, path)
            except _TokenExpired as err:
                _LOGGER.debug("Token invalid, logging in again (attempt %s)", attempt + 1)
                self._token = None
                last_err = err
            except _Transient as err:
                _LOGGER.debug("Transient device error, retrying: %s", err)
                last_err = err
                await asyncio.sleep(2)
        if isinstance(last_err, _TokenExpired):
            raise NovastarAuthError("Re-login failed")
        raise NovastarError(str(last_err))

    # ------------------------------------------------------------------ public

    async def async_get(self, path: str) -> Any:
        return await self._request("GET", path)

    async def async_post(self, path: str, payload: dict | None = None) -> Any:
        return await self._request("POST", path, payload or {})

    async def async_login(self) -> None:
        """Log in and obtain a token."""
        if not self.sn:
            raise NovastarAuthError("Serial number (SN) missing")
        payload = {
            "sn": self.sn,
            "username": self.username,
            "password": self.password,
            "loginType": 2,
            "clientId": 1,
            "clientName": "HomeAssistant",
        }
        try:
            data = await self._raw("POST", "/core/v1/user/login", payload, auth=False)
        except _TokenExpired as err:
            raise NovastarAuthError(str(err)) from err
        if data.get("code", 0) != 0:
            raise NovastarAuthError(f"code {data.get('code')}: {data.get('message', '')}")
        token = find_key(data.get("data") or {}, ("token",))
        if not token:
            raise NovastarAuthError("No token in login response")
        self._token = str(token)
        _LOGGER.debug("Logged in to %s", self.host)

    async def async_fetch_device_info(self) -> dict[str, Any]:
        info = await self.async_get("/core/v2/device/info") or {}
        if isinstance(info, dict):
            self.device_info = info
        return self.device_info

    # Brightness ----------------------------------------------------------------

    async def async_get_brightness(self) -> dict[str, float | None]:
        """Return {'raw': 0-255, 'percent': 0-100}."""
        data = await self.async_get("/core/v1/brightness")
        if isinstance(data, (int, float)):
            raw, pct = float(data), None
        else:
            raw = to_float(find_key(data, ("brightness", "brightnessValue", "value")))
            pct = to_float(find_key(data, ("ratio", "percent", "percentage")))
        if pct is None and raw is not None:
            pct = raw * 100 / 255
        if raw is None and pct is not None:
            raw = pct * 255 / 100
        return {"raw": raw, "percent": pct}

    async def async_set_brightness(self, percent: float, persist: bool = True) -> None:
        percent = max(0.0, min(100.0, float(percent)))
        await self.async_post(
            "/core/v1/brightness",
            {"ratio": round(percent), "brightness": round(percent * 255 / 100), "solidity": persist},
        )

    # Volume --------------------------------------------------------------------

    async def async_get_volume(self) -> float | None:
        last: NovastarError | None = None
        for path in self.VOLUME_PATHS:
            try:
                data = await self.async_get(path)
                return to_float(find_key(data, ("ratio", "volume", "value")))
            except NovastarNotSupported as err:
                last = err
        raise last or NovastarNotSupported("volume")

    async def async_set_volume(self, percent: float, persist: bool = True) -> None:
        percent = max(0.0, min(100.0, float(percent)))
        payload = {"ratio": round(percent), "solidity": persist}
        last: NovastarError | None = None
        for path in self.VOLUME_PATHS:
            try:
                await self.async_post(path, payload)
                return
            except NovastarNotSupported as err:
                last = err
        raise last or NovastarNotSupported("volume")

    # Screen on/off (not supported by every firmware) ---------------------------

    async def async_get_screen_on(self) -> bool | None:
        data = await self.async_get("/core/v1/screen/status")
        value = (
            data
            if isinstance(data, (str, int, bool))
            else find_key(data, ("status", "state", "screenStatus", "value"))
        )
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value == 1
        if isinstance(value, str):
            return value.upper() in ("OPEN", "ON", "TRUE", "1")
        return None

    async def async_set_screen_on(self, on: bool) -> None:
        await self.async_post("/core/v1/screen/status", {"status": "OPEN" if on else "CLOSE"})

    # Schedules stored on the device -------------------------------------------

    async def async_set_brightness_policy(self, conditions: list[dict]) -> None:
        await self.async_post("/core/v1/brightness/timing-policy", {"conditions": conditions})

    async def async_set_power_policy(self, enable: bool, conditions: list[dict]) -> None:
        await self.async_post(
            "/core/v1/screen/power-policy", {"enable": enable, "conditions": conditions}
        )

    # System ----------------------------------------------------------------------

    async def async_reboot(self) -> None:
        await self.async_post("/core/v1/device/reboot", {"reason": "Home Assistant"})

    async def async_set_time(self, time_zone: str, utc_millis: int) -> None:
        await self.async_post(
            "/core/v1/device/time", {"timeZone": time_zone, "utcTimeMillis": utc_millis}
        )

    # Screenshot ------------------------------------------------------------------

    async def _raw_bytes(self, path: str, params: dict[str, str]) -> bytes:
        """GET returning binary data (with re-login)."""
        for _ in range(2):
            await self._ensure_login()
            try:
                async with self._session.get(
                    self._base + path,
                    params=params,
                    headers={"Authorization": self._token or ""},
                    ssl=self._ssl,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    body = await _read_limited(resp, _limits()[1])
                    ctype = resp.headers.get("Content-Type", "")
                    if resp.status in (401, 403):
                        self._token = None
                        continue
                    if resp.status >= 400:
                        raise NovastarError(f"HTTP {resp.status} for {path}")
            except aiohttp.ServerFingerprintMismatch as err:
                raise NovastarCertificateError(
                    f"Certificate of {self.host} has changed - possible man-in-the-middle attack"
                ) from err
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise NovastarConnectionError(str(err)) from err
            if "json" in ctype or body[:1] == b"{":
                try:
                    self._check(json.loads(body), path)
                except _TokenExpired:
                    self._token = None
                    continue
                raise NovastarError(f"{path}: no file received")
            return body
        raise NovastarAuthError("Re-login failed")

    async def async_screenshot(self) -> bytes:
        """Trigger a screenshot on the device and download it."""
        data = await self._request("GET", "/core/v1/device/screenshot?type=PNG")
        path = data if isinstance(data, str) else find_key(
            data, ("path", "filePath", "absolutePath", "screenshotPath", "url", "file")
        )
        if not path:
            raise NovastarError(f"No screenshot path in response: {redact(data)}")
        return await self._raw_bytes("/tools/v1/file/download", {"filePath": str(path)})

    # Relay -----------------------------------------------------------------------

    async def async_set_relay(self, on: bool, relay_type: str | None) -> None:
        payload: dict[str, Any] = {"status": 1 if on else 0}
        if relay_type:
            payload["type"] = relay_type
        await self.async_post("/core/v1/relay/status", payload)
