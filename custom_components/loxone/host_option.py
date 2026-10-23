"""Normalize the host option once, so every component sees the same plain host.

The connection, the program download, the UDP source filter and the HA values
sender all use the stored host directly. A pasted browser address such as
"http://192.168.178.123/" broke them in different ways (HTTP 404 for
"//jdev/cfg/apiKey", OSError on the program download).
"""
from __future__ import annotations

from urllib.parse import urlparse


def normalize_host(host, port):
    """Return (host, port) without scheme, trailing slash or embedded port.

    Port 443 is the only signal for https elsewhere, so https with another port
    keeps its scheme. An address with a path keeps the path.
    """
    text = str(host or "").strip()
    port = int(port)
    if "://" not in text and "/" not in text:
        # Working hosts stay byte-identical: the backup directory hashes the host.
        return text, port
    try:
        parsed = urlparse(text if "://" in text else f"//{text}")
        hostname, url_port = parsed.hostname, parsed.port
    except ValueError:
        return text, port
    if not hostname:
        return text, port
    if ":" in hostname:
        hostname = f"[{hostname}]"
    path = parsed.path.rstrip("/")
    if parsed.scheme == "https":
        port = url_port or 443
        if port != 443:
            return f"https://{hostname}:{port}{path}", port
    elif url_port:
        port = url_port
    return f"{hostname}{path}", port
