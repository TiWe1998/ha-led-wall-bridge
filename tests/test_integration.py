"""Tests with simulated responses of a T series controller and the VNNOX cloud."""
import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.led_wall_bridge.const import DOMAIN

BASE = "https://192.0.2.10:16674/terminal"
CLOUD = "https://open-us.vnnox.com"
SN = "TESTSN000000001"
INFO = {"aliasName": "Demo-LED-Wall", "androidVersion": "5.1.1", "fpga": "3.0.1.5",
        "mac": "00:00:5e:00:53:01", "mainVersion": "4.0.0.0000", "model": "T2-4GV000000XX0000",
        "osVersion": "V000000XX0000", "productName": "T2-4G", "width": 384, "height": 192}
NOT_IMPL = {"code": 12, "message": "not find command"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
DEVICE_DATA = {"entry_type": "device", "host": "192.0.2.10", "port": 16674, "sn": SN,
               "username": "admin", "password": "x"}


def ok(data):
    return {"code": 0, "message": "", "data": data}


def mock_device(m):
    m.post(f"{BASE}/core/v1/user/login", json=ok({"token": "abc", "logined": True}))
    m.get(f"{BASE}/core/v2/device/info", json=ok(INFO))
    m.get(f"{BASE}/core/v1/brightness", json=ok({"brightness": 127, "ratio": 50.0, "solidity": True}))
    m.post(f"{BASE}/core/v1/brightness", json=ok({}))
    m.get(f"{BASE}/core/v1/device/volume", json=ok({"ratio": 0.0, "solidity": True}))
    m.post(f"{BASE}/core/v1/device/volume", json=ok({}))
    m.get(f"{BASE}/core/v1/screen/status", json=NOT_IMPL)
    m.get(f"{BASE}/core/v1/relay/status", json=NOT_IMPL)
    m.get(f"{BASE}/core/v1/brightness/timing-policy", json=ok({"type": "BRIGHTNESS", "conditions": [
        {"brightness": 0, "type": 1, "cron": ["0 45 6 * * ? *"], "enable": True},
        {"brightness": 128, "type": 1, "cron": ["0 45 7 * * ? *"], "enable": True}]}))
    m.post(f"{BASE}/core/v1/brightness/timing-policy", json=ok({}))
    m.get(f"{BASE}/core/v1/screen/power-policy", json=ok({"action": "", "enable": False, "type": "SCREENPOWER"}))
    m.get(f"{BASE}/core/v1/device/time", json=ok({"currentTime": "2026-01-01 12:00:00", "timeZone": "UTC"}))
    m.post(f"{BASE}/core/v1/device/time", json=ok({}))
    m.post(f"{BASE}/core/v1/device/reboot", json=ok({}))
    m.get(f"{BASE}/core/v1/device/screenshot?type=PNG", json=ok({"path": "/sdcard/screenshot/shot.png"}))
    m.get(f"{BASE}/tools/v1/file/download?filePath=/sdcard/screenshot/shot.png",
          content=PNG, headers={"Content-Type": "image/png"})


def mock_cloud(m, status=200):
    if status != 200:
        m.get(f"{CLOUD}/v2/player/list?start=0&count=100", status=status)
        return
    m.get(f"{CLOUD}/v2/player/list?start=0&count=100", json={
        "pageInfo": {"start": 0, "count": 100}, "total": 2, "rows": [
            {"playerId": "a", "name": "Demo", "sn": SN, "version": "V9.9", "ip": "198.51.100.7",
             "lastOnlineTime": "2026-01-01 12:00:00", "onlineStatus": 1},
            {"playerId": "b", "name": "Second wall", "sn": "TESTSN000000002", "version": "V1.0",
             "ip": "198.51.100.8", "lastOnlineTime": "2026-01-01 11:00:00", "onlineStatus": 0}]})
    m.post(f"{CLOUD}/v2/player/current/online-status", json=[
        {"sn": SN, "onlineStatus": 1, "lastOnlineTime": "2026-01-01 12:00:00"},
        {"sn": "TESTSN000000002", "onlineStatus": 0, "lastOnlineTime": "2026-01-01 11:00:00"}])


async def setup_device(hass, m, options=None):
    mock_device(m)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SN, title="Demo-LED-Wall", data=DEVICE_DATA, options=options or {})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def last_post(m, path):
    calls = [c for c in m.mock_calls if c[0] == "POST" and str(c[1]).endswith(path)]
    return calls[-1][2] if calls else None


async def test_device_entities(hass: HomeAssistant, aioclient_mock):
    entry = await setup_device(hass, aioclient_mock)
    assert entry.state is ConfigEntryState.LOADED
    light = hass.states.get("light.demo_led_wall")
    assert light.state == "on" and light.attributes["brightness"] == 128
    assert hass.states.get("switch.demo_led_wall_store_values_permanently").state == "on"
    assert hass.states.get("number.demo_led_wall_volume").state == "0"
    assert hass.states.get("sensor.demo_led_wall_resolution").state == "384×192"
    assert hass.states.get("image.demo_led_wall_screen_content") is not None
    assert not any("relay" in s.entity_id for s in hass.states.async_all())


async def test_persist_switch(hass: HomeAssistant, aioclient_mock):
    await setup_device(hass, aioclient_mock)
    await hass.services.async_call("light", "turn_on",
        {"entity_id": "light.demo_led_wall", "brightness_pct": 75}, blocking=True)
    assert last_post(aioclient_mock, "/core/v1/brightness")["solidity"] is True
    await hass.services.async_call("switch", "turn_off",
        {"entity_id": "switch.demo_led_wall_store_values_permanently"}, blocking=True)
    await hass.services.async_call("light", "turn_on",
        {"entity_id": "light.demo_led_wall", "brightness_pct": 40}, blocking=True)
    assert last_post(aioclient_mock, "/core/v1/brightness") == {"ratio": 40, "brightness": 102, "solidity": False}
    await hass.services.async_call("number", "set_value",
        {"entity_id": "number.demo_led_wall_volume", "value": 30}, blocking=True)
    assert last_post(aioclient_mock, "/core/v1/device/volume") == {"ratio": 30, "solidity": False}


async def test_actions(hass: HomeAssistant, aioclient_mock):
    await setup_device(hass, aioclient_mock)
    await hass.services.async_call("switch", "turn_off",
        {"entity_id": "switch.demo_led_wall_brightness_schedule_device"}, blocking=True)
    body = last_post(aioclient_mock, "/core/v1/brightness/timing-policy")
    assert len(body["conditions"]) == 2 and not any(c["enable"] for c in body["conditions"])
    await hass.services.async_call("button", "press",
        {"entity_id": "button.demo_led_wall_restart"}, blocking=True)
    assert last_post(aioclient_mock, "/core/v1/device/reboot") == {"reason": "Home Assistant"}


async def test_screenshot(hass: HomeAssistant, aioclient_mock, hass_client):
    await setup_device(hass, aioclient_mock)
    client = await hass_client()
    resp = await client.get("/api/image_proxy/image.demo_led_wall_screen_content")
    assert resp.status == 200 and await resp.read() == PNG


async def test_config_flow_menu_device(hass: HomeAssistant, aioclient_mock):
    mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "menu"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "device"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "host": "192.0.2.10", "port": 16674, "sn": SN.lower(), "username": "admin", "password": "x"})
    assert result["type"] == "create_entry"
    assert result["title"] == "Demo-LED-Wall"
    assert result["data"]["sn"] == SN and result["data"]["entry_type"] == "device"


async def test_config_flow_cloud(hass: HomeAssistant, aioclient_mock):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "cloud"})
    assert result["type"] == "form" and "portal_eu" in result["description_placeholders"]
    mock_cloud(aioclient_mock, status=401)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "cloud_domain": "https://open-us.vnnox.com/", "app_key": "k", "app_secret": "bad"})
    assert result["errors"] == {"base": "cloud_auth"}
    aioclient_mock.clear_requests()
    mock_cloud(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "cloud_domain": "https://open-us.vnnox.com/", "app_key": "k", "app_secret": "s"})
    assert result["type"] == "create_entry"
    assert result["data"]["cloud_domain"] == "open-us.vnnox.com"


async def test_cloud_account_serves_all_walls(hass: HomeAssistant, aioclient_mock):
    await setup_device(hass, aioclient_mock)
    mock_cloud(aioclient_mock)
    cloud = MockConfigEntry(domain=DOMAIN, unique_id="cloud_k", data={
        "entry_type": "cloud", "cloud_domain": "open-us.vnnox.com", "app_key": "k", "app_secret": "s"})
    cloud.add_to_hass(hass)
    assert await hass.config_entries.async_setup(cloud.entry_id)
    await hass.async_block_till_done()
    # local wall: cloud entities land on the same device
    assert hass.states.get("binary_sensor.demo_led_wall_online_vnnox_cloud").state == "on"
    assert hass.states.get("sensor.demo_led_wall_player_version_vnnox_cloud").state == "V9.9"
    # second wall only known in the cloud: own device
    assert hass.states.get("binary_sensor.second_wall_online_vnnox_cloud").state == "off"
    devreg = dr.async_get(hass)
    assert len(dr.async_entries_for_config_entry(devreg, cloud.entry_id)) == 2
    hdr = [c for c in aioclient_mock.mock_calls if "open-us" in str(c[1])][0][3]
    assert {"AppKey", "Nonce", "CurTime", "CheckSum"} <= set(hdr)


async def test_cloud_failure_keeps_local_working(hass: HomeAssistant, aioclient_mock):
    await setup_device(hass, aioclient_mock)
    mock_cloud(aioclient_mock, status=500)
    cloud = MockConfigEntry(domain=DOMAIN, unique_id="cloud_k", data={
        "entry_type": "cloud", "cloud_domain": "open-us.vnnox.com", "app_key": "k", "app_secret": "s"})
    cloud.add_to_hass(hass)
    await hass.config_entries.async_setup(cloud.entry_id)
    await hass.async_block_till_done()
    assert cloud.state is ConfigEntryState.SETUP_RETRY
    assert hass.states.get("light.demo_led_wall").state == "on"


async def test_legacy_cloud_options_migrated(hass: HomeAssistant, aioclient_mock):
    mock_cloud(aioclient_mock)
    entry = await setup_device(hass, aioclient_mock, options={
        "app_key": "k", "app_secret": "s", "cloud_domain": "open-us.vnnox.com", "persist": False})
    await hass.async_block_till_done()
    assert "app_key" not in entry.options
    clouds = [e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get("entry_type") == "cloud"]
    assert len(clouds) == 1
    assert hass.states.get("switch.demo_led_wall_store_values_permanently").state == "off"


async def test_options_flow(hass: HomeAssistant, aioclient_mock):
    entry = await setup_device(hass, aioclient_mock)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "scan_interval": 60, "screenshot_interval": 0})
    assert result["type"] == "create_entry"
    assert entry.options["screenshot_interval"] == 0


def test_translations_complete():
    base = Path(__file__).parents[1] / "custom_components" / "led_wall_bridge"
    ref = json.loads((base / "strings.json").read_text())

    def keys(d, p=""):
        out = set()
        for k, v in d.items():
            out |= keys(v, f"{p}.{k}") if isinstance(v, dict) else {f"{p}.{k}"}
        return out

    ref_keys = keys(ref)
    files = list((base / "translations").glob("*.json"))
    assert len(files) >= 12
    for f in files:
        assert keys(json.loads(f.read_text())) == ref_keys, f.name


async def test_legacy_cloud_entities_removed(hass: HomeAssistant, aioclient_mock):
    from homeassistant.helpers import entity_registry as er
    mock_device(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SN, data=DEVICE_DATA)
    entry.add_to_hass(hass)
    reg = er.async_get(hass)
    reg.async_get_or_create("binary_sensor", DOMAIN, f"{SN}_cloud_online", config_entry=entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert reg.async_get_entity_id("binary_sensor", DOMAIN, f"{SN}_cloud_online") is None



async def test_certificate_pinned_on_first_setup(hass: HomeAssistant, aioclient_mock):
    """Entries from older versions get the certificate pinned (trust on first use)."""
    entry = await setup_device(hass, aioclient_mock)
    assert entry.data["cert_fingerprint"] == "ab" * 32


async def test_config_flow_stores_fingerprint(hass: HomeAssistant, aioclient_mock):
    mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "device"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "host": "192.0.2.10", "port": 16674, "sn": SN, "username": "admin", "password": "x"})
    assert result["data"]["cert_fingerprint"] == "ab" * 32


async def test_certificate_change_triggers_reauth(hass: HomeAssistant, aioclient_mock):
    """A changed certificate must stop communication and ask the user."""
    import aiohttp

    aioclient_mock.get(f"{BASE}/core/v2/device/info",
                       exc=aiohttp.ServerFingerprintMismatch(b"a" * 32, b"b" * 32, "192.0.2.10", 16674))
    aioclient_mock.post(f"{BASE}/core/v1/user/login", json=ok({"token": "abc"}))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SN,
                            data={**DEVICE_DATA, "cert_fingerprint": "cd" * 32})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_oversized_screenshot_rejected(hass: HomeAssistant, aioclient_mock, monkeypatch):
    from custom_components.led_wall_bridge import api as api_mod
    from custom_components.led_wall_bridge.api import NovastarError, NovastarTerminalApi
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    import pytest

    monkeypatch.setattr(api_mod, "MAX_SCREENSHOT_BYTES", 16)
    mock_device(aioclient_mock)
    client = NovastarTerminalApi(async_get_clientsession(hass), "192.0.2.10", 16674, "admin", "x", SN)
    with pytest.raises(NovastarError, match="too large"):
        await client.async_screenshot()


def test_fingerprint_is_used_for_tls():
    import aiohttp
    from custom_components.led_wall_bridge.api import NovastarTerminalApi

    client = NovastarTerminalApi(None, "h", 1, "u", "p", "s", "ab" * 32)
    assert isinstance(client._ssl, aiohttp.Fingerprint)
    assert NovastarTerminalApi(None, "h", 1, "u", "p", "s")._ssl is False


async def test_short_device_hiccup_keeps_values(hass: HomeAssistant, aioclient_mock):
    """A brief 'appService is null' must not make the wall unavailable."""
    entry = await setup_device(hass, aioclient_mock)
    coordinator = entry.runtime_data
    aioclient_mock.clear_requests()
    mock_device(aioclient_mock)
    aioclient_mock._mocks = [m for m in aioclient_mock._mocks if not (
        m.method == "get" and str(m._url).endswith("/core/v1/brightness"))]
    aioclient_mock.get(f"{BASE}/core/v1/brightness", json={"code": 2, "message": "appService is null"})
    from unittest.mock import patch
    with patch("custom_components.led_wall_bridge.api.asyncio.sleep"):
        await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert hass.states.get("light.demo_led_wall").state == "on"
