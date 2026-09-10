"""Recover original program bytes from a Home Assistant support diagnostic JSON."""
import argparse
import base64
import hashlib
import json
from pathlib import Path


def extract(source, destination):
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    # Home Assistant wraps integration diagnostics in its own `data` envelope.
    payload = data.get("data", data)["program_archive"]
    if payload.get("state") != "included":
        raise ValueError("No program archive included in this diagnostic")
    raw = base64.b64decode(payload["data_base64"], validate=True)
    if len(raw) != payload["size_bytes"] or hashlib.sha256(raw).hexdigest() != payload["sha256"]:
        raise ValueError("Archive size or checksum mismatch")
    # Do not parse or unpack: invalid archives are essential support evidence.
    with Path(destination).open("xb") as handle:
        handle.write(raw)
    return len(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostic_json")
    parser.add_argument("output_zip")
    args = parser.parse_args()
    print(f"Recovered {extract(args.diagnostic_json, args.output_zip)} bytes; checksum verified.")
