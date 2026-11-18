"""UDP setup runs once on load; explicit HA-values checks still read the program."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

from test_udp_diagnostics import manager, reporting  # noqa: F401 (pytest fixture)
from test_udp_install import archive, XML


def test_load_checks_once_and_later_config_save_does_not_upload(reporting, tmp_path, monkeypatch):
    setup = manager(reporting, tmp_path)
    timers = []
    monkeypatch.setattr(sys.modules["homeassistant.helpers.event"], "async_track_time_interval",
                        lambda *args: timers.append(args))
    sleep = asyncio.sleep

    async def immediate_delay(seconds):
        assert seconds == 5
    monkeypatch.setattr(reporting.setup.asyncio, "sleep", immediate_delay)

    async def run():
        setup.hass.async_create_task = asyncio.create_task
        setup.start()
        await setup.task
        assert setup.status["state"] == "reload_required"
        assert "neu laden" in reporting.messages[-1]
        assert setup.client.calls == 2
        assert setup.client.events == ["ftp", "upload", "activate", "restart"]
        # Config saves a program without our logger while clients distribute.
        # The completed startup check must not trigger another request or restart.
        setup.client.raw = archive(XML.replace(b"2026", b"2027"))
        setup.client.events.clear()
        for _ in range(3):
            await sleep(0)
        assert setup.client.calls == 2 and setup.client.events == []
        assert timers == []
        await setup.close()
    asyncio.run(run())


def test_reload_verifies_activation_without_another_upload(reporting, tmp_path):
    setup = manager(reporting, tmp_path)
    asyncio.run(setup.check())
    activated = setup.client.files.pop("sps_new.zip")
    reloaded = manager(reporting, tmp_path)
    reloaded.client.raw = activated
    asyncio.run(reloaded.check())
    assert reloaded.status["state"] == "configured"
    assert reloaded.client.calls == 1 and reloaded.client.events == []
    assert reporting.dismissed


def test_explicit_check_reads_current_program_each_time(reporting, tmp_path):
    setup = manager(reporting, tmp_path)
    asyncio.run(setup.check())
    setup.client.raw = setup.client.files.pop("sps_new.zip")
    seen = []
    setup.configured_callbacks.append(lambda: seen.append("sent"))
    asyncio.run(setup.check())
    asyncio.run(setup.check())
    assert setup.client.calls == 4
    assert setup.status["state"] == "configured" and seen == ["sent", "sent"]


def test_unload_during_startup_delay_prevents_program_access(reporting, tmp_path, monkeypatch):
    setup = manager(reporting, tmp_path)
    sleep = asyncio.sleep

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        async def delay(_seconds):
            entered.set()
            await release.wait()
        monkeypatch.setattr(reporting.setup.asyncio, "sleep", delay)
        setup.hass.async_create_task = asyncio.create_task
        setup.start()
        await entered.wait()
        closing = asyncio.create_task(setup.close())
        # close sets the stop event before waiting for the delayed task.
        await sleep(0)
        assert setup.stop.is_set()
        release.set()
        await closing
        assert setup.client.calls == 0 and setup.client.events == []
    asyncio.run(run())


def _immediate(reporting, monkeypatch):
    async def immediate_delay(seconds):
        return None
    monkeypatch.setattr(reporting.setup.asyncio, "sleep", immediate_delay)


def test_load_after_connection_loss_reports_change_without_upload(reporting, tmp_path, monkeypatch):
    setup = manager(reporting, tmp_path)
    _immediate(reporting, monkeypatch)

    async def run():
        setup.hass.async_create_task = asyncio.create_task
        setup.start(after_connection_loss=True)
        await setup.task
        assert setup.status["state"] == "upload_deferred"
        assert setup.client.events == [] and setup.client.calls == 1
        assert list(tmp_path.glob("*.zip")) == []
        assert "nichts hochgeladen" in reporting.messages[-1]
        # A deliberate check afterwards (button, reload) may change the program.
        await setup.check()
        assert setup.status["state"] == "reload_required"
        assert setup.client.events == ["ftp", "upload", "activate", "restart"]
        await setup.close()
    asyncio.run(run())


def test_load_after_connection_loss_still_confirms_unchanged_program(reporting, tmp_path, monkeypatch):
    setup = manager(reporting, tmp_path)
    asyncio.run(setup.check())
    activated = setup.client.files.pop("sps_new.zip")
    reloaded = manager(reporting, tmp_path)
    reloaded.client.raw = activated
    _immediate(reporting, monkeypatch)

    async def run():
        reloaded.hass.async_create_task = asyncio.create_task
        reloaded.start(after_connection_loss=True)
        await reloaded.task
        assert reloaded.status["state"] == "configured"
        assert reloaded.client.events == []
        await reloaded.close()
    asyncio.run(run())


def test_load_without_connection_loss_still_uploads(reporting, tmp_path, monkeypatch):
    setup = manager(reporting, tmp_path)
    _immediate(reporting, monkeypatch)

    async def run():
        setup.hass.async_create_task = asyncio.create_task
        setup.start()
        await setup.task
        assert setup.status["state"] == "reload_required"
        await setup.close()
    asyncio.run(run())


def test_connection_reload_mark_applies_to_every_entry_once(reporting):
    entries = [NS(entry_id="a"), NS(entry_id="b")]
    hass = NS(data={}, config_entries=NS(async_entries=lambda domain: entries))
    reporting.setup.mark_connection_reload(hass)
    assert reporting.setup.take_connection_reload(hass, "a") is True
    assert reporting.setup.take_connection_reload(hass, "a") is False
    assert reporting.setup.take_connection_reload(hass, "b") is True
    assert reporting.setup.take_connection_reload(hass, "other") is False


def test_upload_deferred_state_is_translated():
    root = Path(__file__).parents[1] / "custom_components/loxone/translations"
    for language in ("de", "en"):
        data = json.loads((root / (language + ".json")).read_text(encoding="utf-8"))
        assert "upload_deferred" in data["entity"]["sensor"]["udp_status"]["state"]
