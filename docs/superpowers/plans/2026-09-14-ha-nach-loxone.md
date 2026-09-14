# Weg 3: HA → Loxone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HA-Entitäten mit Label „loxone“ per Knopfdruck als virtuellen UDP-Eingang ins Gateway-Programm eintragen und ihre Werte per UDP senden.

**Architecture:** Ein HA-freies Modul `ha_values_program.py` ändert das Programm-XML (ein `VirtualUdpIn` „HA Werte“ mit `VirtualUdpInCmd` je Wert unter der `VirtualInCaption` des Gateways) und hängt sich in `udp_program.prepare()` hinter `patch_xml`. `ha_values.py` hält Wertregeln (HA-frei) plus Sender, Store, Knopf-Logik; `button.py`/`sensor.py` liefern Knopf und Diagnose-Sensor. `UdpSetup` reicht die Wunschliste an `install` durch und kennt `check(force=True)`.

**Tech Stack:** Python 3.12, Home Assistant custom integration, pytest offline (`py -3.12 -m pytest tests -q`), HA-Laufzeittests im Container.

**Spec:** `docs/superpowers/specs/2026-09-14-ha-nach-loxone-design.md`

## Global Constraints

- Port fest `55556`, Label `loxone`, Titel des Eingangs `HA Werte`, `IName` `HAV` / `HAV<n>`.
- UUID-Namensraum `doc_id + "/smartmacherei/havalues/" + label`, Suffix = letzte 16 Zeichen der Document-UUID.
- Keine Programmänderung ohne Knopfdruck; Weg 2 (`auto_configure_udp`) muss an sein.
- `udp_max_signals` deckelt die Zahl der Werte.
- Datagramm `<schlüssel>=<zahl>`, UTF-8, Zahl mit Punkt, ohne Zeilenende.
- Stil: bestehende Muster (`_span`, `_append`, `coded_error`, deterministische UUIDs), CRLF/LF der jeweiligen Datei erhalten, Commit nach jedem Task, kein Push.

---

### Task 1: Document-Stempel aus patch_xml herausziehen

**Files:**
- Modify: `custom_components/loxone/udp_program.py` (Ende von `patch_xml`, ca. Zeilen 410-433)
- Test: bestehende `tests/test_udp_install.py` (Regression)

**Interfaces:**
- Produces: `stamp_document(text: str, doc_id: str, proxies: set[str] = frozenset()) -> bytes` — setzt `Date`, `DateS`, `NumO` am Document und prüft doppelte UUIDs; wirft `ValueError`.

- [ ] Step 1: Funktion anlegen, Code aus `patch_xml` verschieben:

```python
def stamp_document(text: str, doc_id: str, proxies=frozenset()) -> bytes:
    """Refresh Date/DateS/NumO on the Document and reject duplicate identities."""
    date = dt.datetime.now().replace(microsecond=0)
    date_s = int((dt.datetime.now(dt.timezone.utc) - dt.datetime(2009, 1, 1, tzinfo=dt.timezone.utc)).total_seconds())
    start, _ = _span(text, doc_id)
    end = text.index(">", start) + 1
    tag = text[start:end]
    for key, value in {"Date": date.strftime("%Y-%m-%d %H:%M:%S"), "DateS": str(date_s),
                       "NumO": str(len(list(ET.fromstring(text).iter("C"))))}.items():
        tag, count = re.subn(r'\b' + key + r'="[^"]*"', key + '="' + value + '"', tag)
        if count != 1:
            raise ValueError("Missing Document attribute " + key)
    result = (text[:start] + tag + text[end:]).encode("utf-8")
    ids = [el.get("U").lower() for el in ET.fromstring(result).iter()
           if el.get("U") and (el.tag in {"C", "Co"} or re.fullmatch(
               r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{16}", el.get("U")))]
    if len(ids) != len(set(ids)) and {value for value in ids if ids.count(value) > 1} - set(proxies):
        raise ValueError("Duplicate UUID in patched program")
    return result
```
   In `patch_xml` bleibt nur `return stamp_document(text, doc_id, proxies), report`.
- [ ] Step 2: `py -3.12 -m pytest tests -q` → alle grün. Commit „Document-Stempel als eigene Funktion“.

### Task 2: Programmänderung `ha_values_program.py`

**Files:**
- Create: `custom_components/loxone/ha_values_program.py`
- Modify: `custom_components/loxone/udp_errors.py` (REASONS: `HA_VALUES_PORT_IN_USE`)
- Test: `tests/test_ha_values_program.py`

**Interfaces:**
- Produces: `patch_ha_values(xml: bytes, entries: list[dict], port: int = PORT) -> tuple[bytes, dict]`; `entries` = `[{"key": str, "title": str, "digital": bool}]`; Report `{"ha_values": n, "ha_values_changed": bool}`. Konstanten `PORT = 55556`, `TITLE = "HA Werte"`, `INAME = "HAV"`.

- [ ] Step 1: Tests schreiben (Einzel-XML aus `test_udp_install.XML` plus `VirtualInCaption`, Verbund-XML aus `test_gateway_udp` plus `VirtualInCaption` je LoxLIVE):
  - Anlage: `VirtualUdpIn` mit Port, `IName` HAV, zwei Befehle HAV1/HAV2 mit `Check="sensor.a=\v"`, deterministische UUIDs, NumO aktualisiert.
  - Idempotenz: zweiter Aufruf mit gleicher Liste liefert `xml` unverändert.
  - Änderung ersetzt Block, bewahrt geänderten Titel je UUID.
  - Leere Liste entfernt den Block.
  - Fremder `VirtualUdpIn` mit Port 55556 → `udp_code == "HA_VALUES_PORT_IN_USE"`.
  - Fremdes Objekt mit `IName="HAV3"` → `ValueError`.
  - Verbund: nur die Caption des Gateway-LoxLIVE bekommt den Block; Client-Teilprogramm bleibt byteidentisch.
  - Ungültiger Schlüssel (`"a b"`) → `ValueError`.
- [ ] Step 2: Tests laufen rot (Modul fehlt).
- [ ] Step 3: Implementierung:

```python
"""Weg 3: HA values as one virtual UDP input in the gateway program (HA-free)."""
import re
import uuid
import xml.etree.ElementTree as ET

from .udp_errors import coded_error
from .udp_program import _append, _span, stamp_document

PORT = 55556
TITLE = "HA Werte"
INAME = "HAV"
KEY = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+(?:\.[a-z0-9_]+)?")


def _caption(root):
    lives = [el for el in root.iter("C") if el.get("Type") == "LoxLIVE"]
    gateway = [live for live in lives if any(el.get("Type") == "Gateway" for el in live.iter("C"))]
    if gateway:
        scope = gateway[0]
    elif len(lives) > 1:
        return None, None  # a client partial: nothing to do
    else:
        scope = lives[0] if lives else root
    captions = [el for el in scope.iter("C") if el.get("Type") == "VirtualInCaption"]
    if len(captions) != 1:
        raise ValueError("Ambiguous or missing VirtualInCaption")
    programs = [el for el in root.iter("C") if el.get("Type") == "Program"
                and (not lives or el.get("Ref") == scope.get("U") or scope is root)]
    if len(programs) != 1:
        raise ValueError("Ambiguous or missing Program")
    return captions[0], programs[0].get("V")


def patch_ha_values(xml: bytes, entries, port: int = PORT):
    root = ET.fromstring(xml)
    documents = [el for el in root.iter("C") if el.get("Type") == "Document"]
    if len(documents) != 1:
        raise ValueError("Expected one Document")
    doc_id = documents[0].get("U", "")
    report = {"ha_values": 0, "ha_values_changed": False}
    caption, version = _caption(root)
    if caption is None:
        return xml, report

    def uid(label):
        value = uuid.uuid5(uuid.NAMESPACE_URL, doc_id + "/smartmacherei/havalues/" + label).hex
        return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{doc_id[-16:]}"

    wanted = sorted(entries, key=lambda e: e["key"])
    for entry in wanted:
        if not KEY.fullmatch(entry["key"]):
            raise ValueError("Unsupported HA value key")
    input_id = uid("input")
    objects = list(root.iter("C"))
    existing = next((el for el in objects if el.get("U") == input_id), None)
    if existing is not None and (existing.get("Type") != "VirtualUdpIn" or existing.get("IName") != INAME):
        raise ValueError("Managed object was modified; refusing to overwrite it")
    owned = set(existing.iter()) if existing is not None else set()
    for el in objects:
        if el in owned:
            continue
        if el.get("Type") == "VirtualUdpIn" and el.get("Port") == str(port):
            raise coded_error("HA_VALUES_PORT_IN_USE", "UDP port for HA values is used by another virtual input", ValueError)
        if (el.get("IName") or "").startswith(INAME):
            raise ValueError("Foreign object uses the HA values short name")
    desired = {(uid(e["key"]), e["key"] + "=\\v") for e in wanted}
    report["ha_values"] = len(wanted)
    if existing is not None:
        current = {(c.get("U"), c.get("Check")) for c in existing.findall("C")}
        if existing.get("Port") == str(port) and current == desired:
            return xml, report
    elif not wanted:
        return xml, report
    titles = {c.get("U"): c.get("Title") for c in existing.findall("C")} if existing is not None else {}
    block = ET.Element("C", Type="VirtualUdpIn", IName=INAME, V=version, U=input_id, Title=TITLE,
                       WF="16384", Address="", Port=str(port))
    for index, entry in enumerate(wanted, 1):
        key = entry["key"]
        cmd = ET.SubElement(block, "C", Type="VirtualUdpInCmd", IName=f"{INAME}{index}", V=version, U=uid(key),
                            Title=titles.get(uid(key)) or entry["title"], Cl="238,238,238", Nio="2", WF="16400",
                            Check=key + "=\\v", Signed="true", SourceValHigh="100", DestValHigh="100",
                            MinVal="-1000000000", MaxVal="1000000000", MinChange="0", MinTime="0")
        tail = uuid.uuid5(uuid.NAMESPACE_URL, doc_id + key).hex[-12:]
        ET.SubElement(cmd, "Co", K="AQ", U=uid(key + "/AQ")[:19] + "00ff" + tail)
        ET.SubElement(cmd, "Co", K="Q", U=uid(key + "/Q")[:19] + "01ff" + tail)
        ET.SubElement(cmd, "Display", Type="1", Unit="<v>" if entry.get("digital") else "<v.2>", StateOnly="true")
    text = xml.decode("utf-8")
    if existing is not None:
        start, end = _span(text, input_id)
        text = text[:start] + text[end:]
    if wanted:
        text = _append(text, caption.get("U"), ET.tostring(block, encoding="unicode"))
    report["ha_values_changed"] = True
    return stamp_document(text, doc_id), report
```
  REASONS-Eintrag: `"HA_VALUES_PORT_IN_USE": ("Der UDP-Port 55556 für HA-Werte wird im Programm bereits von einem anderen virtuellen UDP-Eingang benutzt.", "UDP port 55556 for HA values is already used by another virtual UDP input in the program.")`.
- [ ] Step 4: Tests grün, Commit „HA-Werte als virtueller UDP-Eingang im Programm“.

### Task 3: `prepare`/`install`/`UdpSetup` reichen die Wunschliste durch

**Files:**
- Modify: `custom_components/loxone/udp_program.py` (`prepare`), `udp_install.py` (`install`, `_install`), `udp_setup.py` (`__init__`, `check`)
- Test: `tests/test_ha_values_program.py` (prepare mit Verbund-Archiv), `tests/test_udp_diagnostics.py` (force)

**Interfaces:**
- `prepare(raw, target, selected, gateway=False, ha_values=None)`; `install(client, directory, udp_port, select, stop, progress=None, gateway=False, ha_values=None)`; `UdpSetup.ha_values` (Liste oder `None`), `UdpSetup.configured_callbacks: list[callable]`, `UdpSetup.check(force=False)`.

- [ ] Step 1: Tests: `prepare(archive(), TARGET, set(), gateway=True, ha_values=[...])` → Projekt und `sps0.LoxCC` enthalten den Block mit identischen UUIDs, `sps1.LoxCC` unverändert, Report `ha_values == 2`. `UdpSetup.check(force=True)` lädt trotz unverändertem Listing (Fixture wie `test_unchanged_program_listing_skips_download`).
- [ ] Step 2: rot. Step 3: Implementierung; im `_install` fließt die Liste in den Attempt-Digest: `attempt = digest(original + target.encode() + json.dumps(sorted(e["key"] for e in ha_values or []), separators=(",", ":")).encode())`. In `check()` nach `configured`: `for callback in self.configured_callbacks: callback()`.
- [ ] Step 4: grün, Commit „Wunschliste bis in die Programmänderung durchgereicht“.

### Task 4: Wertregeln `ha_values.py` (HA-frei)

**Files:**
- Create: `custom_components/loxone/ha_values.py` (oberer Teil ohne HA-Import)
- Test: `tests/test_ha_values.py`

**Interfaces:**
- `entries_for(entity_id: str, state, language: str = "de") -> list[dict] | None` — `state` hat `.state` und `.attributes` oder ist `None`; Eintrag `{"key", "entity_id", "attribute", "title", "digital"}`; `None` = nicht exportierbar.
- `value_of(entry: dict, state) -> float | None`; `format_number(value: float) -> str`; `program_entries(entries) -> list[dict]` (`key`, `title`, `digital`).

- [ ] Step 1: Tests mit `SimpleNamespace(state=..., attributes={...})`: Zahl, on/off digital, options-Index, climate vier Einträge und Werte (Modus-Index, hvac_action-Index, Temperaturen), unknown → `None`, Text ohne options → `entries_for` gibt `None`, `format_number(23.0) == "23"`, `format_number(1000000.5) == "1000000.5"`, Titel de/en.
- [ ] Step 2: rot. Step 3: Implementierung nach Spec-Tabelle (`BOOL`, `ACTIONS`, `LABELS`).
- [ ] Step 4: grün, Commit „Wertregeln HA nach Loxone“.

### Task 5: Sender, Store, Knopf, Sensor, Verdrahtung

**Files:**
- Modify: `custom_components/loxone/ha_values.py` (HA-Teil: `desired`, `HaValuesSender`, `async_load`, `async_apply`), `button.py`, `sensor.py`, `__init__.py` (Setup nach Manager, Unload), `translations/de.json`, `translations/en.json`
- Test: HA-Container (`tests/test_ha_values_ha.py`, überspringt ohne HA)

**Interfaces:**
- `async_load(hass, entry) -> list[dict]` (Store lesen), `desired(hass, limit, language) -> tuple[list, list, list]` (entries, unsupported entity_ids, beyond_limit keys), `async_apply(hass, entry)` (Knopf), `HaValuesSender(hass, entries, host, port)` mit `start()`, `send_all()`, `stop()`; `hass.data[DOMAIN + "_ha_values"][entry_id] = {"entries": [...], "sender": HaValuesSender | None}`.

- [ ] Step 1: Implementierung wie in der Spec; Knopf `HaValuesApplyButton` (`translation_key` `ha_values_apply`, Icon `mdi:upload-network`), Sensor `HaValuesSensor` (`translation_key` `ha_values`, Icon `mdi:export`, Diagnose, `should_poll`).
- [ ] Step 2: Übersetzungen: de „HA-Werte ins Programm übernehmen“ / „HA → Loxone“, en „Apply HA values to program“ / „HA → Loxone“.
- [ ] Step 3: Offline-Suite grün, Container-Lauf wenn erreichbar. Commit „Knopf, Sensor und Sender für HA nach Loxone“.

### Task 6: Doku

**Files:**
- Modify: `README.md`, `README.de.md` (Abschnitt Weg 3), `CHANGELOG.md` (Unveröffentlicht), `docs/udp-setup-diagnostics.md` (Fehlercode)

- [ ] Step 1: Bedienung aus der Spec in 6-8 Zeilen je Sprache; Fehlercode in die Tabelle. Commit „Doku Weg 3“.
