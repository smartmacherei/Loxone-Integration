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
_DEVICE_TYPES = {"TreeDevice", "LoxAIRDevice", "LoxLIVE"}
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


def _loxcc_from_zip(data: bytes) -> bytes | None:
    """sps0.LoxCC aus einem sps_*.zip-Programmpaket holen."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".loxcc") and name.lower().startswith("sps"):
                    return zf.read(name)
        _LOGGER.warning("Kein sps*.LoxCC im Programm-ZIP")
    except Exception as err:  # noqa: BLE001 - best effort
        _LOGGER.warning("Programm-ZIP nicht lesbar: %s", err)
    return None


# --- Voll-Auto-Discovery: physische Klemmen ohne Visu-Haekchen -----------------

# Loxone-Klemmentyp (im Programm) -> (synthetischer LoxAPP3-Typ, is_analog)
# Aktoren werden bewusst nur lesend abgebildet: Ihr Zustand ist interessant,
# geschaltet wird weiterhin ueber den zustaendigen Funktionsbaustein.
_READ_TERMINALS = {
    # Tree-Geraete
    "TreeSensor": ("InfoOnlyDigital", False),
    "TreeAsensor": ("InfoOnlyAnalog", True),
    # Air-Geraete
    "LoxAIRsensor": ("InfoOnlyDigital", False),
    "LoxAIRAsensor": ("InfoOnlyAnalog", True),
    "LoxAIRactor": ("InfoOnlyDigital", False),
    "LoxAIRAactor": ("InfoOnlyAnalog", True),
    # Onboard-Klemmen des Miniservers
    "DigitalIn": ("InfoOnlyDigital", False),
    "VoltageIn": ("InfoOnlyAnalog", True),
    "Actor": ("InfoOnlyDigital", False),
    # Verbindungsstatus je Geraet/Extension
    "Online": ("InfoOnlyDigital", False),
}


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


def enumerate_discoverable(program_xml: bytes, loxconfig: dict) -> list[tuple[str, dict]]:
    """Synthetische InfoOnly-Controls fuer physische Klemmen, die (noch) NICHT in
    der Visu/loxconfig stehen. Read-only: TreeSensor->binary_sensor,
    TreeAsensor->sensor. Rueckgabe: Liste (uuid, control_dict) zur Injektion."""
    try:
        root = ET.fromstring(program_xml)
    except ET.ParseError:
        return []
    existing = {u.lower() for u in loxconfig.get("controls", {})}
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
        parsed = _parse_display_unit(
            disp.attrib.get("Unit", "") if disp is not None else ""
        )
        if parsed is None:
            continue  # unbelegte/ungueltige Klemme (z.B. '<v.i>') -> ueberspringen
        unit, precision = parsed
        lox_type, is_analog = info
        ctrl = {
            "name": el.attrib.get("Title") or el.attrib.get("IName") or u,
            "type": lox_type,
            "uuidAction": u,
            "room": iod.attrib.get("Pr", "") if iod is not None else "",
            "cat": iod.attrib.get("Cr", "") if iod is not None else "",
            "defaultRating": 0,
            "isFavorite": False,
            "isSecured": False,
            "restrictions": 0,
            "auto_discovered": True,
        }
        if is_analog:
            ctrl["details"] = {"format": _lox_format(unit, precision)}
            ctrl["states"] = {"value": u}
        else:
            ctrl["details"] = {"text": {"off": "Aus", "on": "Ein"}}
            ctrl["states"] = {"active": u}
        out.append((u, ctrl))
    return out


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
    m = re.match(r"\s*([-+]?\d+(?:[.,]\d+)?)", str(raw))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


async def async_fetch_values(session, host, port, username, password, uuids) -> dict:
    """Aktuelle Werte einzelner UUIDs per HTTP holen (/jdev/sps/io/<uuid>).

    Fallback fuer auto-entdeckte Klemmen, deren Wert der Miniserver nicht ueber
    den WebSocket-Stream pusht (z.B. Konfig-Analogwerte). Best-effort.
    """
    import aiohttp

    base = "http://{}:{}".format(host, port)
    auth = aiohttp.BasicAuth(str(username), str(password))
    timeout = aiohttp.ClientTimeout(total=8)
    out: dict = {}
    for u in uuids:
        try:
            async with session.get(base + "/jdev/sps/io/" + u, auth=auth, timeout=timeout) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json(content_type=None)
                val = data.get("LL", {}).get("value")
                if val is not None and str(val).strip() not in ("", "<v.i>"):
                    num = _numeric_value(val)
                    if num is not None:
                        out[u] = num
        except Exception:  # noqa: BLE001 - best effort
            continue
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
            data = _loxcc_from_zip(data)
            if data is None:
                return None
    except Exception as err:  # noqa: BLE001 - best effort
        _LOGGER.warning("Programm-Download fehlgeschlagen: %s", err)
        return None

    return decode_loxcc(data)
