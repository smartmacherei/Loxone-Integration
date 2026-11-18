"""System information page with the real HA runtime; skipped without HA.

hass.data[DOMAIN] holds one LoxoneCoordinator per config entry; the Miniserver data lives in its
structure file (msInfo, softwareVersion).
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import frame
    from custom_components.loxone.const import DOMAIN
    from custom_components.loxone.coordinator import LoxoneCoordinator
    from custom_components.loxone.miniserver import MiniServer
    from custom_components.loxone.system_health import system_health_info

STRUCTURE = {"softwareVersion": [16, 0, 4, 10], "msInfo": {
    "serialNr": "504F94A00000", "msName": "Haus", "projectName": "Einfamilienhaus",
    "localUrl": "192.168.1.77:80", "remoteUrl": "dns.loxonecloud.com/504F94A00000"}}


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class SystemHealthHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_health_test_")
        self.hass = HomeAssistant(self.directory.name)
        frame.async_setup(self.hass)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def test_miniserver_info_is_shown(self):
        entry = NS(entry_id="entry", unique_id="504F94A00000", options={
            CONF_USERNAME: "admin", CONF_PASSWORD: "pw", CONF_HOST: "192.168.1.77", CONF_PORT: 80})
        coordinator = LoxoneCoordinator(self.hass, entry)
        coordinator.miniserver = MiniServer(self.hass, STRUCTURE, entry)
        self.hass.data[DOMAIN] = {"entry": coordinator}
        self.assertEqual(await system_health_info(self.hass), {
            "Loxone Miniserver Serial": "504F94A00000",
            "Project Name": "Einfamilienhaus",
            "Local Url": "192.168.1.77:80",
            "Loxone Software Version": "16.0.4.10",
        })

    async def test_no_miniserver_shows_no_info(self):
        self.assertEqual(await system_health_info(self.hass), {})
        self.hass.data[DOMAIN] = {}
        self.assertEqual(await system_health_info(self.hass), {})
