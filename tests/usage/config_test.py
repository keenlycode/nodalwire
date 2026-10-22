"""Public API usage: load a TOML file and inspect its cooperative routing policy."""

from pathlib import Path

from nodalwire import Relay, load_config


def test_load_local_policy(monkeypatch):
    monkeypatch.setenv("NODALWIRE_ADMIN_TOKEN", "usage-test-only-admin")
    config = load_config(Path(__file__).with_name("local.toml"))
    relay = Relay(config)

    assert relay.config == config
    assert config.endpoint == "tcp://127.0.0.1:5555"
    assert config.allowed_names == ("alice", "bob", "observer")
    assert config.routing_groups == {"writers": ("alice", "bob")}
    assert set(config.networks) == {"default", "writers"}
    assert config.networks["default"].join_verifier is None
    assert config.networks["writers"].join_verifier is None
    assert config.permits("alice", "bob")
    assert not config.permits("alice", "observer")
    assert not config.permits("bob", "observer")
    assert config.permits("observer", "alice")  # Denies are directional.
