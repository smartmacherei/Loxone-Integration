"""Explicit support download: original project bytes, never logged or activated."""
from __future__ import annotations

import base64

from .udp_errors import TRACE, SetupTrace, failure, utc_now
from .udp_program import MAX_SIZE, digest, unpack


def collect(manager):
    """Run in the executor. Cached failure bytes take precedence over a new read."""
    captured = getattr(manager, "failed_program", None)
    try:
        if captured is not None:
            raw, timestamp = captured
        else:
            _, raw = manager.client.current()
            timestamp = utc_now()
    except Exception as error:
        return {"state": "unavailable", "error": failure("program_download", error)}
    result = {
        "state": "included",
        "contains_sensitive_project_data": True,
        "notice_de": "Enthält das vollständige, nicht anonymisierte Miniserver-Programmarchiv. Nur vertraulich an den Support weitergeben.",
        "notice_en": "Contains the complete, unredacted Miniserver program archive. Share privately with support only.",
        "filename": "miniserver-program.zip",
        "encoding": "base64",
        "size_bytes": len(raw),
        "captured_at": timestamp,
        "matches_failed_attempt": captured is not None,
        "source": "failed_attempt" if captured is not None else "read_only_download",
    }
    if len(raw) > MAX_SIZE:
        return dict(result, state="size_limit", limit_bytes=MAX_SIZE)
    result["sha256"] = digest(raw)
    # Reproduction is possible even when ZIP parsing or XML decoding fails.
    trace = SetupTrace()
    token = TRACE.set(trace)
    try:
        unpack(raw)
    except Exception as error:
        result["validation"] = failure(trace.step, error)
    else:
        result["validation"] = {"state": "passed"}
    finally:
        TRACE.reset(token)
    result["data_base64"] = base64.b64encode(raw).decode("ascii")
    return result
