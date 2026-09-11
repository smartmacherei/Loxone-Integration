"""Transport failure and recovery tests with a deterministic clock."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "loxone"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transport = load("transport")
states = load("control_states")
U = "00000000-0000-0000-0000000000000001"
H = "00000000-0000-0000-0000000000000002"


def router():
    clock, events = [0], []
    r = transport.SignalRouter(events.append, lambda: clock[0])
    r.heartbeat, r.udp_signals = H, {U}
    return r, clock, events


def test_unchanged_value_does_not_trigger_failure_with_heartbeat():
    r, clock, events = router()
    r.receive("poll", {U: 1})
    for second in range(1, 100):
        clock[0] = second
        r.receive("udp", {H: second})
        assert r.due([U]) == []
    assert events == [{U: 1}]
    clock[0] = 300
    r.receive("udp", {H: 0})
    assert r.due([U]) == []  # a healthy stream is not re-read every few minutes
    clock[0] = 1800
    r.receive("udp", {H: 0})
    assert r.due([U]) == [U]  # half-hourly verification even on a healthy stream


def test_heartbeat_loss_falls_back_then_recovers():
    r, clock, events = router()
    r.receive("udp", {H: 0, U: 1})
    r.receive("ws", {U: 2})
    assert events == [{U: 1}]
    clock[0] = 6
    r.receive("ws", {U: 2})
    assert events[-1] == {U: 2}
    clock[0] = 40
    r.websocket_state(False)
    assert r.due([U]) == [U]
    r.receive("poll", {U: 3})
    r.receive("udp", {H: 40, U: 4})
    assert events[-1] == {U: 4}


def test_inflight_poll_cannot_overwrite_newer_push():
    r, _, events = router()
    snapshot = dict(r.revision)
    r.receive("udp", {U: 2})
    r.receive("poll", {U: 1}, snapshot)
    assert events == [{U: 2}]


def test_timed_out_requests_do_not_starve_later_signals():
    r, _, _ = router()
    r.attempted(U)
    assert r.due([U, H]) == [H, U]


def test_alias_keeps_original_state_and_respects_udp_priority():
    r, clock, events = router()
    r.aliases = {"state": [U]}
    r.receive("ws", {"state": 7.4})
    assert events[-1] == {"state": 7.4, U: 7.4}
    r.receive("udp", {H: 1, U: 11})
    r.receive("ws", {"state": 12})
    assert events[-1] == {"state": 12}
    clock[0] = 6
    r.receive("ws", {"state": 13})
    assert events[-1] == {"state": 13, U: 13}


def test_quiet_websocket_alias_does_not_degrade_while_connection_is_open():
    r, clock, _ = router()
    r.aliases = {"state": [U]}
    r.receive("ws", {"state": 1})
    r.receive("poll", {U: 1})
    clock[0] = 60
    assert r.due([U]) == []
    r.websocket_state(False)
    assert r.due([U]) == [U]


def test_udp_loss_recovers_suppressed_websocket_snapshot_without_new_event():
    r, clock, events = router()
    r.receive("udp", {H: 0, U: 1})
    r.receive("ws", {U: 2})
    assert events[-1] == {U: 1}
    clock[0] = 6
    r.due([U])
    assert events[-1] == {U: 2}
    r.websocket_state(False)
    assert not r.ws_values


def test_all_paths_lost_marks_unknown_and_recovers_identical_value():
    r, clock, events = router()
    r.seed({U: 12})
    clock[0] = 89
    r.expire([U])
    assert events == []
    clock[0] = 90
    r.expire([U])
    assert events == [{U: None}]
    r.receive('udp', {H: 1})
    assert r.due([U]) == [U]
    r.receive('ws', {'other': 0})
    r.receive('poll', {U: 12})
    assert events[-1] == {U: 12}


def test_control_state_inventory_dedupes_and_never_invents_commands():
    cfg = {"controls": {"a": {"type": "Wallbox2", "name": "Charger", "uuidAction": H,
                               "states": {"active": U, "alias": U, "invalid": "x"}},
                         "b": {"type": "Switch", "states": {"active": H}}}}
    found = list(states.state_inventory(cfg))
    assert len(found) == 1
    assert found[0]["uuidAction"] == U
    assert found[0]["parent_id"] == H
    assert "command" not in found[0]


def test_only_matching_logger_port_configures_heartbeat():
    xml = f'<Root><C Type="Second" U="{H}"/><C Type="Logger" U="logger" Address="/dev/udp/1.2.3.4/55555"/>' \
          f'<LoggerMailer RefLogger="logger" On="{H};&lt;v&gt;" Off="{H};&lt;v&gt;"/></Root>'
    assert transport.logger_inventory(xml, 55555) == ({H}, H)
    assert transport.logger_inventory(xml, 55556) == (set(), None)


def test_unload_cleanup_does_not_return_an_object_for_ha_to_await():
    import ast
    from types import SimpleNamespace
    tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8"))
    cleanup = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_remove_transport")
    hass = SimpleNamespace(data={"loxone_transport": {"entry": object(), "other": object()}})
    ns = {"hass": hass, "DOMAIN": "loxone", "config_entry": SimpleNamespace(entry_id="entry")}
    exec(compile(ast.Module(body=[cleanup], type_ignores=[]), "cleanup", "exec"), ns)
    assert ns["_remove_transport"]() is None
    assert set(hass.data["loxone_transport"]) == {"other"}
    assert ns["_remove_transport"]() is None


def test_state_update_keeps_event_data_interface():
    update = transport.StateUpdate({U: 1})
    assert update.data == {U: 1} and U in update.data


def test_registry_entry_collection_does_not_probe_mapping_api():
    from types import SimpleNamespace
    compat = load("registry_compat")
    entry = SimpleNamespace(id="device")
    class Collection:
        def __iter__(self):
            return iter([entry])
        def __getattr__(self, name):
            raise AssertionError(name)
    assert list(compat.registry_entries(Collection())) == [entry]
    assert list(compat.registry_entries({"device": entry})) == [entry]


def test_poll_budget_rotates_fairly_and_bounds_each_cycle():
    r, clock, _ = router()
    keys = [f"00000000-0000-0000-00000000000000{i:02x}" for i in range(6)]
    first = r.due(keys, 4)
    assert len(first) == 4
    for key in first:
        r.attempted(key)
    clock[0] = 31
    second = r.due(keys, 4)
    assert second[:2] == [k for k in keys if k not in first]  # the two never-attempted keys go first
    assert len(second) == 4 and len(r.due(keys)) == 6


def test_expiry_window_follows_rotation_period():
    r, clock, events = router()
    r.receive("poll", {U: 1})
    clock[0] = 200
    r.expire([U], max_age=600)
    assert events == [{U: 1}]
    clock[0] = 700
    r.expire([U], max_age=600)
    assert events[-1] == {U: None}
