import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(scope="session", autouse=True)
def _start_pycares_shutdown_thread():
    """pycares startet beim ersten Test einen Hintergrund-Thread – vorab starten,
    damit die Thread-Prüfung des Testframeworks nicht anschlägt."""
    try:
        import pycares

        channel = pycares.Channel()
        channel.close() if hasattr(channel, "close") else None
        del channel
    except Exception:  # noqa: BLE001
        pass
    yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


FINGERPRINT = "ab" * 32


@pytest.fixture(autouse=True)
def mock_cert_fingerprint():
    """No real TLS connection in tests: return a fixed certificate fingerprint."""
    from unittest.mock import patch

    with patch(
        "custom_components.novastar_terminal.async_get_cert_fingerprint", return_value=FINGERPRINT
    ), patch(
        "custom_components.novastar_terminal.config_flow.async_get_cert_fingerprint",
        return_value=FINGERPRINT,
    ):
        yield FINGERPRINT
