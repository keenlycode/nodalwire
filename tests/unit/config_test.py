from importlib.resources import files
from pathlib import Path

import pytest

from nodalwire import Node, RelayConfig, load_config
from nodalwire.config import local_endpoint


def test_defaults_local_only():
    assert RelayConfig().endpoint == "tcp://127.0.0.1:5555"
    assert RelayConfig().lease_seconds == 10
    assert RelayConfig().allowed_names is None
    assert RelayConfig().permits("alice", "bob")
    assert RelayConfig(endpoint="tcp://localhost:5555").endpoint == "tcp://127.0.0.1:5555"


@pytest.mark.parametrize(
    "endpoint",
    [
        "tcp://0.0.0.0:5555", "tcp://*:5555", "tcp://192.0.2.1:5555",
        "tcp://[::]:5555", "tcp://[2001:db8::1]:5555", "tcp://example.com:5555",
        "tcp://127.0.0.1:5555;192.0.2.1:5555", "tcp://127.0.0.1:5555/path",
        "tcp://::1:5555", "tcp://[127.0.0.1]:5555", "tcp://[::1%lo]:5555",
    ],
)
def test_nonlocal_and_wildcard_hosts_rejected_for_bind_and_connect(endpoint):
    with pytest.raises(ValueError):
        RelayConfig(endpoint=endpoint)
    # Validation precedes context/socket allocation and any attempted connect.
    with pytest.raises(ValueError):
        Node("alice", endpoint)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "[::1]", "localhost"])
def test_supported_loopback_addresses_and_bind_only_wildcard_port(host):
    endpoint = f"tcp://{host}:5555"
    assert local_endpoint(endpoint) == endpoint.replace("localhost", "127.0.0.1")
    assert RelayConfig(endpoint=f"tcp://{host}:*")
    with pytest.raises(ValueError, match="port"):
        Node("alice", f"tcp://{host}:*")


@pytest.mark.parametrize(
    "options",
    [
        {"endpoint": "ipc:///tmp/not-in-this-slice"},
        {"endpoint": "tcp://127.0.0.1:bad"},
        {"lease_seconds": 0},
        {"lease_seconds": True},
        {"endpoint": "tcp://127.0.0.1:65536"},
        {"send_hwm": 0},
        {"receive_hwm": -1},
        {"max_payload_bytes": True},
        {"allowed_names": ("@forged",)},
        {"allowed_names": "alice"},
        {"networks": {"red": "alice"}},
        {"deny": "alice,bob"},
        {"deny": ((1, "bob"),)},
        {"networks": {"bad group": ("alice",)}},
        {"deny": (("@unknown", "bob"),)},
    ],
)
def test_invalid_configuration_is_rejected(options):
    with pytest.raises(ValueError):
        RelayConfig(**options)


def test_toml_policy_and_safe_shipped_example(tmp_path: Path):
    config = tmp_path / "relay.toml"
    config.write_text('''endpoint = "tcp://127.0.0.1:*"
allowed_names = ["alice", "bob"]
deny = [["@writers", "bob"]]
[networks]
writers = ["alice"]
''')
    loaded = load_config(config)
    assert loaded.allowed_names == ("alice", "bob")
    assert not loaded.permits("alice", "bob")
    assert loaded.permits("bob", "alice")
    example = Path(str(files("nodalwire") / "examples/local.toml"))
    loaded = load_config(example)
    assert loaded.endpoint == "tcp://127.0.0.1:5555"
    assert not loaded.permits("alice", "observer")


@pytest.mark.parametrize("content", ['allow_nonlocal = true', 'allow_nonlocal = false',
                                     '[curve]', 'secret_key_file = "removed"'])
def test_obsolete_or_unknown_toml_options_explicitly_rejected(tmp_path, content):
    path = tmp_path / "obsolete.toml"
    path.write_text(content)
    with pytest.raises(ValueError, match="unsupported local-only|unknown relay configuration"):
        load_config(path)


def test_removed_api_options_are_not_accepted():
    with pytest.raises(TypeError, match="allow_nonlocal"):
        RelayConfig(allow_nonlocal=True)
    with pytest.raises(TypeError, match="curve"):
        RelayConfig(curve=None)
    with pytest.raises(TypeError, match="curve"):
        Node("alice", "tcp://127.0.0.1:5555", curve=None)
