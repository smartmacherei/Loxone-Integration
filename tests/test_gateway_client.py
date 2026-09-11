"""Gateway/Client archives: full project, Miniserver ownership, per-client polling."""
import asyncio
import importlib.util
import io
from pathlib import Path
import zipfile

from test_udp_install import program

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "loxone"
spec = importlib.util.spec_from_file_location("gateway_topology", ROOT / "topology.py")
top = importlib.util.module_from_spec(spec)
spec.loader.exec_module(top)

GW, CL = "10000000-0000-0000-ffff000000000001", "20000000-0000-0000-ffff000000000002"
GW_IN, CL_IN = "10000000-0000-0001-ffff000000000001", "20000000-0000-0001-ffff000000000002"
GLOBAL = '<C Type="CategoryCaption" U="30000000-0000-0000-ffff000000000003" Title="Kategorien"/>'


def live(uuid, title, ip, terminal, extra=""):
    return (f'<C Type="LoxLIVE" U="{uuid}" Title="{title}" Serial="{uuid[-4:]}" IntAddr="{ip}" ExP="80">'
            f'<C Type="InputCaption" U="{uuid[:-1]}9" Title="Eingänge">'
            f'<C Type="DigitalIn" U="{terminal}" Title="Kontakt {title}"><Display Unit="&lt;v&gt;"/></C></C>'
            f'<C Type="WeatherCaption" U="{uuid[:-1]}8">{extra}</C></C>')


GATEWAY_OBJ = (f'<C Type="Gateway" U="{GW[:-1]}7" Title="Gateway" Concentrator="true" Exts="1">'
               f'<SLAVE Used="true" Name="Client" IP="192.168.9.12" Serial="0002" Type="1" Port="8080" uuid="{CL}"/></C>')
CLIENT_OBJ = f'<C Type="GatewayClient" U="{CL[:-1]}7" Title="Client" ConcentratorClient="true" ProgType="1" Serial="0002" GwAddr="192.168.9.10"/>'
PROG_GW = f'<C Type="Program" U="{GW[:-1]}6" Title="Gateway" Ref="{GW}"><C Type="Page" U="{GW[:-1]}5" Title="Seite"/></C>'
PROG_CL = f'<C Type="Program" U="{CL[:-1]}6" Title="Client" Ref="{CL}"><C Type="Page" U="{CL[:-1]}5" Title="Seite"/></C>'


def document(*parts):
    return ('<?xml version="1.0" encoding="utf-8"?><ControlList Version="259">'
            '<C Type="Document" U="00000000-0000-0000-ffff000000000000" Title="Projekt">'
            + GLOBAL + "".join(parts) + "</C></ControlList>").encode()


FULL = document(live(GW, "Gateway", "192.168.9.10", GW_IN, GATEWAY_OBJ), live(CL, "Client", "192.168.9.12", CL_IN, CLIENT_OBJ), PROG_GW, PROG_CL)
PART_GW = document(live(GW, "Gateway", "192.168.9.10", GW_IN, GATEWAY_OBJ), PROG_GW)
PART_CL = document(live(CL, "Client", "192.168.9.12", CL_IN, CLIENT_OBJ), PROG_CL)
SINGLE = document(live(GW, "Solo", "192.168.9.10", GW_IN), PROG_GW)


def archive(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as output:
        for name, content in members.items():
            output.writestr(name, content)
    return buffer.getvalue()


def test_full_project_is_preferred_over_partial_programs():
    raw = archive({"LoxAPP3.json": b"{}", "sps1.LoxCC": program.encode(PART_CL),
                   "sps0.LoxCC": program.encode(PART_GW), "sps.Loxone": b"\xef\xbb\xbf" + FULL})
    xml = top.program_from_zip(raw)
    assert xml.lstrip(b"\xef\xbb\xbf") == FULL
    assert top.program_from_zip(archive({"sps0.LoxCC": program.encode(SINGLE)})) == SINGLE


def test_partial_programs_are_merged_when_no_full_project_exists(monkeypatch):
    monkeypatch.setattr(top, "classify_terminal", lambda *args: None)
    raw = archive({"sps1.LoxCC": program.encode(PART_CL), "sps0.LoxCC": program.encode(PART_GW)})
    merged = top.program_from_zip(raw)
    servers = {m["uuid"]: m for m in top.miniservers(merged)}
    assert set(servers) == {GW, CL}
    assert {u for u, _ in top.enumerate_discoverable(merged, {})} == {GW_IN, CL_IN}
    assert merged.count(b'Type="CategoryCaption"') == 1
    assert merged.count(b'Type="Program"') == 2


def test_miniserver_roles_addresses_and_ownership():
    servers = {m["uuid"]: m for m in top.miniservers(FULL)}
    assert servers[GW] == {"uuid": GW, "name": "Gateway", "serial": "0001", "role": "gateway", "index": 0, "host": "192.168.9.10", "port": 80}
    assert servers[CL] == {"uuid": CL, "name": "Client", "serial": "0002", "role": "client", "index": 1, "host": "192.168.9.12", "port": 8080}
    assert top.miniservers(SINGLE)[0]["role"] == "single"
    owner = top.terminal_owner(FULL)
    assert owner[GW_IN] == GW and owner[CL_IN] == CL
    devices = top.build_device_map(FULL)
    assert devices[GW_IN] == (GW, "Miniserver Gateway") and devices[CL_IN] == (CL, "Miniserver Client")


def test_client_hosts_only_for_client_terminals():
    hosts = top.client_hosts(FULL, [GW_IN, CL_IN, "unknown"])
    assert hosts == {CL_IN: ("192.168.9.12", 8080)}
    assert top.client_hosts(SINGLE, [GW_IN]) == {}


def test_values_are_fetched_from_the_owning_miniserver(monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "aiohttp", SimpleNamespace(
        BasicAuth=lambda user, password: (user, password), ClientTimeout=lambda total: total))
    urls = []

    class Response:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def json(self, content_type=None): return {"LL": {"Code": "200", "value": "1"}}

    class Session:
        def get(self, url, **kwargs):
            urls.append(url)
            return Response()

    values = asyncio.run(top.async_fetch_values(Session(), "gateway.local", 80, "u", "p", [GW_IN, CL_IN],
                                                hosts={CL_IN: ("192.168.9.12", 8080)}))
    assert values == {GW_IN: 1.0, CL_IN: 1.0}
    assert sorted(urls) == sorted([f"http://gateway.local:80/jdev/sps/io/{GW_IN}", f"http://192.168.9.12:8080/jdev/sps/io/{CL_IN}"])


def test_udp_receiver_accepts_every_miniserver_address():
    import socket
    spec_udp = importlib.util.spec_from_file_location("gateway_udp_push", ROOT / "udp_push.py")
    udp = importlib.util.module_from_spec(spec_udp)
    spec_udp.loader.exec_module(udp)

    async def run():
        loop = asyncio.get_running_loop()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        transport, protocol = await udp.async_start_udp_push(
            loop, port, lambda values: None, host="127.0.0.1", source_host=["127.0.0.1", "127.0.0.2"])
        try:
            return protocol._allowed_hosts
        finally:
            transport.close()

    assert asyncio.run(run()) == {"127.0.0.1", "127.0.0.2"}
