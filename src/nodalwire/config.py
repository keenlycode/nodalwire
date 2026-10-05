"""Startup-only relay policy and native transport limits (TOML configuration)."""

import ipaddress
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from .protocol import valid_name


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
        (bind and port == "*")
        or (port.isascii() and port.isdecimal() and 1 <= int(port) <= 65535)
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
class RelayConfig:
    endpoint: str = "tcp://127.0.0.1:5555"
    lease_seconds: float = 10.0
    send_hwm: int = 64
    receive_hwm: int = 64
    max_payload_bytes: int = 1_048_576
    allowed_names: tuple[str, ...] | None = None
    networks: dict[str, tuple[str, ...]] = field(default_factory=dict)
    deny: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint", local_endpoint(self.endpoint, bind=True))
        if type(self.lease_seconds) not in (float, int) or not 0.1 <= self.lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 0.1 and 3600")
        for name in ("send_hwm", "receive_hwm", "max_payload_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.allowed_names is not None and not _name_list(self.allowed_names):
            raise ValueError("allowed_names must be an array of valid names")
        if not isinstance(self.networks, dict):
            raise ValueError("networks must map group names to member arrays")
        for group, members in self.networks.items():
            if not valid_name(group) or not _name_list(members):
                raise ValueError("invalid network or member name array")
        if not isinstance(self.deny, (tuple, list)):
            raise ValueError("deny must be an array of directional rules")
        for rule in self.deny:
            if (
                not isinstance(rule, (tuple, list))
                or len(rule) != 2
                or any(not self._valid_selector(selector) for selector in rule)
            ):
                raise ValueError("deny entries need two name, @network or * selectors")

    def _valid_selector(self, selector: str) -> bool:
        return isinstance(selector, str) and (
            selector == "*"
            or valid_name(selector)
            or (selector.startswith("@") and selector[1:] in self.networks)
        )

    def _matches(self, selector: str, name: str) -> bool:
        if selector == "*":
            return True
        if selector.startswith("@"):
            return name in self.networks[selector[1:]]
        return selector == name

    def permits(self, source: str, destination: str) -> bool:
        return not any(
            self._matches(left, source) and self._matches(right, destination)
            for left, right in self.deny
        )


def load_config(path: Path) -> RelayConfig:
    """Load cooperative local policy once; obsolete/unknown options are errors."""
    with path.open("rb") as source:
        data = tomllib.load(source)
    obsolete = {"curve", "allow_nonlocal"}.intersection(data)
    if obsolete:
        raise ValueError(
            f"unsupported local-only configuration: {', '.join(sorted(obsolete))}; "
            "security mode and nonlocal endpoints have been removed"
        )
    unknown = data.keys() - {item.name for item in fields(RelayConfig)}
    if unknown:
        raise ValueError(f"unknown relay configuration: {', '.join(sorted(unknown))}")
    config = RelayConfig(**data)  # Validate arrays before converting; strings aren't arrays.
    return RelayConfig(
        **{
            **data,
            "allowed_names": None if config.allowed_names is None else tuple(config.allowed_names),
            "networks": {name: tuple(members) for name, members in config.networks.items()},
            "deny": tuple(tuple(rule) for rule in config.deny),
        }
    )
