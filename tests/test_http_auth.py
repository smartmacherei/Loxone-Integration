"""Basic auth of the bundled pyloxone_api HTTP client, without HA.

aiohttp 3.14 deprecates aiohttp.BasicAuth (removed in 4.0), so the Authorization header is built
directly, latin-1 encoded like aiohttp's default.
"""
import asyncio
import importlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import warnings

ROOT = Path(__file__).resolve().parents[1] / "custom_components/loxone/pyloxone_api"
PACKAGE = "pyloxone_api_http_auth_test"
# "user:pässword" in latin-1.
EXPECTED = "Basic dXNlcjpw5HNzd29yZA=="


def basic_auth(*args):
    warnings.warn("BasicAuth is deprecated and will be removed in aiohttp 4.0", DeprecationWarning)


def _load():
    # aiohttp 3.14's deprecated BasicAuth; Windows test runs lack aiohttp.
    aiohttp = ModuleType("aiohttp")
    aiohttp.BasicAuth = basic_auth
    aiohttp.ClientTimeout = lambda **kwargs: kwargs
    aiohttp.ClientSession = object
    previous = sys.modules.get("aiohttp")
    sys.modules["aiohttp"] = aiohttp
    try:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
        return importlib.import_module(PACKAGE + ".loxone_http_client")
    finally:
        if previous is None:
            del sys.modules["aiohttp"]
        else:
            sys.modules["aiohttp"] = previous


http = _load()


def test_http_client_sends_basic_auth_without_the_deprecated_helper():
    requests = []

    class Session:
        closed = False

        async def get(self, url, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(status=200)

    client = http.LoxoneAsyncHttpClient("ms", "user", "pässword", session=Session())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        asyncio.run(client.get("/jdev/cfg/apiKey"))
    assert [str(warning.message) for warning in caught if "BasicAuth" in str(warning.message)] == []
    request, = requests
    assert request["headers"] == {"Authorization": EXPECTED}
    assert "auth" not in request
