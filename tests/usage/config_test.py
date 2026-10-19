"""Public API usage: load a TOML file and inspect its cooperative routing policy."""

from pathlib import Path

from nodalwire import Relay, load_config


def test_load_local_policy():
    config = load_config(Path(__file__).with_name("local.toml"))
    relay = Relay(config)

    assert relay.config is config
    assert config.endpoint == "tcp://127.0.0.1:5555"
    assert config.allowed_names == ("alice", "bob", "observer")
    assert config.networks == {"writers": ("alice", "bob")}
    assert config.permits("alice", "bob")
    assert not config.permits("alice", "observer")
    assert not config.permits("bob", "observer")
    assert config.permits("observer", "alice")  # Denies are directional.
