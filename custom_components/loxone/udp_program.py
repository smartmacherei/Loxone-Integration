"""Conservative, offline UDP program transformation and verified backups.

The OutputRefLM layout follows smartmacherei's ha_udp_logger.py, verified with
Loxone Config 17.1/17.2. Original XML outside owned objects is kept verbatim.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import uuid
import xml.etree.ElementTree as ET
import zipfile
import zlib

from .udp_errors import coded_error, mark

TITLE = "HA UDP"
# Pages and loggers written by releases up to 1.6.2 keep working untouched.
LEGACY_TITLES = {"HA UDP (smartmacherei)"}
MAX_SIZE = 64 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(data: bytes) -> bytes:
    """Validate header, bounded LZ4 block, exact size and CRC before editing."""
    if len(data) < 16:
        raise ValueError("Truncated LoxCC header")
    magic, size, length, crc = struct.unpack("<4I", data[:16])
    if magic != 0xAABBCCEE or size != len(data) - 16 or not 0 < length <= MAX_SIZE:
        raise ValueError("Unsupported LoxCC header")
    src, out, i = data[16:], bytearray(), 0
    while i < len(src):
        token = src[i]
        i += 1
        literal = token >> 4
        if literal == 15:
            while True:
                b = src[i]
                i += 1
                literal += b
                if b != 255:
                    break
        if i + literal > len(src) or len(out) + literal > length:
            raise ValueError("Invalid LZ4 literal")
        out.extend(src[i:i + literal])
        i += literal
        if i == len(src):
            break
        offset = int.from_bytes(src[i:i + 2], "little")
        i += 2
        if not 0 < offset <= len(out):
            raise ValueError("Invalid LZ4 offset")
        count = (token & 15) + 4
        if token & 15 == 15:
            while True:
                b = src[i]
                i += 1
                count += b
                if b != 255:
                    break
        if len(out) + count > length:
            raise ValueError("Invalid LZ4 match")
        for _ in range(count):
            out.append(out[-offset])
    if len(out) != length or zlib.crc32(out) & 0xFFFFFFFF != crc:
        raise ValueError("LoxCC checksum mismatch")
    return bytes(out)


def encode(xml: bytes) -> bytes:
    """A valid LZ4 literal block; the surrounding ZIP provides compression."""
    n = len(xml)
    block = bytearray([min(n, 15) << 4])
    if n >= 15:
        remaining = n - 15
        while remaining >= 255:
            block.append(255)
            remaining -= 255
        block.append(remaining)
    block.extend(xml)
    return struct.pack("<4I", 0xAABBCCEE, len(block), n, zlib.crc32(xml) & 0xFFFFFFFF) + block


PROJECT = "sps.Loxone"


def unpack(raw: bytes, gateway: bool = False) -> tuple[str, bytes]:
    """Require a complete, intact program ZIP, never assemble from older files.

    A Gateway/Client archive holds one program per Miniserver plus the full
    project ``sps.Loxone``. It is accepted only with ``gateway`` (the beta
    option); the returned XML is then the full project.
    """
    mark("archive_check")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise coded_error("ARCHIVE_INVALID_ZIP", "Invalid program ZIP", ValueError) from None
    with archive:
        names = archive.namelist()
        members = sorted(n for n in names if re.fullmatch(r"sps\d*\.LoxCC", n, re.I))
        required = {"LoxAPP3.json", "permissions.bin", "Emergency.LoxCC", "Music.json"}
        def reject(code, message):
            error = coded_error(code, message, ValueError)
            error.archive_details = {"entry_count": len(names), "program_file_count": len(members),
                "missing_required_files": sorted((required | ({PROJECT} if len(members) > 1 else set())) - set(names))}
            raise error
        if len(names) != len(set(names)):
            reject("ARCHIVE_DUPLICATE_ENTRIES", "Ambiguous program ZIP: duplicate entries")
        if not members:
            reject("ARCHIVE_PROGRAM_MISSING", "Ambiguous program ZIP: missing program file")
        if len(members) > 1 and not gateway:
            reject("ARCHIVE_MULTIPLE_PROGRAMS", "Ambiguous program ZIP: multiple program files")
        if len(members) > 1 and PROJECT not in names:
            reject("ARCHIVE_PROJECT_MISSING", "Gateway archive without full project")
        if not required <= set(names):
            reject("ARCHIVE_REQUIRED_FILES_MISSING", "Incomplete program ZIP; save the project with Loxone Config first")
        if sum(info.file_size for info in archive.infolist()) > MAX_SIZE:
            reject("ARCHIVE_SIZE_LIMIT", "Program ZIP exceeds size limit")
        if archive.testzip():
            reject("ARCHIVE_CHECKSUM_MISMATCH", "Program ZIP checksum mismatch")
        mark("program_format")
        if len(members) == 1:
            xml = decode(archive.read(members[0]))
            ET.fromstring(xml)
            return members[0], xml
        for member in members:
            ET.fromstring(decode(archive.read(member)))
        project = archive.read(PROJECT)
        ET.fromstring(project)
        return PROJECT, project


def program_members(raw: bytes) -> dict[str, bytes]:
    """Decoded XML of every program file in the archive, keyed by member name."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: decode(archive.read(name)) for name in sorted(archive.namelist())
                if re.fullmatch(r"sps\d*\.LoxCC", name, re.I)}


def newest_archive(listing: str) -> str:
    files = re.findall(r"\b(sps_\d+_(\d+)\.(zip|LoxCC))\s*$", listing, re.M)
    if not files:
        raise ValueError("No current program archive")
    newest = max(timestamp for _, timestamp, _ in files)
    archives = [name for name, timestamp, ext in files if timestamp == newest and ext == "zip"]
    if len(archives) != 1:
        raise ValueError("Latest program has no complete ZIP; save with Loxone Config first")
    return archives[0]


def _span(text: str, object_id: str) -> tuple[int, int]:
    for match in re.finditer(r"<C\b[^>]*>", text):
        if re.search(r'\bU="' + re.escape(object_id) + '"', match.group()):
            if match.group().endswith("/>"):
                return match.start(), match.end()
            depth = 1
            for tag in re.finditer(r"</?C\b[^>]*>", text[match.end():]):
                value = tag.group()
                depth += -1 if value.startswith("</") else (0 if value.endswith("/>") else 1)
                if depth == 0:
                    return match.start(), match.end() + tag.end()
    raise ValueError("Cannot locate program object")


def _append(text: str, object_id: str, fragment: str) -> str:
    start, end = _span(text, object_id)
    if text[end - 2:end] == "/>":
        return text[:end - 2] + ">\n" + fragment + "\n</C>" + text[end:]
    close = text.rfind("</C>", start, end)
    return text[:close] + fragment + "\n" + text[close:]


def patch_xml(xml: bytes, target: str, selected: set[str], gateway: bool = False) -> tuple[bytes, dict]:
    """Add missing references; only replace deterministic, integration-owned objects.

    ``gateway``: the XML is a Gateway/Client full project or one of its partial
    programs. Every Program object then gets its own logger and page, limited to
    terminals of the Miniserver it runs on (``Program/@Ref`` -> ``LoxLIVE``);
    object identities include the Program UUID so project and partials agree.
    """
    mark("program_prepare")
    try:
        from .signal_bindings import SignalBindings
    except ImportError:  # Standalone offline tools load this module without HA.
        import importlib.util
        spec = importlib.util.spec_from_file_location("loxone_signal_bindings", Path(__file__).with_name("signal_bindings.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        SignalBindings = module.SignalBindings
    mark("program_format")
    root = ET.fromstring(xml)
    # Config writes a foreign terminal that is used on several pages of a
    # partial program as one Memory proxy per page, all carrying the terminal's
    # UUID. Only that duplicate is tolerated, and only on the gateway path.
    proxies = set()
    if gateway:
        from collections import Counter
        counts = Counter(e.get("U").lower() for e in root.iter() if e.tag in {"C", "Co"} and e.get("U"))
        for value, n in counts.items():
            if n < 2:
                continue
            copies = [e for e in root.iter("C") if e.get("U", "").lower() == value]
            if len(copies) != n or any(e.get("Type") != "Memory" or e.get("Tp") is None for e in copies):
                raise ValueError("Duplicate UUID in source program")
            proxies.add(value)
    bindings = SignalBindings(xml, proxies=proxies)
    documents = [el for el in root.iter("C") if el.get("Type") == "Document"]
    if len(documents) != 1:
        raise ValueError("Expected one Document")
    document = documents[0]
    doc_id = document.get("U", "")
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{16}", doc_id):
        raise ValueError("Unsupported Document UUID")
    programs = [el for el in root.iter("C") if el.get("Type") == "Program"]
    # Format 174 (older Config) is only admitted on the gateway beta path.
    allowed = {"175", "178"} | ({"174"} if gateway else set())
    if gateway:
        scopes = programs
        unsupported = not scopes or any(p.get("V") not in allowed or not p.get("Ref") for p in scopes)
    else:
        scopes = programs
        unsupported = len(programs) != 1 or programs[0].get("V") not in allowed
    if unsupported:
        raise coded_error("PROGRAM_FORMAT_UNSUPPORTED", "Program format has not been validated for automatic editing", ValueError)

    mark("program_prepare")
    objects = list(root.iter("C"))
    lives = {el.get("U"): el for el in objects if el.get("Type") == "LoxLIVE" and el.get("U")}
    owner = {}
    for live_u, live in lives.items():
        for el in live.iter("C"):
            if el.get("U"):
                owner[el.get("U").lower()] = live_u

    def make_uid(program_u):
        def uid(label):
            scope = f"{program_u}/" if gateway else ""
            value = uuid.uuid5(uuid.NAMESPACE_URL, doc_id + "/smartmacherei/udp/" + scope + label).hex
            return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{doc_id[-16:]}"
        return uid

    scope_ids = {}
    for program in scopes:
        uid = make_uid(program.get("U"))
        scope_ids[program] = (uid, uid("page"), uid("logger"))
    managed_pages = {page_id for _, page_id, _ in scope_ids.values()}
    managed_children = set()
    for el in objects:
        if el.get("U") in managed_pages:
            managed_children |= set(el.iter())
    loggers = {el.get("U"): el.get("Address") for el in objects if el.get("Type") == "Logger"}
    # An existing manually configured logger is usable if its destination matches.
    # Broadcast loggers also work on the local segment.
    port = target.rsplit("/", 1)[1]
    addresses = {target, f"/dev/udp/255.255.255.255/{port}"}
    selected = {value.lower() for value in selected}
    # Reuse Config's existing system-second output as a one-second heartbeat.
    # No guessed function-block template or visualization change is necessary.
    # In a Gateway/Client project every Miniserver runs that same object and
    # sends it from its own address, which is what the receiver keys on.
    heartbeat = next((el for el in objects if el.get("Type") == "Second"
                      and el.find("Co[@K='Q']") is not None), None)
    text = xml.decode("utf-8")
    report = {"selected": len(selected), "managed": 0, "unsupported": 0, "heartbeat": heartbeat is not None,
              "scopes": {}}
    changed = False

    for program in scopes:
        version = program.get("V")
        live_u = program.get("Ref") if gateway else None
        uid, page_id, logger_id = scope_ids[program]
        owned = {page_id: "Page", logger_id: "Logger"}
        for el in objects:
            if el.get("U") in owned and (el.get("Type") != owned[el.get("U")]
                                         or (el.get("Title") != TITLE and el.get("Title") not in LEGACY_TITLES)):
                raise ValueError("Managed object was modified; refusing to overwrite it")
        owned_page = next((el for el in objects if el.get("U") == page_id), None)
        existing = set()
        for el in objects:
            if el in managed_children or el.get("Type") != "OutputRefLM":
                continue
            lm, source = el.find("LoggerMailer"), el.find("Co[@K='AI']/In")
            if lm is None or source is None:
                continue
            if lm.get("RefLogger") == logger_id:
                raise ValueError("External reference to managed logger")
            if loggers.get(lm.get("RefLogger")) in addresses and lm.get("MinimumTime", "0") == "0":
                existing.add((lm.get("On"), lm.get("Off"), source.get("Input")))

        terminals, skipped, scoped = [], [], set()
        for el in objects:
            terminal = el.get("U", "")
            is_heartbeat = el is heartbeat
            if terminal.lower() not in selected and not is_heartbeat:
                continue
            if gateway and not is_heartbeat and owner.get(terminal.lower()) != live_u:
                continue
            if not is_heartbeat:
                scoped.add(terminal.lower())
            display = el.find("Display")
            unit = "<v>" if is_heartbeat or el.get("Type") == "ModbusSensor" else display.get("Unit", "") if display is not None else ""
            if not re.fullmatch(r"<v(?:\.\d+)?>.*", unit):
                skipped.append(terminal)
                continue
            connectors = {co.get("K"): co for co in el.findall("Co")}
            precision_match = re.match(r"<v\.(\d+)>", unit)
            analog = ("AQ" in connectors or precision_match is not None
                      or unit != "<v>" or el.get("Type") in {"TreeAactor", "LoxAIRAactor"})
            source = bindings.source(terminal)
            if not source:
                skipped.append(terminal)
                continue
            precision = min(12, max(2, int(precision_match[1]) if precision_match else 2))
            # Gateway/Client: every Miniserver runs the same Second object, so
            # its heartbeat is sent under the Miniserver (LoxLIVE) UUID instead.
            key = live_u if gateway and is_heartbeat else terminal
            message = key + (f";<v.{precision}>" if analog else ";<v>")
            if (message, message, source) not in existing:
                terminals.append((key, el.get("Title") or el.get("IName") or terminal, source, analog, message))
        report["scopes"][program.get("U")] = sorted(scoped)

        page = ET.Element("C", Type="Page", V=version, U=page_id, Title=TITLE, WF="16384")
        logger = ET.Element("C", Type="Logger", V=version, U=logger_id, Title=TITLE,
                            WF="16384", Address=target, MailSubjText="")
        for i, (terminal, title, source, analog, message) in enumerate(terminals):
            attrs = dict(Type="OutputRefLM", V=version, U=uid(terminal), Title=title,
                         Px=str(1344 + i % 4 * 2688), Py=str(576 + i // 4 * 384),
                         Px2=str(3456 + i % 4 * 2688), Py2=str(768 + i // 4 * 384),
                         Cl="0,0,0", Nio="2", Ref=logger_id, WF="147456")
            if analog:
                attrs["Analog"] = "true"
            ref = ET.SubElement(page, "C", attrs)
            tail = uuid.uuid5(uuid.NAMESPACE_URL, doc_id + terminal).hex[-12:]
            inp = uid(terminal + "/AI")[:19] + "00ff" + tail
            out = uid(terminal + "/AQ")[:19] + "01ff" + tail
            co = ET.SubElement(ref, "Co", K="AI", Nc="1", U=inp)
            ET.SubElement(co, "In", Input=source)
            ET.SubElement(ref, "Co", K="AQ", U=out)
            ET.SubElement(ref, "LoggerMailer", RefLogger=logger_id, On=message, Off=message)

        def canonical(el, uid=uid, logger_id=logger_id):
            if el is None:
                return None
            # Config may rewrite flags and placement; compare only functional fields.
            if el.get("Type") == "Logger":
                return el.get("Address")
            refs = []
            for ref in el.findall("C"):
                lm, co = ref.find("LoggerMailer"), ref.find("Co[@K='AI']/In")
                if ref.get("Type") != "OutputRefLM" or lm is None:
                    raise ValueError("Unmanaged content on the managed UDP page")
                if co is None:
                    # Config disconnects logger inputs when their source device is
                    # deleted. Only discard references provably generated by us for
                    # a terminal that no longer exists; user content stays protected.
                    message = lm.get("On", "")
                    match = re.fullmatch(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{16});<v(?:\.\d+)?>", message)
                    if (match is None or lm.get("Off") != message
                            or ref.get("U") != uid(match[1])
                            or ref.get("Ref") != logger_id
                            or lm.get("RefLogger") != logger_id
                            or ref.find("Co[@K='AI']") is None
                            or any(obj.get("U", "").lower() == match[1] for obj in objects)
                            or any(child.tag not in {"Co", "LoggerMailer"} for child in ref)
                            or len(list(ref.iter("C"))) != 1):
                        raise ValueError("Unmanaged content on the managed UDP page")
                    refs.append((ref.get("U"), "disconnected"))
                    continue
                refs.append((ref.get("U"), ref.get("Ref"), ref.get("Analog", "false"),
                             lm.get("RefLogger"), lm.get("On"), lm.get("Off"),
                             lm.get("MinimumTime", "0"), co.get("Input")))
            return sorted(refs)

        old_logger = next((el for el in objects if el.get("U") == logger_id), None)
        report["managed"] += len(terminals)
        report["unsupported"] += len(skipped)
        if (not terminals and owned_page is None and old_logger is None) or (
            canonical(owned_page) == canonical(page) and canonical(old_logger) == canonical(logger)
        ):
            continue
        if owned_page is not None:
            canonical(owned_page)  # Refuse to remove user-added function blocks.
        for object_id in owned:
            if any(el.get("U") == object_id for el in objects):
                start, end = _span(text, object_id)
                text = text[:start] + text[end:]
        if terminals:
            if gateway:
                live = lives.get(live_u)
                caption = next((el for el in live.iter("C") if el.get("Type") == "LoggerOutCaption"), None) if live is not None else None
                parents = {"LoggerOutCaption": caption, "Program": program}
            else:
                found = {type_: [el for el in objects if el.get("Type") == type_] for type_ in ("LoggerOutCaption", "Program")}
                parents = {type_: (items[0] if len(items) == 1 else None) for type_, items in found.items()}
            for type_, fragment in (("LoggerOutCaption", logger), ("Program", page)):
                parent = parents[type_]
                if parent is None or not parent.get("U"):
                    raise ValueError("Ambiguous or missing " + type_)
                text = _append(text, parent.get("U"), ET.tostring(fragment, encoding="unicode"))
        changed = True

    if not changed:
        return xml, report
    return stamp_document(text, doc_id, proxies), report


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
    # U is also a boolean setting on e.g. MO/AF/FS elements. Only object,
    # connector and UUID-valued attributes belong to the identity namespace.
    ids = [el.get("U").lower() for el in ET.fromstring(result).iter()
           if el.get("U") and (el.tag in {"C", "Co"} or re.fullmatch(
               r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{16}", el.get("U")))]
    if len(ids) != len(set(ids)) and {value for value in ids if ids.count(value) > 1} - set(proxies):
        raise ValueError("Duplicate UUID in patched program")
    return result


def _stamp_date(xml: bytes, date: str, date_s: str) -> bytes:
    """Set Date/DateS on the Document only; objects and NumO stay untouched."""
    match = re.search(rb'<C\b[^>]*\bType="Document"[^>]*>', xml)
    if match is None:
        raise ValueError("Missing Document")
    tag = match.group()
    for key, value in ((b"Date", date), (b"DateS", date_s)):
        tag, count = re.subn(rb'\b' + key + rb'="[^"]*"', key + b'="' + value.encode() + b'"', tag)
        if count != 1:
            raise ValueError("Missing Document attribute " + key.decode())
    return xml[:match.start()] + tag + xml[match.end():]


def _stamp_structure(content: bytes, date: str) -> bytes:
    content, count = re.subn(rb'("lastModified"\s*:\s*")[^"]*"',
        lambda m: m.group(1) + date.encode() + b'"', content, count=1)
    if count != 1:
        raise ValueError("Missing LoxAPP3 lastModified")
    json.loads(content)
    return content


def prepare(raw: bytes, target: str, selected: set[str], gateway: bool = False, ha_values=None) -> tuple[bytes, dict]:
    """``ha_values``: wish list for the HA -> Loxone input (Weg 3); ``None`` leaves it alone."""
    from .ha_values_program import patch_ha_values

    def with_ha_values(patched, report):
        if ha_values is None:
            return patched
        patched, extra = patch_ha_values(patched, ha_values)
        report.update(extra)
        return patched

    member, xml = unpack(raw, gateway)
    if member != PROJECT:
        updated, report = patch_xml(xml, target, selected)
        updated = with_ha_values(updated, report)
        parts = {}
    else:
        # Gateway/Client: the full project decides which terminals belong to which
        # Miniserver; every partial program then gets the same deterministic
        # objects, so Config and the Miniservers agree.
        updated, report = patch_xml(xml, target, selected, gateway=True)
        updated = with_ha_values(updated, report)
        parts = {}
        members = program_members(raw)
        for name, partial in members.items():
            programs = [el.get("U") for el in ET.fromstring(partial).iter("C") if el.get("Type") == "Program"]
            if len(programs) != 1 or programs[0] not in report["scopes"]:
                raise ValueError("Partial program " + name + " does not match the project")
            patched, _ = patch_xml(partial, target, set(report["scopes"][programs[0]]), gateway=True)
            patched = with_ha_values(patched, {})
            if patched != partial:
                parts[name] = patched
    if updated == xml and not parts:
        return raw, report
    if member == PROJECT:
        # Like Config: one Date/DateS for the project and every partial program,
        # also the unchanged ones. The gateway reports a client whose program date
        # differs from its own as running an outdated program.
        moment = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        date = moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        date_s = str(int((moment - dt.datetime(2009, 1, 1, tzinfo=dt.timezone.utc)).total_seconds()))
        updated = _stamp_date(updated, date, date_s)
        parts = {name: _stamp_date(parts.get(name, partial), date, date_s) for name, partial in members.items()}
    stamped = updated if updated != xml else next(iter(parts.values()))
    document = next(el for el in ET.fromstring(stamped).iter("C") if el.get("Type") == "Document")
    date = document.get("Date")
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as output:
        output.comment = original.comment
        for info in original.infolist():
            content = original.read(info.filename)
            if info.filename == member and updated != xml:
                content = updated if member == PROJECT else encode(updated)
            elif info.filename in parts:
                content = encode(parts[info.filename])
            elif info.filename == "LoxAPP3.json":
                content = _stamp_structure(content, date)
            elif member == PROJECT and re.fullmatch(r"LoxAPP3_\d+\.LoxCC", info.filename, re.I):
                content = encode(_stamp_structure(decode(content), date))
            output.writestr(info, content)
    result = buf.getvalue()
    unpack(result, gateway)
    mark("program_prepare")
    return result, report


def backup(directory: str, source: str, raw: bytes, gateway: bool = False) -> str:
    """Durably save and read back the FULL original archive before any upload.

    Content-addressed filenames never overwrite another project version. Backups
    contain credentials and are deliberately outside the web-accessible www path.
    For a Gateway/Client archive the openable project is the full ``sps.Loxone``.
    """
    _, xml = unpack(raw, gateway)
    mark("backup_write")
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    checksum = digest(raw)
    path = folder / (checksum + ".zip")
    if not path.exists():
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    mark("backup_verify")
    if digest(path.read_bytes()) != checksum:
        raise coded_error("BACKUP_CHECKSUM_MISMATCH", "Backup read-back checksum mismatch; upload blocked")
    # A customer can open this directly in Loxone Config even if HA no longer runs.
    project = path.with_suffix(".Loxone")
    project_data = b"\xef\xbb\xbf" + xml.removeprefix(b"\xef\xbb\xbf")
    mark("backup_write")
    if not project.exists():
        with project.open("xb") as handle:
            os.chmod(project, 0o600)
            handle.write(project_data)
            handle.flush()
            os.fsync(handle.fileno())
    mark("backup_verify")
    if project.read_bytes() != project_data:
        raise coded_error("BACKUP_CHECKSUM_MISMATCH", "Loxone Config project backup verification failed; upload blocked")
    mark("backup_write")
    instructions = folder / "RESTORE.txt"
    if not instructions.exists():
        with instructions.open("x", encoding="utf-8") as handle:
            handle.write(
                "LOXONE PROJECT BACKUP / LOXONE-PROJEKTSICHERUNG\n\n"
                "EN: Disable automatic UDP setup in Home Assistant or stop HA first.\n"
                "Copy the .Loxone file to your computer. Open it in Loxone Config,\n"
                "connect to the correct Miniserver and use Save in Miniserver.\n"
                "This replaces the running program and briefly interrupts its logic.\n"
                "The matching .zip is the complete original Miniserver archive;\n"
                "the .json records its SHA-256, source filename and backup time.\n"
                "If HA is unavailable, use a previously downloaded copy or recover\n"
                "this folder from an HA backup. Keep a copy outside the HA server.\n\n"
                "DE: Zuerst automatische UDP-Einrichtung deaktivieren oder HA stoppen.\n"
                ".Loxone-Datei auf den PC kopieren und in Loxone Config öffnen.\n"
                "Mit dem richtigen Miniserver verbinden und In Miniserver speichern.\n"
                "Dies ersetzt das laufende Programm und unterbricht kurz die Logik.\n"
                "Die zugehörige ZIP-Datei enthält das vollständige Originalpaket;\n"
                "die JSON-Datei Prüfsumme, Quelldateiname und Sicherungszeit.\n"
                "Bei ausgefallenem HA eine vorher heruntergeladene Kopie nutzen\n"
                "oder diesen Ordner aus einer HA-Sicherung wiederherstellen.\n"
                "Eine zusätzliche Kopie außerhalb des HA-Servers aufbewahren.\n\n"
                "These files contain credentials. Do not publish them.\n"
                "Diese Dateien enthalten Zugangsdaten. Nicht veröffentlichen.\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
    metadata = path.with_suffix(".json")
    if not metadata.exists():
        with metadata.open("x", encoding="utf-8") as handle:
            os.chmod(metadata, 0o600)
            json.dump({"source": source, "sha256": checksum, "bytes": len(raw),
                       "created_utc": dt.datetime.now(dt.timezone.utc).isoformat()}, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
    mark("backup_verify")
    saved = json.loads(metadata.read_text(encoding="utf-8"))
    if saved.get("sha256") != checksum or saved.get("bytes") != len(raw):
        raise coded_error("BACKUP_CHECKSUM_MISMATCH", "Backup metadata verification failed; upload blocked")
    if os.name != "nt":
        descriptor = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return str(path)
