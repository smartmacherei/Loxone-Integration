"""HA entry point for explicitly requested, read-only connectivity diagnostics."""
import asyncio
import logging
import time

from homeassistant.components import persistent_notification
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .connection_probe import describe, now, probe
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
KEY = DOMAIN + "_connection_diagnostics"


def live_status(hass, entry):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    api = getattr(coordinator, "api", None)
    receiver = hass.data.get(DOMAIN + "_udp", {}).get(entry.entry_id)
    last = getattr(receiver, "last_valid_received", None)
    age = max(0, round(time.monotonic() - last, 1)) if last is not None else None
    port = int(entry.options.get("udp_port", 55555))
    return {
        "websocket_connected": bool(api and api.is_connected),
        "websocket_authentication": getattr(api, "authentication_state", "not_confirmed") if api and api.is_connected else "disconnected",
        "udp_port": port,
        "udp_listener_active": receiver is not None,
        "udp_receive_state": "disabled" if port == 0 else "listener_missing" if receiver is None else "waiting_for_data" if age is None else "receiving" if age < 120 else "stale",
        "udp_packets": getattr(receiver, "packets", 0),
        "udp_values": getattr(receiver, "values", 0),
        "udp_last_valid_age_seconds": age,
    }


async def run_check(hass, entry):
    locks = hass.data.setdefault(KEY + "_locks", {})
    lock = locks.setdefault(entry.entry_id, asyncio.Lock())
    if lock.locked():
        raise HomeAssistantError("A connection check is already running")
    manager = hass.data.get(DOMAIN + "_udp_setup", {}).get(entry.entry_id)
    if manager and manager.status.get("state") in {"checking", "restarting"}:
        raise HomeAssistantError("Automatic UDP setup is in progress; run the check after it finishes")
    async with lock:
        reports = hass.data.setdefault(KEY, {})
        reports[entry.entry_id] = {"state": "running", "started_at": now(), "checks": {}}
        loop = asyncio.get_running_loop()
        active = True

        def update(step, item):
            if active:
                reports[entry.entry_id]["checks"][step] = item

        def progress(step, item):
            loop.call_soon_threadsafe(update, step, item)

        try:
            result = await hass.async_add_executor_job(probe, dict(entry.options), progress)
        finally:
            active = False
        result["observed_connection"] = live_status(hass, entry)
        reports[entry.entry_id] = result
        try:
            await Store(hass, 1, KEY + "." + entry.entry_id).async_save(result)
        except Exception:
            _LOGGER.warning("Loxone connection check completed; diagnostic history could not be saved")
        de = hass.config.language == "de"
        message = describe(result, hass.config.language)
        live = result["observed_connection"]
        if de:
            udp_labels = {"disabled": "Deaktiviert", "listener_missing": "Kein aktiver Empfangslistener", "waiting_for_data": "Listener aktiv, noch keine gültigen Daten empfangen", "receiving": "Empfängt gültige Daten", "stale": "Keine aktuellen gültigen Daten"}
            message += f"\n\nUDP-Empfang: {udp_labels[live['udp_receive_state']]}; Port {live['udp_port']}; Pakete {live['udp_packets']}."
            message += "\n\nDies war eine Verbindungsprüfung, keine UDP-Einrichtung. Keine Uploads oder Neustarts. Schreibrechte und die Zustellung neuer UDP-Pakete wurden nicht aktiv getestet."
        else:
            message += f"\n\nUDP reception: {live['udp_receive_state']}; port {live['udp_port']}; packets {live['udp_packets']}."
            message += "\n\nThis was a connectivity check, not UDP setup. No uploads or restarts. Write access and delivery of new UDP packets were not actively tested."
        persistent_notification.async_create(hass, message,
            title="Loxone-Verbindungsdiagnose" if de else "Loxone connection diagnostics",
            notification_id=KEY + entry.entry_id)
        return result


async def diagnostics(hass, entry):
    last = hass.data.get(KEY, {}).get(entry.entry_id)
    if last is None:
        last = await Store(hass, 1, KEY + "." + entry.entry_id).async_load()
    return {"current": live_status(hass, entry), "last_explicit_check": last}
