"""Semantic bindings require structural evidence, never matching names."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components/loxone"
spec = importlib.util.spec_from_file_location("signal_bindings", ROOT / "signal_bindings.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

XML = '''<Root>
<C Type="TreeDevice" TreeType="32803" U="device">
 <C Type="TreeAactor" U="terminal" IName="AQ1" Channel="1" SubType="61" Title="Renamed">
  <Co K="I" U="terminal-input"/><Display Unit="&lt;v.1&gt;kW"/>
 </C>
 <C Type="ApiActor" U="api"><Co K="I" U="api-input"><In Input="ref-out"/></Co></C>
</C>
<C Type="OutputRef" U="ref" Ref="api">
 <Co K="AI" U="ref-in"><In Input="block-api"/></Co><Co K="AQ" U="ref-out"/>
</C>
<C Type="Wallbox" U="block"><Co K="OutputAPI" U="block-api"/><Co K="outLimit" U="target"/></C>
</Root>'''


def test_wallbox_target_power_uses_api_wiring_not_name():
    binding = module.SignalBindings(XML, {"controls": {"block": {"states": {"limit": "target"}}}})
    assert binding.source("terminal") == "target"
    assert binding.websocket_aliases(["terminal"]) == {"target": ["terminal"]}
    assert binding.http_scales(["terminal"]) == {"terminal": 0.001}


def test_other_channel_model_unit_or_controller_is_not_guessed():
    for old, new in [('Channel="1"', 'Channel="2"'), ('32803', '12345'),
                     ('kW', 'W'), ('Type="Wallbox"', 'Type="Other"'),
                     ('Input="ref-out"', 'Input="missing"')]:
        assert module.SignalBindings(XML.replace(old, new)).source("terminal") is None


def test_direct_output_can_use_reference_value_but_cannot_alias_inverted_source():
    xml = '''<Root><C Type="DaliActor" U="lamp"><Co K="I" U="lamp-in"><In Input="ref-out"/></Co></C>
    <C Type="OutputRef" U="ref"><Co K="AI" U="ref-in" Inv="true"><In Input="color"/></Co><Co K="AQ" U="ref-out"/></C>
    <C Type="LightController2" U="light"><Co K="AQ1" U="color"/></C></Root>'''
    cfg = {"controls": {"light": {"subControls": {"channel": {"states": {"color": "color"}}}}}}
    binding = module.SignalBindings(xml, cfg)
    assert binding.source("lamp") == "ref-out"
    assert binding.websocket_aliases(["lamp"]) == {}
    assert module.SignalBindings(xml.replace(' Inv="true"', ''), cfg).websocket_aliases(["lamp"]) == {"color": ["lamp"]}


def test_scaled_terminal_and_reference_cycle_are_rejected():
    xml = XML.replace('Title="Renamed"', 'SourceValHigh="100" DestValHigh="10"')
    assert module.SignalBindings(xml).source("terminal") is None
    cycle = XML.replace('Input="block-api"', 'Input="ref-out"')
    assert module.SignalBindings(cycle).source("terminal") is None


def test_websocket_binding_must_exist_in_structure():
    assert module.SignalBindings(XML, {}).websocket_aliases(["terminal"]) == {}
