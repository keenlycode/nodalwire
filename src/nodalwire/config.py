"""Versioned immutable configuration, separate from ephemeral memberships."""

import ipaddress
import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import MappingProxyType

from .credentials import validate_verifier
from .protocol import valid_name

MAX_REVISION = (1 << 53) - 1


def _name_list(names: object) -> bool:
    return isinstance(names, (tuple, list)) and all(valid_name(name) for name in names)


def local_endpoint(endpoint: str, *, bind: bool = False) -> str:
    """Validate before allocating resources; normalize localhost without DNS.

    Only literal loopback addresses (or localhost) are supported. A wildcard
    port is allowed for binds, never connects; wildcard/nonlocal hosts are not.
    """
    if not isinstance(endpoint, str) or not endpoint.startswith("tcp://"):
        raise ValueError("local relay endpoint must use tcp://")
    host, separator, port = endpoint[6:].rpartition(":")
    if not separator or not (
        (bind and port == "*") or (port.isascii() and port.isdecimal() and 1 <= int(port) <= 65535)
    ):
        raise ValueError("invalid TCP endpoint port")
    if host == "localhost":
        host = "127.0.0.1"
    try:
        address = ipaddress.ip_address(host[1:-1] if host.startswith("[") else host)
    except ValueError as exc:
        raise ValueError("endpoint must use a literal loopback address or localhost") from exc
    if not address.is_loopback or "%" in host:
        raise ValueError("endpoint must be loopback-only")
    expected = f"[{address}]" if address.version == 6 else str(address)
    if host != expected:
        raise ValueError("invalid TCP loopback address syntax")
    return f"tcp://{expected}:{port}"


@dataclass(frozen=True)
class NetworkConfig:
    join_verifier: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.join_verifier is not None:
            validate_verifier(self.join_verifier)


@dataclass(frozen=True)
class RelayConfig:
    endpoint: str = "tcp://127.0.0.1:5555"
    lease_seconds: float = 10.0
    send_hwm: int = 64
    receive_hwm: int = 64
    max_payload_bytes: int = 1_048_576
    allowed_names: tuple[str, ...] | None = None
    networks: Mapping[str, NetworkConfig] = field(default_factory=dict)
    deny: tuple[tuple[str, str], ...] = ()
    config_version: int = 2
    revision: int = 0
    admin_endpoint: str = "tcp://127.0.0.1:5556"
    admin_verifier: str | None = field(default=None, repr=False)
    routing_groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.config_version) is not int or self.config_version != 2:
            raise ValueError("configuration migration required: config_version must be 2")
        if type(self.revision) is not int or not 0 <= self.revision <= MAX_REVISION:
            raise ValueError("invalid configuration revision")
        for name in ("endpoint", "admin_endpoint"):
            object.__setattr__(self, name, local_endpoint(getattr(self, name), bind=True))
        if (
            type(self.lease_seconds) not in (float, int)
            or not 0.1 <= self.lease_seconds <= 3600
            or not math.isfinite(self.lease_seconds)
        ):
            raise ValueError("lease_seconds must be finite and between 0.1 and 3600")
        for name in ("send_hwm", "receive_hwm", "max_payload_bytes"):
            value = getattr(self, name)
            maximum = (1 << 31) - (4096 if name == "max_payload_bytes" else 1)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("invalid native transport limit")
        if self.allowed_names is not None:
            if not _name_list(self.allowed_names):
                raise ValueError("allowed_names must be an array of valid names")
            object.__setattr__(self, "allowed_names", tuple(self.allowed_names))
        if self.admin_verifier is not None:
            validate_verifier(self.admin_verifier)
        if not isinstance(self.routing_groups, Mapping):
            raise ValueError("routing_groups must map static groups to member arrays")
        groups = {}
        for group, members in self.routing_groups.items():
            if not valid_name(group) or not _name_list(members):
                raise ValueError("invalid static routing group")
            groups[group] = tuple(members)
        object.__setattr__(self, "routing_groups", MappingProxyType(groups))
        if not isinstance(self.networks, Mapping):
            raise ValueError("networks must map names to policy tables")
        networks = {}
        for name, policy in self.networks.items():
            if not valid_name(name):
                raise ValueError("invalid network name")
            if not isinstance(policy, NetworkConfig):
                raise ValueError("configuration migration required: networks need policy tables")
            networks[name] = NetworkConfig(policy.join_verifier)
        networks.setdefault("default", NetworkConfig())
        object.__setattr__(self, "networks", MappingProxyType(networks))
        if not isinstance(self.deny, (tuple, list)):
            raise ValueError("deny must be an array of directional rules")
        for rule in self.deny:
            if (
                not isinstance(rule, (tuple, list))
                or len(rule) != 2
                or any(not self._valid_selector(selector) for selector in rule)
            ):
                raise ValueError("deny entries need two name, @routing_group or * selectors")
        object.__setattr__(self, "deny", tuple(tuple(rule) for rule in self.deny))

    def _valid_selector(self, selector: str) -> bool:
        return isinstance(selector, str) and (
            selector == "*"
            or valid_name(selector)
            or (selector.startswith("@") and selector[1:] in self.routing_groups)
        )

    def _matches(self, selector: str, name: str) -> bool:
        if selector == "*":
            return True
        if selector.startswith("@"):
            return name in self.routing_groups[selector[1:]]
        return selector == name

    def permits(self, source: str, destination: str) -> bool:
        return not any(
            self._matches(left, source) and self._matches(right, destination)
            for left, right in self.deny
        )


def load_config(path: Path) -> RelayConfig:
    """Load strict v2 TOML; legacy static networks are never memberships."""
    try:
        with path.open("rb") as source:
            data = tomllib.load(source)
    except tomllib.TOMLDecodeError:
        raise ValueError("invalid TOML configuration") from None
    if type(data.get("config_version")) is not int or data["config_version"] != 2:
        raise ValueError("configuration migration required: config_version must be 2")
    if data.keys() - {item.name for item in fields(RelayConfig)}:
        raise ValueError("unknown relay configuration field")
    policies = data.get("networks", {})
    if not isinstance(policies, dict):
        raise ValueError("networks must map names to policy tables")
    networks = {}
    for name, policy in policies.items():
        if not isinstance(policy, dict) or policy.keys() - {"join_verifier"}:
            raise ValueError("configuration migration required: networks need policy tables")
        networks[name] = NetworkConfig(**policy)
    return RelayConfig(**{**data, "networks": networks})
