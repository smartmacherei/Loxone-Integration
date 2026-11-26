"""Energy Flow Monitor (EFM): documented values become sensors, the rest stays raw (issue #22).

Structure File, section EnergyFlowMonitor: Ppwr/Gpwr/Spwr and actual0..N use the unit of
details.actualFormat, CO2 is kg/kWh, Pre/Pri are prices per kWh without a currency.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "loxone"
spec = importlib.util.spec_from_file_location("control_states", ROOT / "control_states.py")
states = importlib.util.module_from_spec(spec)
spec.loader.exec_module(states)


def uid(n):
    return f"00000000-0000-0000-0000{n:012x}"


EFM = {
    "type": "EFM", "name": "Energieflussmonitor", "uuidAction": uid(1), "room": "", "cat": "",
    "details": {
        "actualFormat": "%.3fkW", "totalFormat": "%.1fkWh", "storageFormat": "%.0f%%",
        "nodes": [
            {"title": "Netz", "nodeType": "Grid", "actualEfmState": uid(10)},
            {"title": "PV", "nodeType": "Group", "actualEfmState": uid(11),
             "nodes": [{"title": "PV DC1", "nodeType": "Production", "actualEfmState": uid(99)}]},
        ],
    },
    "states": {
        "Ppwr": uid(2), "Gpwr": uid(3), "Spwr": uid(4), "CO2": uid(5), "Pre": uid(6), "Pri": uid(7),
        "actual0": uid(10), "actual1": uid(11), "actual2": uid(12),
        "jLocked": uid(20), "selfConsumption": uid(21), "totalSelfConsumption": uid(22),
    },
}


def test_documented_states_become_values_with_their_format():
    values = {v["state"]: v for v in states.efm_values(EFM)}
    assert set(values) == {"Ppwr", "Gpwr", "Spwr", "CO2", "Pre", "Pri", "actual0", "actual1", "actual2"}
    assert values["Gpwr"] == {"state": "Gpwr", "uuid": uid(3), "name": "Energieflussmonitor Grid power",
                              "format": "%.3fkW"}
    assert values["actual0"]["name"] == "Energieflussmonitor Netz"
    assert values["actual1"]["name"] == "Energieflussmonitor PV"
    assert values["actual2"]["name"] == "Energieflussmonitor actual2"  # no node names this state
    assert values["actual0"]["format"] == "%.3fkW"
    assert values["CO2"]["format"] == "%.3f kg/kWh"
    assert values["Pri"]["format"] == "%.3f"


def test_actual_state_is_named_after_its_top_level_node_only():
    # Real structures: a child node inside a group can repeat the actualEfmState of a
    # top-level node. The Structure File gives actualEfmState to top-level nodes only.
    group = {"title": "PV Halle DC", "nodeType": "Group", "actualEfmState": uid(11),
             "nodes": [{"title": "PV Halle DC2", "nodeType": "Production", "actualEfmState": uid(12)}]}
    storage = {"title": "Speicher", "nodeType": "Storage", "actualEfmState": uid(12)}
    for nodes in ([group, storage], [storage, group]):
        efm = dict(EFM, details=dict(EFM["details"], nodes=nodes))
        names = {v["state"]: v["name"] for v in states.efm_values(efm)}
        assert names["actual2"] == "Energieflussmonitor Speicher"
        assert names["actual1"] == "Energieflussmonitor PV Halle DC"


def test_without_actual_format_power_states_stay_raw():
    efm = dict(EFM, details={})
    assert {v["state"] for v in states.efm_values(efm)} == {"CO2", "Pre", "Pri"}
    raw = {s["state_key"] for s in states.state_inventory({"controls": {uid(1): efm}})}
    assert {"Ppwr", "Gpwr", "Spwr", "actual0", "actual1", "actual2"} <= raw


def test_inventory_keeps_only_undocumented_states_raw_under_the_control_name():
    found = {s["state_key"]: s for s in states.state_inventory({"controls": {uid(1): EFM}})}
    assert set(found) == {"jLocked", "selfConsumption", "totalSelfConsumption"}
    assert {s["parent_name"] for s in found.values()} == {"Energieflussmonitor"}
    assert found["jLocked"]["name"] == "Energieflussmonitor: jLocked"
