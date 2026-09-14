"""Weg 3: the apply button forces a check even when the program listing is unchanged."""
import asyncio

from test_udp_diagnostics import manager, reporting  # noqa: F401  (pytest fixture)


def test_forced_check_downloads_despite_unchanged_listing(reporting, tmp_path):
    setup = manager(reporting, tmp_path)
    client = setup.client
    client.listing = b"-  1000  2026-09-05 12:00:00  sps_1_20260905120000.zip\n"
    restart, current = client.get, client.current

    def get(path):
        return client.listing if path == "/dev/fslist/prog" else restart(path)

    def listed_current():
        client.last_listing = client.listing
        return current()
    client.get, client.current = get, listed_current
    asyncio.run(setup.check())  # uploads: program read before and at activation
    asyncio.run(setup.check())  # after activation the full check runs once more
    assert setup.status["state"] == "blocked" and client.calls == 3
    asyncio.run(setup.check())
    assert client.calls == 3  # unchanged listing: nothing downloaded
    client.listing = b"-  1000  2026-09-05 12:05:00  sps_1_20260905120500.zip\n"
    client.raw = client.files.pop("sps_new.zip")
    asyncio.run(setup.check())
    assert setup.status["state"] == "configured" and client.calls == 4
    seen = []
    setup.configured_callbacks.append(lambda: seen.append("sent"))
    asyncio.run(setup.check())
    assert client.calls == 4 and seen == []
    asyncio.run(setup.check(force=True))
    assert client.calls == 5 and setup.status["state"] == "configured" and seen == ["sent"]
