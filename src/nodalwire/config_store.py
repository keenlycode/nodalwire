"""Serialized memory or same-file configuration commits with honest cutoffs.

The synchronous lock covers validation, filesystem work and publication. This can
briefly block a relay loop. External edit detection is not a cross-process lock.
"""

import hashlib
import json
import os
import stat
import tempfile
import threading
from dataclasses import fields, replace
from pathlib import Path

from .config import MAX_REVISION, RelayConfig, load_config
from .credentials import AdminCredential, make_verifier, resolve_admin_credential, verify_token


class ConfigStoreError(Exception):
    code = "configuration_error"
    outcome = "no_effect"

    def __init__(self, revision: int) -> None:
        self.revision = revision
        super().__init__(self.code)


class ConfigConflict(ConfigStoreError):
    code = "revision_conflict"


class EnvironmentManaged(ConfigStoreError):
    code = "environment_managed"


class PersistenceError(ConfigStoreError):
    code = "persistence_failed"


class PersistenceIndeterminate(ConfigStoreError):
    code = "persistence_indeterminate"
    outcome = "indeterminate"

    def __init__(self, committed_config: RelayConfig) -> None:
        self.committed_config = committed_config
        super().__init__(committed_config.revision)


def _read_regular(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("configuration must be a regular non-symlink file")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            return source.read()
    finally:
        os.close(descriptor)


def _fingerprint(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _toml(config: RelayConfig) -> bytes:
    """Serialize the closed schema completely; comments/layout are not retained."""

    def value(item: object) -> str:
        if isinstance(item, (tuple, list)):
            return "[" + ", ".join(value(part) for part in item) + "]"
        return json.dumps(item, ensure_ascii=True, allow_nan=False)

    lines = []
    for name in (
        "config_version",
        "revision",
        "endpoint",
        "admin_endpoint",
        "lease_seconds",
        "send_hwm",
        "receive_hwm",
        "max_payload_bytes",
        "allowed_names",
        "deny",
        "admin_verifier",
    ):
        item = getattr(config, name)
        if item is not None:
            lines.append(f"{name} = {value(item)}")
    lines.append("\n[routing_groups]")
    for name, members in sorted(config.routing_groups.items()):
        lines.append(f"{value(name)} = {value(members)}")
    for name, policy in sorted(config.networks.items()):
        lines.append(f"\n[networks.{value(name)}]")
        if policy.join_verifier is not None:
            lines.append(f"join_verifier = {value(policy.join_verifier)}")
    return ("\n".join(lines) + "\n").encode("utf-8")


class ConfigStore:
    def __init__(self, config: RelayConfig, path: Path | None = None, *, environ=None) -> None:
        if not isinstance(config, RelayConfig):
            raise ValueError("invalid relay configuration")
        self._config = replace(config)  # Revalidate and detach caller containers.
        self._admin = resolve_admin_credential(self._config, environ)
        self._lock = threading.RLock()
        self._path = Path(os.path.abspath(path)) if path is not None else None
        self._fingerprint: bytes | None = None
        if self._path is not None:
            try:
                original = _read_regular(self._path)
                loaded = load_config(self._path)
                if loaded != self._config or _read_regular(self._path) != original:
                    raise ValueError("supplied configuration does not match file")
            except OSError:
                raise ValueError("cannot read regular configuration file") from None
            self._fingerprint = _fingerprint(original)

    @property
    def config(self) -> RelayConfig:
        return self.snapshot()

    @property
    def revision(self) -> int:
        return self.snapshot().revision

    @property
    def admin_source(self) -> str:
        return self._admin.source

    def snapshot(self) -> RelayConfig:
        with self._lock:
            return self._config

    def authenticate_admin(self, token: str) -> bool:
        with self._lock:
            return verify_token(token, self._admin.verifier)

    def join_allowed(self, network: str, credential: str | None = None) -> bool:
        with self._lock:
            policy = self._config.networks.get(network)
            if policy is None:
                return False
            return policy.join_verifier is None or verify_token(credential, policy.join_verifier)

    def redacted(self) -> dict:
        with self._lock:
            config = self._config
            result = {
                item.name: getattr(config, item.name)
                for item in fields(config)
                if item.name not in {"admin_verifier", "networks", "routing_groups"}
            }
            result["routing_groups"] = dict(config.routing_groups)
            result["networks"] = {
                name: {"protected": policy.join_verifier is not None}
                for name, policy in config.networks.items()
            }
            result["admin_source"] = self._admin.source
            result["admin_configured"] = True
            return result

    def _publish(self, candidate: RelayConfig) -> None:
        self._config = candidate
        if self._admin.source == "config":
            self._admin = AdminCredential(candidate.admin_verifier, "config")

    def commit(self, candidate: RelayConfig, *, expected_revision: int) -> RelayConfig:
        with self._lock:
            current = self._config
            if type(expected_revision) is not int or expected_revision != current.revision:
                raise ConfigConflict(current.revision)
            if not isinstance(candidate, RelayConfig):
                raise ValueError("invalid relay configuration")
            candidate = replace(candidate)
            if candidate.revision != current.revision:
                raise ConfigConflict(current.revision)
            for item in fields(current):
                if item.name not in {"revision", "networks", "admin_verifier"}:
                    if getattr(candidate, item.name) != getattr(current, item.name):
                        raise ValueError("startup configuration cannot change at runtime")
            if (
                self._admin.source == "environment"
                and candidate.admin_verifier != current.admin_verifier
            ):
                raise EnvironmentManaged(current.revision)
            if self._admin.source == "config" and candidate.admin_verifier is None:
                raise ValueError("administrator verifier required")
            if current.revision == MAX_REVISION:
                raise ValueError("configuration revision exhausted")
            candidate = replace(candidate, revision=current.revision + 1)
            if self._path is None:
                self._publish(candidate)
                return candidate
            try:
                observed = _read_regular(self._path)
            except FileNotFoundError:
                raise ConfigConflict(current.revision) from None
            except (OSError, ValueError):
                raise PersistenceError(current.revision) from None
            if _fingerprint(observed) != self._fingerprint:
                raise ConfigConflict(current.revision)
            data = _toml(candidate)
            temporary = None
            replaced = False
            try:
                descriptor, temporary = tempfile.mkstemp(
                    prefix=f".{self._path.name}.", suffix=".tmp", dir=self._path.parent
                )
                try:
                    target = os.fdopen(descriptor, "wb")
                except OSError:
                    os.close(descriptor)
                    raise
                with target:
                    target.write(data)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temporary, self._path)
                replaced = True
                self._fingerprint = _fingerprint(data)
                parent = os.open(self._path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(parent)
                finally:
                    os.close(parent)
            except OSError:
                if replaced:
                    self._publish(candidate)
                    raise PersistenceIndeterminate(candidate) from None
                raise PersistenceError(current.revision) from None
            finally:
                if temporary is not None and not replaced:
                    try:
                        os.unlink(temporary)
                    except OSError:
                        pass  # Cleanup failure cannot relabel the mutation outcome.
            self._publish(candidate)
            return candidate

    def rotate_admin(self, token: str, *, expected_revision: int) -> RelayConfig:
        with self._lock:
            if type(expected_revision) is not int or expected_revision != self._config.revision:
                raise ConfigConflict(self._config.revision)
            if self._admin.source == "environment":
                raise EnvironmentManaged(self._config.revision)
            candidate = replace(self._config, admin_verifier=make_verifier(token))
            return self.commit(candidate, expected_revision=expected_revision)
