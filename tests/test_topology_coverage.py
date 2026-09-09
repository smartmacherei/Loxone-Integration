"""Discovery preserves generic terminals and extension boundaries."""
import ast
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "loxone"
spec = importlib.util.spec_from_file_location("coverage_topology", ROOT / "topology.py")
top = importlib.util.module_from_spec(spec)
spec.loader.exec_module(top)


def test_link_subdevice_boundaries_and_generic_inputs(monkeypatch):
    monkeypatch.setattr(top, "classify_terminal", lambda *args: None)
    xml = b'''<Root><C Type="LoxLIVE" U="ms" Title="Test">
      <C Type="LoxDigin" U="extension" Title="DI Extension">
        <C Type="DigitalIn" U="input" Title="I1"><Display Unit="&lt;v&gt;"/></C>
      </C>
      <C Type="LoxOCEAN" U="ocean" Title="EnOcean">
        <C Type="LoxOCEANDevice" U="device" Title="Actuator">
          <C Type="LoxOCEANsensor" U="signal" Title="Input 1"><Display Unit="&lt;v&gt;"/></C>
        </C>
      </C></C></Root>'''
    devices = top.build_device_map(xml)
    assert devices["input"] == ("extension", "DI Extension")
    assert devices["signal"] == ("device", "Actuator")
    assert {u for u, c in top.enumerate_discoverable(xml, {}, devices)} == {"input", "signal"}


def test_raw_formats_are_read_only_and_visualized_not_duplicated(monkeypatch):
    monkeypatch.setattr(top, "classify_terminal", lambda *args: None)
    xml = b'''<Root><C Type="DaliActor" U="color"><Display Unit="&lt;v.col&gt;"/></C>
        <C Type="TreeTextActor" U="text"><Co K="Text"/></C>
        <C Type="TreeSensor" U="button"><Display Unit="&lt;v.i&gt;"/></C>
        <C Type="TreeSensor" U="visu"><IoData Visu="true"/><Display Unit="&lt;v&gt;"/></C></Root>'''
    found = dict(top.enumerate_discoverable(xml, {}))
    assert set(found) == {"color", "text", "button"}
    assert all(c["type"] == "RawTerminal" and c["auto_raw"] for c in found.values())


def test_actual_binary_name_rules_do_not_confuse_alarm_motion_and_unlock():
    # Execute the source table/function with enum values only; no HA runtime needed.
    source = ast.parse((ROOT / "binary_sensor.py").read_text(encoding="utf-8"))
    nodes = [n for n in source.body if
             isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == "NAME_DEVICE_CLASS_MAP"
             or isinstance(n, ast.FunctionDef) and n.name == "device_class_from_name"]
    attrs = {n.attr: n.attr.lower() for node in nodes for n in ast.walk(node)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "BinarySensorDeviceClass"}
    ns = {"BinarySensorDeviceClass": SimpleNamespace(**attrs)}
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + nodes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "binary_name_rules", "exec"), ns)
    classify = ns["device_class_from_name"]
    assert classify("Feueralarm") == "smoke"
    assert classify("Testtaste") is None
    assert classify("Motorbewegung") is None
    assert classify("Mit Schluessel entriegelt") is None
    assert classify("Sabotagekontakt") == "problem"
    assert classify("Presence") == "occupancy"


def test_http_wallbox_scaling_placeholders_and_server_error_codes(monkeypatch):
    import sys
    import pytest
    monkeypatch.setitem(sys.modules, "aiohttp", SimpleNamespace(
        BasicAuth=lambda *args: args, ClientTimeout=lambda **kwargs: kwargs))
    replies = {"target": {"LL": {"Code": "200", "value": "14296.0kW"}},
               "color": {"LL": {"Code": "200", "value": "<v.col>"}},
               "error": {"LL": {"Code": "404", "value": "1"}},
               "tiny": {"LL": {"Code": "200", "value": "1.25e-3A"}},
               "text": {"LL": {"Code": "200", "value": "hello"}}}
    class Reply:
        status = 200
        def __init__(self, data): self.data = data
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def json(self, **kwargs): return self.data
    class Session:
        def get(self, url, **kwargs): return Reply(replies[url.rsplit('/', 1)[1]])
    values = asyncio.run(top.async_fetch_values(Session(), 'server', 80, 'user', 'pass',
        list(replies), {'color', 'text'}, http_scales={'target': 0.001}))
    assert values.pop('target') == pytest.approx(14.296)
    assert values == {'tiny': 0.00125, 'text': 'hello'}
