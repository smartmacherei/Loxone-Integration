"""Build a local installation ZIP from an explicit, credential-free file list."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def package_version(version, commits):
    """Return a PEP 440 dev release of the next version for builds after the release tag."""
    if not commits:
        return version
    match = re.fullmatch(r"(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?", version)
    if not match:
        raise ValueError(f"Unsupported manifest version {version}")
    release, label, number = match.groups()
    if label:
        return f"{release}{label}{int(number) + 1}.dev{commits}"
    *head, last = release.split(".")
    return ".".join([*head, str(int(last) + 1)]) + f".dev{commits}"


def commits_since_release(version):
    """Commits after tag v<version>; 0 if the tag is missing (unreleased version)."""
    result = subprocess.run(["git", "rev-list", "--count", f"v{version}..HEAD"],
                            cwd=ROOT, capture_output=True, text=True)
    return int(result.stdout) if result.returncode == 0 else 0


def build():
    manifest_path = ROOT / "custom_components/loxone/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    version = manifest["version"] = package_version(manifest["version"], commits_since_release(manifest["version"]))
    files = [p for p in (ROOT / "custom_components/loxone").rglob("*")
             if p.is_file() and p.suffix in {".py", ".json", ".yaml", ".yml"}
             and "tests" not in p.parts and "__pycache__" not in p.parts and p != manifest_path]
    files += [ROOT / name for name in ("README.md", "README.de.md", "CHANGELOG.md", "LICENSE", "NOTICE")]
    files += [ROOT / "scripts" / "extract_program_archive.py"]
    files += [ROOT / "docs" / name for name in (
        "automatic-udp.md", "automatic-udp.de.md", "device-coverage.md", "device-coverage.de.md",
        "room-mapping.md", "udp-setup-diagnostics.md", "connection-diagnostics.md")]
    path = ROOT / "dist" / f"loxone-{version}.zip"
    path.parent.mkdir(exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for file in sorted(files):
            archive.write(file, file.relative_to(ROOT).as_posix())
        # Only the packaged manifest carries the test version; the repo file stays unchanged.
        archive.writestr(manifest_path.relative_to(ROOT).as_posix(), json.dumps(manifest, indent=2) + "\n")
        archive.writestr("INSTALL.txt", """LOXONE FOR HOME ASSISTANT / INSTALLATION

EN: Back up Home Assistant first. Copy the included custom_components/loxone
folder to /config/custom_components/loxone, replacing the integration files.
Restart HA. This is the same domain as PyLoxone; install only one implementation.
Review the automatic setup option: enabling it can back up, modify and restart
the Miniserver program. Follow docs/device-coverage.md for physical acceptance.
Existing project backups must be retained. Do not copy dist or baseline files
into the integration folder. Published releases are also available through HACS
when this repository is added as a custom integration repository.

DE: Zuerst Home Assistant sichern. Den enthaltenen Ordner custom_components/loxone
nach /config/custom_components/loxone kopieren und Integrationsdateien ersetzen.
HA neu starten. Gleiche Domain wie PyLoxone: nur eine Implementierung installieren.
Die automatische Einrichtung kann nach gepruefter Sicherung das Miniserver-
Programm aendern und neu starten. Abnahme: docs/device-coverage.de.md.
Projektsicherungen behalten. Veroeffentlichte Versionen sind auch ueber HACS
mit diesem Repository als benutzerdefinierter Integration verfuegbar.
""")
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read("custom_components/loxone/manifest.json"))["version"] == version
        assert not any(name.endswith((".Loxone", ".LoxCC", ".local.md")) for name in archive.namelist())
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".sha256").write_text(f"{checksum}  {path.name}\n", encoding="ascii")
    print(path)
    print(checksum)


if __name__ == "__main__":
    build()
