"""Reconcile removed project objects without treating offline devices as deleted."""
from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile

_LOGGER = logging.getLogger(__name__)
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{16}"


def inventory(program, app):
    """Require a complete project and structure; collect IDs, including states."""
    root = ET.fromstring(program)
    for kind in ("Document", "Program", "LoxLIVE"):
        if len([el for el in root.iter("C") if el.get("Type") == kind]) != 1:
            raise ValueError("Incomplete or ambiguous project")
    if not isinstance(app.get("controls"), dict) or not app.get("msInfo", {}).get("serialNr"):
        raise ValueError("Incomplete Miniserver structure")
    result = {el.get("U", "").lower() for el in root.iter() if el.tag in {"C", "Co"}}
    # Include nested controls, subcontrols and their state UUIDs. Extra retained
    # references are harmless; missing a live reference could delete user data.
    result.update(re.findall(UUID, json.dumps(app).lower()))
    return result


def plan_cleanup(entry_id, devices, entities, active_ids, known):
    """Plan only absent UUID entities and empty, exclusively owned devices."""
    def absent(value, entity=False):
        pattern = UUID + (r"(?:/[A-Za-z0-9]+)?" if entity else "")
        value = str(value).lower()
        return re.fullmatch(pattern, value) is not None and value.split("/")[0] not in known

    remove_entities = {
        e["entity_id"] for e in entities
        if e.get("config_entry_id") == entry_id and e.get("platform") == "loxone"
        and e["entity_id"] not in active_ids and absent(e["unique_id"], True)
    }
    remove_devices = set()
    for d in devices:
        identifiers = d.get("identifiers", [])
        if ((set(d.get("config_entries", [])) if "config_entry_id" not in d else {d["config_entry_id"]}) != {entry_id} or not identifiers
                or not all(domain == "loxone" and absent(value) for domain, value in identifiers)):
            continue
        if any(e.get("device_id") == d["id"] and e["entity_id"] not in remove_entities for e in entities):
            continue
        # Preserve parents still referenced by another device.
        if any((other.get("via_device_id") == d["id"] or other.get("parent_device_id") == d["id"]) for other in devices):
            continue
        remove_devices.add(d["id"])
    return sorted(remove_entities), sorted(remove_devices)


def write_backup(directory, snapshot):
    """Write and verify the live registry records before any removal."""
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid.uuid4().hex + ".json")
    def encode(value):
        if isinstance(value, (set, frozenset)):
            return list(value)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        raise TypeError(type(value).__name__)
    raw = json.dumps(snapshot, default=encode, ensure_ascii=False, indent=2).encode("utf-8")
    with path.open("xb") as file:
        os.chmod(path, 0o600)
        file.write(raw)
        file.flush()
        os.fsync(file.fileno())
    if path.read_bytes() != raw:
        raise OSError("Registry backup verification failed")
    return str(path)


async def async_cleanup_registry(hass, entry, program, app):
    """Run after platform setup, using an independently validated current ZIP."""
    if not program:
        return
    import attr
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from .registry_compat import registry_entries
    from .udp_install import ProgramClient
    from .udp_program import digest, unpack

    try:
        known = inventory(program, app)
        devices, entities = dr.async_get(hass), er.async_get(hass)

        def snapshot():
            return ([attr.asdict(d, recurse=False) for d in (
                        *registry_entries(devices.devices),
                        *registry_entries(getattr(devices, "child_devices", ())))],
                    [attr.asdict(e, recurse=False) for e in registry_entries(entities.entities)])

        def plan():
            d, e = snapshot()
            return plan_cleanup(entry.entry_id, d, e, set(hass.states.async_entity_ids()), known)

        proposed = plan()
        if not any(proposed):
            return
        o = entry.options
        client = ProgramClient(o["host"], o["port"], o["username"], o["password"])
        _, raw = await hass.async_add_executor_job(client.current)
        _, verified = unpack(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            structure = json.loads(archive.read("LoxAPP3.json"))
        if (verified != program or structure.get("msInfo", {}).get("serialNr") != app["msInfo"]["serialNr"]):
            return  # A newer upload will be handled by the next setup.
        known.update(inventory(verified, structure))
        proposed = plan()
        if not any(proposed):
            return
        # attrs' recursive serializer handles nested registry alias records.
        saved = {"entry_id": entry.entry_id, "program_sha256": digest(raw),
                 "remove_entities": proposed[0], "remove_devices": proposed[1],
                 "entities": [attr.asdict(entities.async_get(key)) for key in proposed[0]],
                 "devices": [attr.asdict(devices.async_get(key)) for key in proposed[1]]}
        backup = await hass.async_add_executor_job(
            write_backup, hass.config.path("loxone_registry_backups", entry.entry_id), saved)
        _, current = await hass.async_add_executor_job(client.current)
        if current != raw or plan() != proposed:
            return  # Upload or registry changes during backup: defer all removals.
        for entity_id in proposed[0]:
            entities.async_remove(entity_id)
        for device_id in proposed[1]:
            devices.async_remove_device(device_id)
        _LOGGER.info("Removed %s deleted Loxone entities and %s devices; registry backup: %s",
                     len(proposed[0]), len(proposed[1]), backup)
    except Exception as err:
        # A missing/failed project download must never empty the HA registries.
        _LOGGER.warning("Loxone registry cleanup skipped (%s)", type(err).__name__)
