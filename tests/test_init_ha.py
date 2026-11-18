"""Entry lifecycle of the integration with the real HA runtime; skipped without HA.

Two Miniservers side by side, entry updates and program parsing. Uses a temporary HA
instance and registries, fake Miniserver connections; no network.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace as NS
from unittest import mock

HAS_HA = importlib.util.find_spec("homeassistant") is not None
if HAS_HA:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntry, ConfigEntries
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from custom_components import loxone
    from custom_components.loxone import block_parameters, helpers, topology, transport
    from custom_components.loxone.const import SENDDOMAIN

A_UUID = "0f000000-0000-0001-ffffaaaaaaaaaaaa"
B_UUID = "0f000000-0000-0002-ffffbbbbbbbbbbbb"


def program(live, extension, uuid):
    return f'''<Root><C Type="LoxLIVE" U="{live}" Title="{live}">
      <C Type="LoxDigin" U="{live}-ext" Title="{extension}">
        <C Type="DigitalIn" U="{uuid}" Title="I1"><IoData Visu="false"/><Display Unit="&lt;v&gt;"/></C>
      </C></C></Root>'''.encode()


class Api:
    def __init__(self):
        self.sent, self.connection = [], None

    async def send_websocket_command(self, uuid, value):
        self.sent.append((uuid, value))

    async def send_secured__websocket_command(self, uuid, value, code):
        self.sent.append((uuid, value, code))

    async def close(self):
        pass


class Coordinator:
    def __init__(self, entry, controls):
        self.config_entry, self.api = entry, Api()
        self.miniserver = NS(lox_config=NS(json={"controls": controls}))
        self.applied_options = dict(entry.options)

    async def async_cleanup(self):
        pass


@unittest.skipUnless(HAS_HA, "Run with the installed Home Assistant Python runtime")
class InitHATest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="loxone_init_test_")
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        await self.hass.config_entries.async_initialize()
        dr.async_setup(self.hass)
        await asyncio.gather(dr.async_load(self.hass), er.async_load(self.hass))
        self.entries = {}
        for name in ("a", "b"):
            options = {"host": f"ms-{name}.invalid", "port": 80, "username": "test", "password": "FAKE_SECRET",
                       "auto_discovery": True, "udp_port": 0, "udp_max_signals": 50}
            entry = ConfigEntry(version=4, minor_version=1, domain="loxone", title=name, data={},
                                options=options, source="user", unique_id=name, discovery_keys={},
                                subentries_data=[])
            self.hass.config_entries._entries[entry.entry_id] = entry
            self.entries[name] = entry

    async def asyncTearDown(self):
        for entry_id in list(self.hass.data.get("loxone", {})):
            await loxone.async_unload_entry(self.hass, self.hass.config_entries.async_get_entry(entry_id))
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def load(self, name, controls):
        """What setup does for the commands of one Miniserver."""
        entry = self.entries[name]
        coordinator = Coordinator(entry, controls)
        self.hass.data.setdefault("loxone", {})[entry.entry_id] = coordinator
        loxone._async_setup_commands(self.hass)
        return coordinator

    async def test_token_write_does_not_reload_but_an_option_change_does(self):
        # HA stop writes the token into the entry data: that must not reload during shutdown.
        entry, reloads = self.entries["a"], []

        async def reload(entry_id):
            reloads.append(entry_id)
            return True
        self.hass.config_entries.async_reload = reload
        self.load("a", {})
        entry.add_update_listener(loxone.async_config_entry_updated)
        self.hass.config_entries.async_update_entry(
            entry, data={"token": "t", "hash_alg": "SHA256", "valid_until": 42})
        self.hass.config_entries.async_update_entry(entry, data={"token": "", "hash_alg": "", "valid_until": ""})
        await self.hass.async_block_till_done()
        self.assertEqual(reloads, [])
        self.hass.config_entries.async_update_entry(entry, options={**entry.options, "auto_discovery": False})
        await self.hass.async_block_till_done()
        self.assertEqual(reloads, [entry.entry_id])

    async def test_commands_go_only_to_the_miniserver_that_owns_the_uuid(self):
        a = self.load("a", {"uuid-a": {"uuidAction": "uuid-a", "subControls": {
            "uuid-a/sub": {"uuidAction": "uuid-a/sub"}}}})
        b = self.load("b", {"uuid-b": {"uuidAction": "uuid-b"}})
        await self.hass.services.async_call("loxone", "event_websocket_command",
                                            {"uuid": "uuid-a", "value": "on"}, blocking=True)
        entity = er.async_get(self.hass).async_get_or_create(
            "switch", "loxone", "uuid-b", config_entry=self.entries["b"])
        await self.hass.services.async_call("loxone", "event_secured_websocket_command",
                                            {"device": entity.entity_id, "value": "off", "code": "1234"}, blocking=True)
        self.hass.bus.async_fire(SENDDOMAIN, {"uuid": "uuid-b", "value": "pulse"})
        self.hass.bus.async_fire(SENDDOMAIN, {"uuid": "uuid-a/sub", "value": "off"})
        await self.hass.async_block_till_done()
        self.assertEqual(a.api.sent, [("uuid-a", "on"), ("uuid-a/sub", "off")])
        self.assertEqual(b.api.sent, [("uuid-b", "off", "1234"), ("uuid-b", "pulse")])

    async def test_unloading_one_miniserver_keeps_the_services_of_the_other(self):
        self.load("a", {"uuid-a": {"uuidAction": "uuid-a"}})
        b = self.load("b", {"uuid-b": {"uuidAction": "uuid-b"}})

        async def shade(call):
            pass
        self.hass.services.async_register("loxone", "quick_shade", shade)  # cover entity service
        self.assertTrue(await loxone.async_unload_entry(self.hass, self.entries["a"]))
        for service in ("event_websocket_command", "event_secured_websocket_command", "sync_areas", "reload",
                        "quick_shade"):
            self.assertTrue(self.hass.services.has_service("loxone", service), service)
        self.hass.bus.async_fire(SENDDOMAIN, {"uuid": "uuid-b", "value": "pulse"})
        await self.hass.async_block_till_done()
        self.assertEqual(b.api.sent, [("uuid-b", "pulse")])
        self.assertTrue(await loxone.async_unload_entry(self.hass, self.entries["b"]))
        self.assertFalse(self.hass.services.has_service("loxone", "event_websocket_command"))
        self.assertFalse(self.hass.services.has_service("loxone", "quick_shade"))
        self.hass.bus.async_fire(SENDDOMAIN, {"uuid": "uuid-b", "value": "pulse"})
        await self.hass.async_block_till_done()
        self.assertEqual(b.api.sent, [("uuid-b", "pulse")])

    async def topology(self, programs, names):
        values_for = {}

        async def fetch_program(session, host, port, username, password):
            await asyncio.sleep(0)
            return programs[host]

        async def fetch_values(session, host, port, username, password, uuids, *args, **kwargs):
            await asyncio.sleep(0)
            return {u: 1.0 for u in uuids}

        coordinators = []
        with mock.patch.object(topology, "async_fetch_program", fetch_program), \
                mock.patch.object(topology, "async_fetch_values", fetch_values), \
                mock.patch("homeassistant.helpers.aiohttp_client.async_get_clientsession", lambda hass: None):
            for name in names:
                coordinator = Coordinator(self.entries[name], {})
                self.hass.data.setdefault("loxone", {})[self.entries[name].entry_id] = coordinator
                coordinators.append(coordinator)
            await asyncio.gather(*(loxone._async_load_topology(
                self.hass, self.entries[name], coordinator, transport.SignalRouter(values_for.update))
                for name, coordinator in zip(names, coordinators)))
        return coordinators

    async def test_two_miniservers_starting_together_keep_their_initial_values(self):
        programs = {"ms-a.invalid": program("ms-a", "DI Flur", A_UUID),
                    "ms-b.invalid": program("ms-b", "DI Garage", B_UUID)}
        await self.topology(programs, ["a", "b"])
        self.assertEqual({A_UUID: 1.0, B_UUID: 1.0},
                         {u: helpers.initial_values.get(u) for u in (A_UUID, B_UUID)})
        self.assertEqual(helpers.device_map[A_UUID][1], "DI Flur")
        self.assertEqual(helpers.device_map[B_UUID][1], "DI Garage")
        self.assertEqual(helpers.get_or_create_device(A_UUID, "I1", "Terminal", "")["name"], "DI Flur")
        # Reload of A after renaming its extension in Loxone Config.
        self.assertTrue(await loxone.async_unload_entry(self.hass, self.entries["a"]))
        self.assertNotIn(A_UUID, helpers.initial_values)
        self.assertIn(B_UUID, helpers.initial_values)
        programs["ms-a.invalid"] = program("ms-a", "DI Eingang", A_UUID)
        await self.topology(programs, ["a"])
        self.assertEqual(helpers.get_or_create_device(A_UUID, "I1", "Terminal", "")["name"], "DI Eingang")

    async def test_program_is_parsed_off_the_event_loop(self):
        loop_thread, threads = threading.get_ident(), {}

        def probe(name, function):
            def run(*args, **kwargs):
                threads.setdefault(name, set()).add(threading.get_ident())
                return function(*args, **kwargs)
            return run
        with mock.patch.object(topology, "build_device_map", probe("devices", topology.build_device_map)), \
                mock.patch.object(topology, "enumerate_discoverable",
                                  probe("discovery", topology.enumerate_discoverable)), \
                mock.patch.object(transport, "_inventory", probe("loggers", transport._inventory)), \
                mock.patch.object(block_parameters, "without_structure_ids",
                                  probe("parameters", block_parameters.without_structure_ids)):
            await self.topology({"ms-a.invalid": program("ms-a", "DI Flur", A_UUID)}, ["a"])
        self.assertEqual(set(threads), {"devices", "discovery", "loggers", "parameters"})
        self.assertEqual({name: loop_thread in seen for name, seen in threads.items()},
                         dict.fromkeys(threads, False))
