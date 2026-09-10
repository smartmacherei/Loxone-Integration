"""Bounded safe timeline for integration setup, including unexpected failures."""
import logging
from .connection_probe import now
from .udp_errors import SAFE_TYPES

KEY = "loxone_startup_trace"
_LOGGER = logging.getLogger(__name__)
STEPS = {
    "prepare_connection": ("Verbindung vorbereiten", "Prepare connection"),
    "http_identity": ("Miniserver-Webschnittstelle erreichen", "Reach Miniserver web API"),
    "http_structure": ("Web-Anmeldung und Projektstruktur laden", "Web login and load project structure"),
    "public_key": ("Verschlüsselung vorbereiten", "Prepare encryption"),
    "websocket_connect": ("WebSocket-Verbindung öffnen", "Open WebSocket connection"),
    "topology_discovery": ("Ein-/Ausgänge erkennen und UDP-Empfang vorbereiten", "Discover I/O and prepare UDP reception"),
    "area_mapping": ("HA-Raumzuordnung initialisieren", "Initialize HA area mapping"),
    "entity_platforms": ("HA-Entitäten einrichten", "Set up HA entities"),
}


def advance(hass, entry, step):
    trace = hass.data.setdefault(KEY, {}).setdefault(entry.entry_id, {"events": []})
    if step not in STEPS:
        return
    previous = trace.get("step")
    if previous:
        trace["last_successful_step"] = previous
        trace["events"].append({"step": previous, "state": "completed", "timestamp": now()})
    trace.update(step=step, step_de=STEPS[step][0], step_en=STEPS[step][1], state="running", timestamp=now())
    trace["events"] = trace["events"][-30:]
    _LOGGER.info("Loxone setup step: %s", step)


async def tracked_setup(hass, entry, setup):
    from homeassistant.helpers.storage import Store
    hass.data.setdefault(KEY, {})[entry.entry_id] = {"events": [], "started_at": now()}
    advance(hass, entry, "prepare_connection")
    trace = hass.data[KEY][entry.entry_id]
    try:
        result = await setup(hass, entry)
        if result:
            trace.update(state="completed", last_successful_step=trace["step"])
        else:
            trace.update(state="failed", error_code=trace["step"].upper() + "_FAILED")
        return result
    except Exception as error:
        name = type(error).__name__
        trace.update(state="failed", error_code=trace["step"].upper() + "_FAILED",
                     exception_type=name if name in SAFE_TYPES or name == "ConfigEntryNotReady" else "Exception")
        trace["next_check"] = (
            "Integration aktualisieren und HA-Version prüfen; Fehler in der HA-Raumzuordnung. Kein Hinweis auf einen FTP-Portfehler."
            if trace["step"] == "area_mapping" else
            "Verbindungsdiagnose ausführen und den gescheiterten Schritt prüfen. Ursache durch diesen Startfehler allein nicht bestätigt."
        )
        _LOGGER.error("Loxone setup failed: step=%s code=%s type=%s",
                      trace["step"], trace["error_code"], trace["exception_type"])
        raise
    finally:
        trace["timestamp"] = now()
        trace["events"].append({"step": trace["step"], "state": trace["state"], "timestamp": trace["timestamp"]})
        try:
            await Store(hass, 1, KEY + "." + entry.entry_id).async_save(trace)
        except Exception:
            _LOGGER.warning("Loxone startup diagnostic history could not be saved")


async def diagnostics(hass, entry):
    from homeassistant.helpers.storage import Store
    if entry.entry_id in hass.data.get(KEY, {}):
        return hass.data[KEY][entry.entry_id]
    previous = await Store(hass, 1, KEY + "." + entry.entry_id).async_load()
    return {**previous, "historical": True} if previous else None
