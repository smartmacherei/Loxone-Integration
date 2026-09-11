"""Loxone Geraete-Topologie aus dem Miniserver-Programm.

Die LoxAPP3.json-Struktur (die PyLoxone normal nutzt) enthaelt KEINE Info,
welcher InfoOnly-Baustein zu welchem physischen Tree-Geraet gehoert. Diese
Zuordnung steckt nur im kompilierten Programm (sps*.LoxCC).

Dieses Modul laedt das Programm ueber die Dateisystem-API des Miniservers
(/dev/fslist, /dev/fsget), dekomprimiert das LoxCC-Format (16-Byte-Header +
LZ4-Block) und baut eine Map  control_uuid -> (device_uuid, device_name)
anhand der <C Type="TreeDevice">-Hierarchie.

Ist alles best-effort: schlaegt irgendetwas fehl, liefert build/fetch eine
leere Map und PyLoxone gruppiert wie bisher (ein Geraet pro Control).
"""
from __future__ import annotations

import io
import logging
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

_LOGGER = logging.getLogger(__name__)

LOXCC_MAGIC = 0xAABBCCEE
# physische Geraete-Container im Loxone-Programm.
# LoxLIVE = der Miniserver selbst; seine Onboard-Klemmen (DigitalIn/VoltageIn/
# Actor) haengen unter Caption-Knoten direkt darunter.
_DEVICE_TYPES = {
    "TreeDevice", "LoxAIRDevice", "LoxLIVE", "LoxTree", "LoxAIR",
    "Comm1wire", "LoxAinV2", "LoxAout", "LoxDali", "LoxDigin", "CommDMX",
    "LoxDIMM", "LoxOCEAN", "LoxMORE", "Comm232", "Comm485", "LoxInternorm",
    "LoxKnx", "MBusExtension", "LoxREL", "SchuecoExtension", "ModbusDev",
    "DaliDevice", "LoxDMXdevice", "LoxOCEANDevice", "LoxInternormDevice",
    "SchuecoDevice", "LoxIRrcvdevice", "LoxIRsnddevice",
}
# Bausteine, die zu einem Geraet gehoeren (Ein-/Ausgaenge)
_CHILD_PREFIXES = ("Tree", "LoxAIR")
# Geraetename aufhuebschen: der LoxLIVE-Title ist der Projektname ("Demo Case")
# und kollidiert sonst mit dem gleichnamigen Raum.
_DEVICE_NAME_FMT = {"LoxLIVE": "Miniserver {}"}


def _lz4_block_decompress(src: bytes, dst_size: int) -> bytes:
    """Standard-LZ4-Block-Dekompression (wie im LoxCC-Payload verwendet)."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if len(out) >= dst_size or i >= n:
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0:
            break
        mlen = (token & 0x0F) + 4
        if (token & 0x0F) == 15:
            while True:
                b = src[i]
                i += 1
                mlen += b
                if b != 255:
                    break
        start = len(out) - offset
        for j in range(mlen):
            out.append(out[start + j])
    return bytes(out)


def decode_loxcc(data: bytes) -> bytes | None:
    """LoxCC (Header + LZ4) -> rohes Programm-XML. None bei Formatfehler."""
    if len(data) < 16:
        return None
    magic, comp_size, uncomp_size, _chk = struct.unpack("<4I", data[:16])
    if magic != LOXCC_MAGIC:
        # Manche Firmwares liefern evtl. unkomprimiert/anders -> nicht raten
        _LOGGER.debug("Unerwartete LoxCC-Magic 0x%08x", magic)
        return None
    xml = _lz4_block_decompress(data[16:], uncomp_size)
    if len(xml) != uncomp_size:
        _LOGGER.debug("LoxCC-Groesse weicht ab: %s != %s", len(xml), uncomp_size)
    return xml


def build_device_map(program_xml: bytes) -> dict[str, tuple[str, str]]:
    """control_uuid(lower) -> (device_uuid, device_name) aus TreeDevice-Hierarchie."""
    result: dict[str, tuple[str, str]] = {}
    try:
        root = ET.fromstring(program_xml)
    except ET.ParseError as err:
        _LOGGER.warning("Programm-XML nicht parsebar: %s", err)
        return result

    parent = {c: p for p in root.iter() for c in p}

    def parent_device(el):
        cur = el
        while cur in parent:
            cur = parent[cur]
            if cur.tag == "C" and (dty := cur.attrib.get("Type")) in _DEVICE_TYPES:
                title = cur.attrib.get("Title", "")
                fmt = _DEVICE_NAME_FMT.get(dty)
                return cur.attrib.get("U"), (fmt.format(title) if fmt else title)
        return None, None

    for el in root.iter("C"):
        ty = el.attrib.get("Type", "")
        if (
            ty.startswith(_CHILD_PREFIXES) or ty in _READ_TERMINALS
        ) and ty not in _DEVICE_TYPES:
            du, dt = parent_device(el)
            u = el.attrib.get("U")
            if du and u:
                result[u.lower()] = (du, dt)
    return result


def _newest_program_file(listing: str) -> str | None:
    """Aus einer /dev/fslist/prog-Ausgabe das neueste Programm holen.

    Der Miniserver legt das Programm je nach Speichervorgang als nacktes
    sps_*.LoxCC ODER als sps_*.zip (mit sps0.LoxCC darin) ab. Nur auf .LoxCC zu
    schauen liefert stillschweigend ein veraltetes Programm, sobald die letzten
    Speicherungen als .zip abgelegt wurden -- neue Geraete fehlen dann komplett.
    Bei gleichem Zeitstempel gewinnt .LoxCC (spart das Entpacken).
    """
    best = None
    best_key = (-1, -1)
    for line in listing.splitlines():
        m = re.search(r"(sps_\d+_(\d+)\.(LoxCC|zip))\s*$", line.strip())
        if m:
            key = (int(m.group(2)), 1 if m.group(3) == "LoxCC" else 0)
            if key > best_key:
                best_key, best = key, m.group(1)
    return best


def program_from_zip(data: bytes) -> bytes | None:
    """Programm-XML aus einem sps_*.zip-Programmpaket.

    Einzelanlage: eine sps0.LoxCC. Gateway/Client-Verbund: je Miniserver eine
    spsN.LoxCC plus sps.Loxone, das Gesamtprojekt mit allen Miniservern. Nur das
    Gesamtprojekt kennt alle Klemmen; die erste LoxCC waere ein zufaelliger
    Miniserver. Fehlt sps.Loxone, werden die Teilprogramme zusammengefuehrt.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            full = next((n for n in names if n.lower() == "sps.loxone"), None)
            if full:
                return zf.read(full)
            parts = sorted(n for n in names if re.fullmatch(r"sps\d*\.loxcc", n.lower()))
            if not parts:
                _LOGGER.warning("Kein sps*.LoxCC im Programm-ZIP")
                return None
            programs = [decode_loxcc(zf.read(n)) for n in parts]
    except Exception as err:  # noqa: BLE001 - best effort
        _LOGGER.warning("Programm-ZIP nicht lesbar: %s", err)
        return None
    if any(p is None for p in programs):
        return None
    return programs[0] if len(programs) == 1 else _merge_programs(programs)


def _merge_programs(programs: list[bytes]) -> bytes | None:
    """Teilprogramme eines Verbunds zu einem Dokument: globale Objekte einmal,
    LoxLIVE (Miniserver samt Klemmen) und Program je Teil."""
    try:
        base = ET.fromstring(programs[0])
        document = next(el for el in base.iter("C") if el.get("Type") == "Document")
        known = {el.get("U") for el in base.iter("C") if el.get("U")}
        for raw in programs[1:]:
            other = next(el for el in ET.fromstring(raw).iter("C") if el.get("Type") == "Document")
            for child in list(other):
                if child.get("Type") in ("LoxLIVE", "Program") and child.get("U") not in known:
                    document.append(child)
                    known.update(el.get("U") for el in child.iter("C") if el.get("U"))
    except (ET.ParseError, StopIteration) as err:
        _LOGGER.warning("Teilprogramme nicht zusammenfuehrbar: %s", err)
        return None
    return ET.tostring(base, encoding="utf-8", xml_declaration=True)


def miniservers(program_xml: bytes) -> list[dict]:
    """Ein Eintrag je LoxLIVE: Rolle (single/gateway/client), Index, Adresse.

    Gateway und Clients erkennt man an den Objekten Gateway (mit SLAVE-Eintraegen
    je Client) und GatewayClient (ProgType = Index der spsN.LoxCC).
    """
    try:
        root = ET.fromstring(program_xml)
    except ET.ParseError:
        return []
    slaves = {}
    for gateway in root.iter("C"):
        if gateway.get("Type") == "Gateway":
            for slave in gateway.findall("SLAVE"):
                slaves[(slave.get("uuid") or "").lower()] = slave
    result = []
    for live in root.iter("C"):
        if live.get("Type") != "LoxLIVE":
            continue
        uuid = live.get("U", "")
        types = {el.get("Type") for el in live.iter("C")}
        slave = slaves.get(uuid.lower())
        client = next((el for el in live.iter("C") if el.get("Type") == "GatewayClient"), None)
        role, index = "single", 0
        if "Gateway" in types:
            role = "gateway"
        elif client is not None or slave is not None:
            role = "client"
            raw_index = (client.get("ProgType") if client is not None else None) or (slave.get("Type") if slave is not None else None) or "0"
            index = int(raw_index) if str(raw_index).isdigit() else 0
        host = (slave.get("IP") if slave is not None and slave.get("IP") else live.get("IntAddr", "")) or ""
        raw_port = (slave.get("Port") if slave is not None and slave.get("Port") else live.get("ExP")) or "80"
        result.append({"uuid": uuid, "name": live.get("Title", ""), "serial": live.get("Serial", ""),
                       "role": role, "index": index, "host": host,
                       "port": int(raw_port) if str(raw_port).isdigit() else 80})
    return result


def terminal_owner(program_xml: bytes) -> dict[str, str]:
    """control_uuid(lower) -> UUID des LoxLIVE (Miniserver), unter dem die Klemme haengt."""
    owner: dict[str, str] = {}
    try:
        root = ET.fromstring(program_xml)
    except ET.ParseError:
        return owner
    for live in root.iter("C"):
        if live.get("Type") == "LoxLIVE":
            for el in live.iter("C"):
                if el.get("U"):
                    owner[el.get("U").lower()] = live.get("U", "")
    return owner


def interleave_by_miniserver(found, owner: dict[str, str]) -> list:
    """Reihum über die Miniserver, innerhalb eines Miniservers in Programmreihenfolge.

    So kann eine globale Höchstzahl die Clients eines Gateway/Client-Verbunds nicht
    aushungern, wenn das Gateway allein schon mehr Klemmen hat als die Grenze.
    """
    from collections import deque
    groups: dict[str, deque] = {}
    for item in found:
        groups.setdefault(owner.get(item[0].lower(), ""), deque()).append(item)
    if len(groups) < 2:
        return list(found)
    result, queues = [], list(groups.values())
    while queues:
        for queue in list(queues):
            result.append(queue.popleft())
            if not queue:
                queues.remove(queue)
    return result


def client_hosts(program_xml: bytes, uuids) -> dict[str, tuple[str, int]]:
    """uuid -> (host, port) fuer Klemmen, die an einem Client-Miniserver haengen.

    Das Gateway kennt Werte fremder Klemmen nur, wenn sein eigenes Programm sie
    nutzt; der Client selbst liefert sie immer (gleiches Subnetz, gleiche
    Zugangsdaten). Klemmen des Gateways oder einer Einzelanlage fehlen hier und
    werden ueber die konfigurierte Adresse abgefragt.
    """
    servers = {m["uuid"].lower(): m for m in miniservers(program_xml)}
    if not any(m["role"] == "client" for m in servers.values()):
        return {}
    owner = terminal_owner(program_xml)
    hosts = {}
    for uuid in uuids:
        server = servers.get(owner.get(str(uuid).lower(), "").lower())
        if server and server["role"] == "client" and server["host"]:
            hosts[uuid] = (server["host"], server["port"])
    return hosts


# --- Voll-Auto-Discovery: physische Klemmen ohne Visu-Haekchen -----------------

# Loxone-Klemmentyp (im Programm) -> (synthetischer LoxAPP3-Typ, is_analog)
#
# Richtung zaehlt: Ein digitaler AUSGANG als InfoOnlyDigital abzubilden macht
# aus einer Klemme, die man schalten kann, einen reinen Melder -- Ausgaenge
# tauchen dann als Eingaenge auf. Digitale Ausgaenge sind am Miniserver per
# /jdev/sps/io/<uuid>/On|Off schaltbar (verifiziert), also -> "Switch".
# Analoge Ausgaenge bleiben lesend: dafuer gibt es hier keine Schreib-Semantik.
_READ_TERMINALS = {
    # --- Eingaenge / Sensoren (lesend) ---
    "TreeSensor": ("InfoOnlyDigital", False),
    "TreeAsensor": ("InfoOnlyAnalog", True),
    "LoxAIRsensor": ("InfoOnlyDigital", False),
    "LoxAIRAsensor": ("InfoOnlyAnalog", True),
    "DigitalIn": ("InfoOnlyDigital", False),
    "VoltageIn": ("InfoOnlyAnalog", True),
    # Verbindungsstatus je Geraet/Extension (lesend)
    "Online": ("InfoOnlyDigital", False),
    # --- Ausgaenge ---
    "Actor": ("Switch", False),  # Onboard-Relais/Digitalausgang des Miniservers
    "TreeActor": ("Switch", False),
    "TreeAactor": ("InfoOnlyAnalog", True),
    "LoxAIRactor": ("Switch", False),
    "LoxAIRAactor": ("InfoOnlyAnalog", True),
}

# Protocol-specific terminals expose the same numeric read endpoint. New output
# types remain read-only until their command semantics have been verified.
for _type in ("DimCurrentIn", "ModbusASensor", "LoxOCEANAsensor", "InternormAsensor",
              "SchuecoAsensor", "SysTemp", "EIBextsensor", "OneWireSensor"):
    _READ_TERMINALS[_type] = ("InfoOnlyAnalog", True)
for _type in ("DaliSensor", "LoxOCEANsensor", "ModbusSensor", "InternormSensor",
              "EIBsensor", "SchuecoSensor", "OvertempShutdown", "UndervoltShutdown"):
    _READ_TERMINALS[_type] = ("InfoOnlyDigital", False)
for _type in ("VoltageOut", "DaliActor", "DaliSwitch", "DaliGroup", "LoxDMXactor",
              "Dimmer", "LoxOCEANAactor", "LoxOCEANactor", "ModbusAActor",
              "EIBactor", "EIBextactor", "SchuecoActor", "SchuecoAactor",
              "Lox232actor", "Lox485actor", "ApiActor"):
    _READ_TERMINALS[_type] = ("InfoOnlyAnalog", True)
# Geraetediagnose ohne Gegenstueck in einem Smart-Home-Standard: Online-Status,
# Schutzabschaltungen, interne Temperaturen. Werden deaktiviert angelegt und
# damit nicht abgefragt, bis jemand sie in HA einschaltet.
_DIAGNOSTIC_TERMINALS = {"Online", "OvertempShutdown", "UndervoltShutdown", "SysTemp"}
_TEXT_TERMINALS = {"TreeTextActor", "AirTextActor", "EIBtextsensor", "EIBtextactor"}
for _type in _TEXT_TERMINALS:
    _READ_TERMINALS[_type] = ("RawTerminal", False)


def _parse_display_unit(display_unit: str):
    """'<v.1>°' -> ('°', 1);  '<v>%' -> ('%', 0);  '<v>' -> ('', 0).

    Gibt None zurueck fuer ungueltige/unbelegte Klemmen (z.B. '<v.i>' = value
    invalid) -> diese werden nicht als Entity angelegt.
    """
    m = re.fullmatch(r"<v(?:\.(\d+))?>(.*)", (display_unit or "").strip())
    if m:
        return m.group(2).strip(), (int(m.group(1)) if m.group(1) else 0)
    return None


def _lox_format(unit: str, precision: int) -> str:
    """HA/PyLoxone-Formatstring, den clean_unit versteht ('%.1f°', '%.0f%%')."""
    if unit == "%":
        return "%.{}f%%".format(precision)
    return "%.{}f{}".format(precision, unit)


def classify_terminal(
    name: str,
    unit: str,
    is_analog: bool,
    is_actor: bool,
    device_name: str = "",
) -> str | None:
    """Classify known measurements; an unknown meaning never prevents discovery.

    Device context is used for ambiguous analog units. Digital device-name
    fallback is restricted to generic inputs on water detectors.
    """
    if is_actor:
        return None
    if is_analog:
        # Der Geraetename geht als "category" hinein - genau dafuer hat
        # match_sensor_description das Feld (mehrdeutige Einheiten wie % brauchen
        # ein Schluesselwort, sonst wird jeder Prozentwert zur Luftfeuchte).
        from .sensor import match_sensor_description

        desc = match_sensor_description(unit, name, device_name)
        return str(desc.device_class) if desc and desc.device_class else None

    from .binary_sensor import device_class_from_name

    dc = device_class_from_name(name)
    # Only generic input names on a water detector justify device-name context.
    # A fire alarm/test button on a presence detector is not occupancy.
    if dc is None and re.fullmatch(r"(?:eingang|input)\s*\d+", name.lower()):
        if any(word in device_name.lower() for word in ("wassersensor", "water sensor")):
            dc = device_class_from_name("water leak")
    return str(dc) if dc else None


def enumerate_discoverable(
    program_xml: bytes, loxconfig: dict, device_map: dict | None = None
) -> list[tuple[str, dict]]:
    """Synthetische InfoOnly-Controls fuer physische Klemmen, die (noch) NICHT in
    der Visu/loxconfig stehen. Read-only: TreeSensor->binary_sensor,
    TreeAsensor->sensor. Rueckgabe: Liste (uuid, control_dict) zur Injektion.

    Bekannte Klemmentypen bleiben auch ohne device_class erhalten."""
    try:
        root = ET.fromstring(program_xml)
    except ET.ParseError:
        return []
    existing = {u.lower() for u in loxconfig.get("controls", {})}
    # Geraetename je Klemme - classify_terminal braucht ihn als Kontext. Der
    # Aufrufer hat die Map beim Setup ohnehin schon gebaut; sie durchzureichen
    # spart bei grossen Projekten ein komplettes Parsen des Programm-XML im
    # Event-Loop.
    device_names = build_device_map(program_xml) if device_map is None else device_map
    out: list[tuple[str, dict]] = []
    for el in root.iter("C"):
        info = _READ_TERMINALS.get(el.attrib.get("Type", ""))
        if not info:
            continue
        u = el.attrib.get("U")
        if not u or u.lower() in existing:
            continue  # De-Dupe: schon als Control vorhanden
        iod = el.find("IoData")
        if iod is not None and iod.attrib.get("Visu") == "true":
            continue  # schon in der Visu -> nicht doppeln
        disp = el.find("Display")
        default_unit = "<v>" if el.get("Type") == "ModbusSensor" else ""
        parsed = _parse_display_unit(
            disp.attrib.get("Unit", default_unit) if disp is not None else default_unit
        )
        raw_format = disp.get("Unit", default_unit) if disp is not None else default_unit
        raw_terminal = parsed is None
        unit, precision = parsed or ("", 0)
        lox_type, is_analog = info
        name = el.attrib.get("Title") or el.attrib.get("IName") or u
        device_name = device_names.get(u.lower(), ("", ""))[1] or ""
        # lox_type "Switch" = schreibender Ausgang -> von der Discovery
        # ausgenommen, siehe classify_terminal().
        device_class = classify_terminal(
            name, unit, is_analog, lox_type == "Switch", device_name
        )
        if raw_terminal:
            lox_type = "RawTerminal"
            device_class = None
        ctrl = {
            "name": name,
            "type": lox_type,
            "uuidAction": u,
            "room": iod.attrib.get("Pr", "") if iod is not None else "",
            "cat": iod.attrib.get("Cr", "") if iod is not None else "",
            "defaultRating": 0,
            "isFavorite": False,
            "isSecured": False,
            "restrictions": 0,
            "auto_discovered": True,
            # Bewusst NICHT "device_class": LoxoneEntity.__init__ setattr-t jeden
            # kwarg, und device_class ist an der Entity eine Property ohne Setter
            # -> das gaebe je Entity eine Fehlermeldung im Log.
            "auto_device_class": device_class,
            # Der Geraetename als Kategorie-Kontext. classify_terminal hat ihn
            # oben benutzt; die Analog-Entity klassifiziert in sensor.py selbst
            # noch einmal und wuerde ohne ihn zu einem ANDEREN Ergebnis kommen
            # (z.B. "%"-Klemme an einem Feuchtesensor: hier durchgelassen, dort
            # ohne device_class). Beide muessen dieselben Eingaben sehen.
            "auto_category": device_name,
            "auto_raw": raw_terminal,
            "auto_terminal_type": el.get("Type"),
            "auto_format": raw_format,
            # Diagnostic category for device internals and battery; internals and
            # raw formats start disabled so nobody polls what nobody asked for.
            "auto_diagnostic": el.get("Type") in _DIAGNOSTIC_TERMINALS or raw_terminal or device_class == "battery",
            "auto_enabled_default": not (el.get("Type") in _DIAGNOSTIC_TERMINALS or raw_terminal),
        }
        if is_analog and not raw_terminal:
            ctrl["details"] = {"format": _lox_format(unit, precision)}
            ctrl["states"] = {"value": u}
        else:
            ctrl["details"] = {"text": {"off": "Aus", "on": "Ein"}}
            ctrl["states"] = {"active": u}
        out.append((u, ctrl))
    return out


def pollable_terminals(uuids, registry, default_off):
    """Terminals worth an HTTP request: their entity is enabled in HA.

    ``registry`` maps unique_id -> disabled_by (None = enabled) for entities HA
    already knows; ``default_off`` holds terminals created disabled. A terminal
    unknown to the registry is polled unless it starts disabled.
    """
    return [u for u in uuids
            if ((registry[u] is None) if u in registry else (u not in default_off))]


def _numeric_value(raw):
    """'0%' -> 0.0, '0.0°' -> 0.0, '0Lx' -> 0.0, '0.0' -> 0.0. None wenn zahllos.

    Anders als der WebSocket-Stream liefert /jdev/sps/io/<uuid> den fertig
    formatierten Anzeigewert INKLUSIVE Einheit. Reicht man den ungefiltert
    weiter, wirft HA fuer numerische Sensoren einen ValueError ("non-numeric
    value") und die Entity stirbt beim ersten Schreiben -- betrifft genau die
    Klemmen mit Einheit (%, °, Lx), waehrend einheitenlose durchrutschen.
    """
    if isinstance(raw, (int, float)):
        return raw
    m = re.match(r"\s*([-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][-+]?\d+)?)", str(raw))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


async def async_fetch_values(session, host, port, username, password, uuids, raw_uuids=(), on_attempt=None, http_scales=None, hosts=None) -> dict:
    """Aktuelle Werte einzelner UUIDs per HTTP holen (/jdev/sps/io/<uuid>).

    Fallback fuer auto-entdeckte Klemmen, deren Wert der Miniserver nicht ueber
    den WebSocket-Stream pusht (z.B. Konfig-Analogwerte). Best-effort.
    ``hosts`` (uuid -> (host, port)) leitet Klemmen eines Client-Miniservers an
    dessen eigene Adresse; alle anderen gehen an host:port.
    """
    import aiohttp

    hosts = hosts or {}
    auth = aiohttp.BasicAuth(str(username), str(password))
    timeout = aiohttp.ClientTimeout(total=8)
    import asyncio
    import math
    raw_uuids = set(raw_uuids)
    out: dict = {}
    semaphore = asyncio.Semaphore(8)
    # A single Miniserver, especially Gen 1, gets at most two requests at once.
    per_host: dict = {}
    async def fetch(u):
        try:
            target_host, target_port = hosts.get(u, (host, port))
            gate = per_host.setdefault((target_host, target_port), asyncio.Semaphore(2))
            async with semaphore, gate:
                if on_attempt:
                    on_attempt(u)
                base = "http://{}:{}".format(target_host, target_port)
                async with session.get(base + "/jdev/sps/io/" + u, auth=auth, timeout=timeout) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json(content_type=None)
                ll = data.get("LL", {})
                if str(ll.get("Code", "200")) != "200":
                    return
                val = ll.get("value")
                if val is not None and str(val).strip() and not re.fullmatch(r"<v(?:\.[^>]*)?>", str(val).strip()):
                    if u in raw_uuids:
                        out[u] = str(val)
                        return
                    num = _numeric_value(val)
                    if num is not None and math.isfinite(num):
                        out[u] = num * (http_scales or {}).get(u, 1)
        except Exception:  # noqa: BLE001 - best effort
            return
    try:
        async with asyncio.timeout(30):
            await asyncio.gather(*(fetch(u) for u in uuids))
    except TimeoutError:
        _LOGGER.debug("Terminal snapshot timed out; partial results retained")
    return out


async def async_fetch_program(session, host, port, username, password) -> bytes | None:
    """Programm vom Miniserver ziehen und zu XML dekodieren. None bei Fehler."""
    import aiohttp

    base = "http://{}:{}".format(host, port)
    auth = aiohttp.BasicAuth(str(username), str(password))
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with session.get(base + "/dev/fslist/prog", auth=auth, timeout=timeout) as resp:
            if resp.status != 200:
                _LOGGER.warning("fslist/prog -> HTTP %s (Geraete-Gruppierung faellt zurueck)", resp.status)
                return None
            listing = await resp.text()
        fname = _newest_program_file(listing)
        if not fname:
            _LOGGER.warning("Kein sps_*.LoxCC/.zip in /prog gefunden")
            return None
        async with session.get(base + "/dev/fsget/prog/" + fname, auth=auth, timeout=timeout) as resp:
            if resp.status != 200:
                _LOGGER.warning("fsget %s -> HTTP %s", fname, resp.status)
                return None
            data = await resp.read()
        if fname.endswith(".zip"):
            return program_from_zip(data)
    except Exception as err:  # noqa: BLE001 - best effort
        _LOGGER.warning("Programm-Download fehlgeschlagen: %s", err)
        return None

    return decode_loxcc(data)
