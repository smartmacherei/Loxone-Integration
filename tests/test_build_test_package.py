"""Test packages must report a version distinct from, and ordered after, the release."""
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from packaging.version import Version

PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_test_package.py"
SPEC = importlib.util.spec_from_file_location("build_test_package", PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

RELEASES = [("1.8.5b2", ["1.8.5b3", "1.8.5rc1", "1.8.5"]),
            ("1.8.5rc1", ["1.8.5rc2", "1.8.5"]),
            ("1.8.5", ["1.8.6b1", "1.8.6", "1.9.0b1"])]


@pytest.mark.parametrize("released, upcoming", RELEASES)
def test_test_build_sorts_after_release_and_before_next_one(released, upcoming):
    assert builder.package_version(released, 0) == released  # Built from the release tag itself.
    first, later = builder.package_version(released, 1), builder.package_version(released, 7)
    assert Version(released) < Version(first) < Version(later)
    for version in upcoming:
        assert Version(later) < Version(version)


@pytest.mark.parametrize("released, upcoming", RELEASES)
def test_hacs_still_offers_the_next_release(released, upcoming):
    awesome = pytest.importorskip("awesomeversion")
    strategy = awesome.AwesomeVersionStrategy
    # HA's loader rejects custom integrations whose version fails this check.
    build = awesome.AwesomeVersion(builder.package_version(released, 7), ensure_strategy=[
        strategy.CALVER, strategy.SEMVER, strategy.SIMPLEVER, strategy.BUILDVER, strategy.PEP440])
    for version in upcoming:
        assert awesome.AwesomeVersion(version) > build
    # AwesomeVersion compares only the last pre-release segment, so nothing sorts
    # between two pre-releases; above a final release the order holds.
    if Version(released).pre is None:
        assert build > awesome.AwesomeVersion(released)


def test_package_manifest_carries_test_version_and_repo_stays_unchanged(monkeypatch):
    manifest = builder.ROOT / "custom_components/loxone/manifest.json"
    before = manifest.read_bytes()
    released = json.loads(before)["version"]
    expected = builder.package_version(released, 3)
    assert expected != released
    monkeypatch.setattr(builder, "commits_since_release", lambda version: 3)
    dist = builder.ROOT / "dist"
    existed = dist.exists()
    path = dist / f"loxone-{expected}.zip"
    try:
        builder.build()
        with ZipFile(path) as archive:
            assert json.loads(archive.read("custom_components/loxone/manifest.json"))["version"] == expected
    finally:
        path.unlink(missing_ok=True)
        path.with_suffix(".sha256").unlink(missing_ok=True)
        if not existed and dist.exists() and not any(dist.iterdir()):
            dist.rmdir()
    assert manifest.read_bytes() == before
