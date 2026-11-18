"""The room list request of the options flow with the real HA runtime; skipped without HA.

aiohttp 3.14 (HA 2026.11) deprecates aiohttp.BasicAuth, removed in 4.0.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import warnings

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
    from homeassistant.core import HomeAssistant
    from custom_components.loxone import config_flow as flow


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class ConfigFlowAuthHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_flow_auth_test_")
        self.hass = HomeAssistant(self.directory.name)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def test_room_fetch_sends_basic_auth_without_the_deprecated_helper(self):
        response = MagicMock()
        response.json = AsyncMock(return_value={"rooms": {"r": {"name": "Room"}}})
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get.return_value = context
        options = {CONF_HOST: "ms", CONF_PORT: 80, CONF_USERNAME: "user", CONF_PASSWORD: "pässword"}
        with warnings.catch_warnings(record=True) as caught, patch(
                "homeassistant.helpers.aiohttp_client.async_get_clientsession", return_value=session):
            warnings.simplefilter("always")
            assert await flow.async_load_rooms(self.hass, options) == {"r": "Room"}
        assert [str(warning.message) for warning in caught if "BasicAuth" in str(warning.message)] == []
        kwargs = session.get.call_args.kwargs
        # "user:pässword" in latin-1, like aiohttp's default.
        assert kwargs["headers"] == {"Authorization": "Basic dXNlcjpw5HNzd29yZA=="}
        assert "auth" not in kwargs
