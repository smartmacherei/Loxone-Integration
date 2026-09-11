"""Resolve explicit signal paths, including supported device API connectors.

Wallbox mapping evidence: Config 17.2 TechDoc outLimit = Tp (kW), project API
wiring, and LoxAPP3 states.limit = the same output connector UUID.
Never infer identity from display names or coincident values.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET


def controls_recursive(config):
    def walk(controls):
        for control in controls.values():
            yield control
            yield from walk(control.get("subControls", {}))
    yield from walk(config.get("controls", {}))


class SignalBindings:
    def __init__(self, xml, config=None, proxies=()):
        self.root = ET.fromstring(xml)
        # ``proxies``: UUIDs Config itself duplicates in a Gateway/Client partial
        # program (one Memory proxy per page for the same foreign terminal).
        identifiers = [e.get("U").lower() for e in self.root.iter()
                       if e.tag in {"C", "Co"} and e.get("U") and e.get("U").lower() not in proxies]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Duplicate UUID in source program")
        self.parents = {c: p for p in self.root.iter() for c in p}
        self.objects = {e.get("U", "").lower(): e for e in self.root.iter("C") if e.get("U")}
        self.connectors = {e.get("U", "").lower(): e for e in self.root.iter("Co") if e.get("U")}
        self.ws_states = {value.lower() for control in controls_recursive(config or {})
                          for value in control.get("states", {}).values() if isinstance(value, str)}

    @staticmethod
    def identity(el):
        if el.get("Inv", "false").lower() == "true":
            return False
        for source, dest in (("SourceValLow", "DestValLow"), ("SourceValHigh", "DestValHigh")):
            try:
                if float(el.get(source, "0")) != float(el.get(dest, "0")):
                    return False
            except ValueError:
                return False
        return True

    def upstream(self, co):
        """Resolve identity reference objects to an originating output connector."""
        seen = set()
        while co is not None:
            key = co.get("U", "").lower()
            if not key or key in seen or not self.identity(co):
                return None
            seen.add(key)
            owner = self.parents.get(co)
            if owner is None:
                return None
            if owner.get("Type") in {"OutputRef", "InputRef"} and co.get("K") == "AQ":
                if not self.identity(owner):
                    return None
                co = owner.find("Co[@K='AI']")
                if co is None or not self.identity(co):
                    return None
                inputs = co.findall("In")
                if len(inputs) != 1 or not self.identity(inputs[0]):
                    return None
                co = self.connectors.get(inputs[0].get("Input", "").lower())
                continue
            return co
        return None

    def device_for(self, el):
        while el in self.parents:
            el = self.parents[el]
            if el.get("Type") in {"TreeDevice", "LoxAIRDevice"}:
                return el
        return None

    def wallbox_source(self, terminal):
        device = self.device_for(terminal)
        if device is None:
            return None
        model = device.get("TreeType") or device.get("AirType")
        if (device.get("Type"), model) not in {("TreeDevice", "32803"), ("LoxAIRDevice", "72")}:
            return None
        # Only the documented target-power channel; not measured power, SOC or
        # vehicle status. Target power is a command, not proof of charging.
        if terminal.get("IName") != "AQ1" or terminal.get("SubType") != "61" or terminal.get("Channel") != "1":
            return None
        display = terminal.find("Display")
        if display is None or not display.get("Unit", "").endswith("kW"):
            return None
        candidates = []
        for api in device.iter("C"):
            if api.get("Type") != "ApiActor" or self.device_for(api) is not device:
                continue
            inputs = api.findall("Co[@K='I']/In")
            if len(inputs) != 1:
                continue
            co = self.upstream(self.connectors.get(inputs[0].get("Input", "").lower()))
            if co is None or co.get("K") != "OutputAPI":
                continue
            owner = self.parents[co]
            if owner.get("Type") != "Wallbox":
                continue
            out = owner.find("Co[@K='outLimit']")
            if out is not None:
                candidates.append(out)
        return candidates[0] if len(candidates) == 1 else None

    def source(self, terminal_id, follow_references=False):
        terminal = self.objects.get(terminal_id.lower())
        if terminal is None or not self.identity(terminal):
            return None
        # Numeric sensor outputs already provide their own value connector.
        for name in ("AQ", "Q"):
            co = terminal.find(f"Co[@K='{name}']")
            if co is not None:
                return co.get("U")
        inp = terminal.find("Co[@K='I']")
        if inp is None or not self.identity(inp):
            return None
        inputs = inp.findall("In")
        if len(inputs) == 1 and self.identity(inputs[0]):
            co = self.connectors.get(inputs[0].get("Input", "").lower())
            if follow_references:
                co = self.upstream(co)
        elif not inputs:
            co = self.wallbox_source(terminal)
        else:
            co = None
        return co.get("U") if co is not None else None

    def websocket_aliases(self, terminal_ids):
        aliases = {}
        for terminal in terminal_ids:
            source = self.source(terminal, follow_references=True)
            if source and source.lower() in self.ws_states:
                aliases.setdefault(source.lower(), []).append(terminal)
        return aliases

    def http_scales(self, terminal_ids):
        # FW 17.2.8.28 returns watts for the Wallbox target channel even when
        # /jdev/sps/io appends the configured kW display suffix. Verified against
        # Tree 32803 and Air 72 and their corresponding outLimit WS values.
        return {terminal: 0.001 for terminal in terminal_ids
                if terminal.lower() in self.objects
                and self.wallbox_source(self.objects[terminal.lower()]) is not None}
