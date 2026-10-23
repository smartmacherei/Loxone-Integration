"""A pasted browser address must become the plain host every component expects."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components/loxone"


def normalize(host, port=80):
    spec = importlib.util.spec_from_file_location("host_option", ROOT / "host_option.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.normalize_host(host, port)


def test_plain_host_stays_unchanged():
    assert normalize("192.168.178.123") == ("192.168.178.123", 80)
    assert normalize("miniserver.invalid", 443) == ("miniserver.invalid", 443)
    # The backup directory is derived from the host, so case must not change.
    assert normalize("MyMiniserver.invalid") == ("MyMiniserver.invalid", 80)


def test_browser_address_loses_scheme_and_trailing_slash():
    # 1.8.2 sent "//jdev/cfg/apiKey" (HTTP 404) and failed the program download (OSError).
    assert normalize("http://192.168.178.123/") == ("192.168.178.123", 80)
    assert normalize("192.168.178.123/") == ("192.168.178.123", 80)
    assert normalize("  http://192.168.178.123  ") == ("192.168.178.123", 80)


def test_port_in_address_wins_over_port_field():
    assert normalize("http://192.168.178.123:8080/") == ("192.168.178.123", 8080)


def test_https_keeps_meaning():
    assert normalize("https://miniserver.invalid/") == ("miniserver.invalid", 443)
    # Only port 443 implies https elsewhere, so a custom https port keeps its scheme.
    assert normalize("https://miniserver.invalid:8443/") == ("https://miniserver.invalid:8443", 8443)


def test_address_with_path_keeps_path_without_trailing_slash():
    assert normalize("dns.loxonecloud.com/504F94100296/") == ("dns.loxonecloud.com/504F94100296", 80)


def test_empty_or_unparsable_input_is_left_to_validation():
    assert normalize("", 80) == ("", 80)
    assert normalize("http://", 80) == ("http://", 80)
