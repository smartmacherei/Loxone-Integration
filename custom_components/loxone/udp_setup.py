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
from .topology import enumerate_discoverable
from .udp_install import ActivationUncertainError, ProgramClient, install
from .udp_program import digest

_LOGGER = logging.getLogger(__name__)


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
        self.stop = threading.Event()
        self.task = None
        self.initial_sha = digest(program) if program else None
        self.status = {"state": "checking"}
        self.cancel_interval = None

    @staticmethod
    def select(raw, xml):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            controls = json.loads(archive.read("LoxAPP3.json"))
        return {u for u, _ in enumerate_discoverable(xml, controls)}

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
        try:
            result = await self.hass.async_add_executor_job(
                install, self.client, self.directory, self.port, self.select, self.stop
            )
            previous = self.status.get("state")
            self.status.update(result)
            if result["state"] == "blocked":
                self.notify("Automatic UDP setup is blocked after an earlier activation attempt. "
                            "Polling remains available. Check the logs and the original project backup "
                            "before retrying. / Ein vorheriger Aktivierungsversuch blockiert die "
                            "automatische Einrichtung. Bitte Protokoll und Projektsicherung prüfen.")
            elif result["state"] == "configured":
                persistent_notification.async_dismiss(self.hass, "loxone_udp_" + self.entry.entry_id)
                if self.initial_sha is not None and result["xml_sha256"] != self.initial_sha:
                    if not self.stop.is_set():
                        # Schedule outside this task, which unload waits for.
                        self.hass.async_create_task(self.hass.config_entries.async_reload(self.entry.entry_id))
            if previous != result["state"]:
                _LOGGER.info("Loxone automatic UDP setup: %s", result["state"])
        except Exception as err:
            self.status["state"] = "error"
            # Exception messages from network libraries may include server content.
            _LOGGER.warning("Loxone automatic UDP setup failed (%s); polling fallback remains active", type(err).__name__)
            if isinstance(err, ActivationUncertainError):
                self.notify("Activation could not be confirmed and cleanup could not be verified. "
                            "A /prog/sps_new.zip file may remain on the Miniserver and load on its next "
                            "restart. Check this with your installer before restarting. The original "
                            "backup is retained. / Aktivierung und Bereinigung unbestätigt: Auf dem "
                            "Miniserver kann /prog/sps_new.zip liegen und beim nächsten Neustart "
                            "geladen werden. Vor einem Neustart durch den Errichter prüfen lassen.")
            else:
                self.notify("Automatic UDP setup failed. Check FTP access, program format and backup "
                            "storage. Failed activation attempts are blocked from automatic repetition. "
                            "/ Automatische UDP-Einrichtung fehlgeschlagen. Bitte FTP-Zugang, "
                            "Programmformat und Speicherplatz für die Sicherung prüfen. "
                            "Fehlgeschlagene Aktivierungsversuche werden nicht automatisch wiederholt.")

    def notify(self, message):
        persistent_notification.async_create(
            self.hass, message + "\n\nBackup folder / Sicherungsordner: `" + self.directory + "`",
            title="Loxone UDP setup / Einrichtung", notification_id="loxone_udp_" + self.entry.entry_id,
        )

    async def close(self):
        self.stop.set()
        if self.cancel_interval:
            self.cancel_interval()
        # Never abandon a worker halfway through writing/activating a program.
        if self.task is not None and not self.task.done():
            await asyncio.shield(self.task)
