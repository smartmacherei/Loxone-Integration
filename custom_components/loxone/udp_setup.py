"""Home Assistant lifecycle for automatic UDP provisioning."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import hashlib
import io
import json
import logging
import threading
import zipfile

from homeassistant.components import persistent_notification
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .topology import enumerate_discoverable, interleave_by_miniserver, terminal_owner
from .udp_install import ProgramClient, install
from .udp_errors import details, failure, notification, restore_failure, utc_now
from .udp_program import digest

_LOGGER = logging.getLogger(__name__)

# Beta for Gateway/Client systems: a small, predictable number of logger
# references per Miniserver, so the first field test stays easy to judge.
GATEWAY_SIGNALS_PER_MINISERVER = 5


class UdpSetup:
    def __init__(self, hass, entry, program):
        self.hass, self.entry = hass, entry
        options = entry.options
        self.client = ProgramClient(options["host"], options["port"],
                                    options["username"], options["password"])
        # Host-based directory persists across removal/reinstallation of the entry.
        identity = hashlib.sha256(str(options["host"]).encode()).hexdigest()[:16]
        self.directory = hass.config.path("loxone_backups", identity)
        self.port = int(options["udp_port"] if "udp_port" in options else 55555)
        # Upper bound for logger references, so a very large installation cannot
        # flood the Miniserver, the network or HA. Terminals beyond it keep polling.
        self.limit = int(options.get("udp_max_signals") or 500)
        # Gateway/Client archives are only touched with the explicit beta option.
        self.gateway_beta = bool(options.get("udp_gateway_beta", False))
        self.stop = threading.Event()
        self.task = None
        self.initial_sha = digest(program) if program else None
        self.status = {"state": "checking", "step": "program_download",
                       "backup_verified": False, "backup_location": self.directory}
        self.cancel_interval = None
        # Private support evidence: excluded from status, notifications and logs.
        self.failed_program = None
        self.listing_sha = None
        self.logged = None
        self.signals_discovered = None

    def select(self, raw, xml):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            controls = json.loads(archive.read("LoxAPP3.json"))
        # Program order is stable, so repeated checks select the same terminals.
        discovered = enumerate_discoverable(xml, controls)
        owner = terminal_owner(xml) if self.gateway_beta else {}
        if self.gateway_beta:
            # Same rotation as entity discovery, so both pick the same subset.
            discovered = interleave_by_miniserver(discovered, owner)
        found = [u for u, _ in discovered]
        self.signals_discovered = len(found)
        if len(found) > self.limit:
            _LOGGER.warning("Loxone UDP: %s discovered terminals exceed the limit of %s; only the "
                            "first %s receive real-time updates (option udp_max_signals)",
                            len(found), self.limit, self.limit)
            found = found[:self.limit]
        if self.gateway_beta:
            # Per Miniserver only the first few terminals that start enabled in
            # HA; device internals that start disabled get no logger reference.
            enabled = {u for u, control in discovered if control.get("auto_enabled_default") is not False}
            count, picked = {}, []
            for u in found:
                live = owner.get(u.lower())
                if not live or u not in enabled or count.get(live, 0) >= GATEWAY_SIGNALS_PER_MINISERVER:
                    continue
                count[live] = count.get(live, 0) + 1
                picked.append(u)
            found = picked
        return set(found)

    def start(self):
        self.cancel_interval = async_track_time_interval(self.hass, self.tick, timedelta(seconds=60))
        # Let setup complete before triggering a Miniserver restart/reconnection.
        self.task = self.hass.async_create_task(self._run_delayed())

    async def _run_delayed(self):
        await asyncio.sleep(5)
        if not self.stop.is_set():
            await self.check()

    async def tick(self, _now):
        if not self.stop.is_set() and (self.task is None or self.task.done()):
            self.task = self.hass.async_create_task(self.check())

    async def check(self):
        previous = self.status.get("state")
        previous_error = self.status.get("error")
        previous_attempt = self.status.get("error_attempt")
        if previous in {"configured", "error", "blocked"} and self.listing_sha is not None:
            # Only the small directory listing is read every interval. The full
            # program is downloaded again only after Config saved a new one.
            try:
                listing = await self.hass.async_add_executor_job(self.client.get, "/dev/fslist/prog")
            except Exception:
                listing = None
            if listing is not None and digest(listing) == self.listing_sha:
                self.status["last_listing_check"] = utc_now()
                return
        self.status.update(state="checking", step="program_download", backup_verified=False)
        self.status["step_history"] = []
        self.status.pop("backup", None)
        self.client.last_listing = None
        loop = asyncio.get_running_loop()
        active = True

        def update_progress(data):
            if active:
                step = data.get("step")
                if step and (not self.status["step_history"] or self.status["step_history"][-1]["step"] != step):
                    from .udp_errors import utc_now
                    self.status["step_history"].append({"step": step, "timestamp": utc_now()})
                    self.status["step_history"] = self.status["step_history"][-50:]
                    _LOGGER.debug("Loxone UDP setup step: %s", step)
                self.status.update(data)

        def progress(data):
            loop.call_soon_threadsafe(update_progress, data)

        try:
            result = await self.hass.async_add_executor_job(
                install, self.client, self.directory, self.port, self.select, self.stop, progress,
                self.gateway_beta,
            )
            active = False
            self.status.update(result)
            if result["state"] == "blocked":
                data = result["error"]
                if (data["code"] == "PREVIOUS_ATTEMPT_BLOCKED" and previous_error
                        and previous_attempt == result.get("error_attempt")):
                    data = previous_error
                self.set_error(data)
                self.notify(notification(self.status["error"], self.language, blocked=True))
            elif result["state"] == "configured":
                self.failed_program = None
                self.logged = None
                for key in ("cleanup_warning", "activation_error"):
                    self.archive_detail(key)
                if self.status.get("error"):
                    self.status["last_error"] = dict(self.status["error"], historical=True)
                for key in ("error", "error_code", "error_step", "error_timestamp", "error_persisted", "error_attempt", "step"):
                    self.status.pop(key, None)
                persistent_notification.async_dismiss(self.hass, "loxone_udp_" + self.entry.entry_id)
                if self.initial_sha is not None and result["xml_sha256"] != self.initial_sha:
                    if not self.stop.is_set():
                        # Schedule outside this task, which unload waits for.
                        self.hass.async_create_task(self.hass.config_entries.async_reload(self.entry.entry_id))
            if previous != result["state"]:
                _LOGGER.info("Loxone automatic UDP setup: %s", result["state"])
        except Exception as err:
            active = False
            self.status["state"] = "error"
            data = restore_failure(getattr(err, "udp_failure", None)) or failure(self.status.get("step"), err)
            self.set_error(data)
            source = getattr(err, "udp_source_program", None)
            self.failed_program = (source, data["timestamp"]) if source is not None else None
            backup = getattr(err, "udp_backup", None)
            if backup:
                self.status.update(backup=backup, backup_verified=True)
            self.status["error_persisted"] = getattr(err, "udp_error_persisted", None)
            self.status["error_attempt"] = getattr(err, "udp_attempt", None)
            if previous_attempt != self.status["error_attempt"]:
                for key in ("cleanup_warning", "activation_error"):
                    self.archive_detail(key)
            warning = restore_failure(getattr(err, "udp_cleanup_warning", None))
            if warning:
                self.status["cleanup_warning"] = warning
            activation_error = restore_failure(getattr(err, "udp_activation_error", None))
            if activation_error:
                self.status["activation_error"] = activation_error
                _LOGGER.warning("Loxone UDP original activation failure: code=%s step=%s exception=%s",
                                activation_error["code"], activation_error["step"], activation_error["exception_type"])
            # The same failure every minute is one warning, then debug only.
            key = (data["code"], data["step"])
            log = _LOGGER.debug if key == self.logged else _LOGGER.warning
            self.logged = key
            log("Loxone automatic UDP setup failed: code=%s step=%s exception=%s; %s Next check: %s",
                data["code"], data["step"], data["exception_type"], data["description"], data["next_check"])
            message = notification(data, self.language)
            message += ("\n\nFür Support: Diagnosedaten herunterladen. Der Download enthält das vollständige Programmarchiv, sofern abrufbar; bitte vertraulich weitergeben."
                        if self.language.startswith("de") else
                        "\n\nFor support: download diagnostics. The download includes the complete program archive when available; share privately.")
            if self.status["error_persisted"] is False:
                _LOGGER.warning("Loxone UDP error details could not be persisted; the existing activation guard remains unchanged")
                message += ("\n\nFehlerdetails konnten nicht dauerhaft gespeichert werden; die vorhandene Aktivierungssperre bleibt bestehen."
                            if self.language.startswith("de") else "\n\nError details could not be persisted; the existing activation guard remains in place.")
            self.notify(message)
        finally:
            active = False
            self.status.update(signal_limit=self.limit, signals_discovered=self.signals_discovered,
                               gateway_beta=self.gateway_beta,
                               signals_per_miniserver=GATEWAY_SIGNALS_PER_MINISERVER if self.gateway_beta else None)
            listing = getattr(self.client, "last_listing", None)
            self.listing_sha = digest(listing) if listing else None

    @property
    def language(self):
        return getattr(self.hass.config, "language", "en") or "en"

    def set_error(self, data):
        self.status.update(error=data, error_code=data["code"], error_step=data["step"],
                           error_timestamp=data["timestamp"], step=data["step"])

    def archive_detail(self, key):
        data = self.status.pop(key, None)
        if data:
            self.status["last_" + key] = dict(data, historical=True)

    def notify(self, message):
        if self.status.get("activation_error"):
            data = self.status["activation_error"]
            label = "Ursprünglicher Aktivierungsfehler" if self.language.startswith("de") else "Original activation error"
            description, check = details(data, "de" if self.language.startswith("de") else "en")
            message += f"\n\n{label}: {data['code']} ({data['exception_type']})\n\n{description}\n\n{check}"
        if self.status.get("cleanup_warning"):
            message += "\n\n" + details(self.status["cleanup_warning"], "de" if self.language.startswith("de") else "en")[0]
        if self.status.get("backup_verified"):
            label = "Verifizierte Sicherung" if self.language.startswith("de") else "Verified backup"
            location = self.status["backup"]
        else:
            label = "Vorgesehener Sicherungsort (noch nicht verifiziert)" if self.language.startswith("de") else "Intended backup location (not yet verified)"
            location = self.directory
        persistent_notification.async_create(
            self.hass, message + f"\n\n{label}: `{location}`",
            title="Loxone UDP setup / Einrichtung", notification_id="loxone_udp_" + self.entry.entry_id,
        )

    async def close(self):
        self.stop.set()
        if self.cancel_interval:
            self.cancel_interval()
        # Never abandon a worker halfway through writing/activating a program.
        if self.task is not None and not self.task.done():
            await asyncio.shield(self.task)
