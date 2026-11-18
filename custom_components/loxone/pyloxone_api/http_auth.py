"""HTTP basic auth for the Miniserver.

aiohttp 3.14 deprecates aiohttp.BasicAuth and older aiohttp lacks encode_basic_auth, so the
header is built here, latin-1 encoded like aiohttp's default.
"""

import base64


def basic_auth_header(username: str, password: str) -> str:
    """Value of the Authorization header."""
    return "Basic " + base64.b64encode(f"{username}:{password}".encode("latin-1")).decode()
