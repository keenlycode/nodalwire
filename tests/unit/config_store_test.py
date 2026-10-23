import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

import nodalwire.config_store as module
from nodalwire.config import MAX_REVISION, NetworkConfig, RelayConfig, load_config
from nodalwire.config_store import (
    ConfigConflict,
    ConfigStore,
    EnvironmentManaged,
    PersistenceError,
    PersistenceIndeterminate,
)
from nodalwire.credentials import make_verifier


@pytest.fixture(scope="module")
def verifier():
    return make_verifier("test-only-admin")


@pytest.fixture
def file_store(tmp_path, verifier):
    path = tmp_path / "relay.toml"
    path.write_text(f'''config_version = 2
admin_verifier = "{verifier}"
endpoint = "tcp://127.0.0.2:*"
admin_endpoint = "tcp://127.0.0.1:*"
lease_seconds = 3.5
send_hwm = 7
receive_hwm = 9
max_payload_bytes = 2048
allowed_names = ["alice", "bob"]
deny = [["@writers", "bob"]]
[routing_groups]
writers = ["alice"]
[networks.red]
''')
    return path, ConfigStore(load_config(path), path, environ={})


def changed(store):
    return replace(store.snapshot(), networks={**store.config.networks, "blue": NetworkConfig()})


def test_memory_mode_has_no_files_and_validates_admin(tmp_path, monkeypatch, verifier):
    monkeypatch.chdir(tmp_path)
    store = ConfigStore(RelayConfig(admin_verifier=verifier), environ={})
    assert store.revision == 0
    assert store.authenticate_admin("test-only-admin")
    assert not store.authenticate_admin("wrong")
    assert not store.authenticate_admin(None)
    committed = store.commit(changed(store), expected_revision=0)
    assert store.snapshot() is committed
    assert committed.revision == 1
    assert list(tmp_path.iterdir()) == []
    assert store.join_allowed("blue")
    assert not store.join_allowed("missing")
    with pytest.raises(ValueError):
        ConfigStore(RelayConfig(), environ={})


def test_same_file_complete_roundtrip_and_restart(file_store, verifier):
    path, store = file_store
    original = store.snapshot()
    join = make_verifier("test-only-join")
    candidate = replace(
        original, networks={"default": NetworkConfig(join), "blue": NetworkConfig()}
    )
    result = store.commit(candidate, expected_revision=0)
    assert result.revision == 1
    assert load_config(path) == result
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    for field in (
        "endpoint",
        "admin_endpoint",
        "lease_seconds",
        "send_hwm",
        "receive_hwm",
        "max_payload_bytes",
        "allowed_names",
        "deny",
        "routing_groups",
    ):
        assert getattr(result, field) == getattr(original, field)
    restarted = ConfigStore(load_config(path), path, environ={})
    assert restarted.revision == 1
    assert restarted.join_allowed("default", "test-only-join")
    assert not restarted.join_allowed("default")
    assert restarted.authenticate_admin("test-only-admin")
    assert not restarted.authenticate_admin("test-only-join")
    assert "test-only-join" not in path.read_text()
    assert list(path.parent.iterdir()) == [path]


def test_environment_separate_and_all_rotation_paths_rejected(file_store, verifier):
    path, initial = file_store
    store = ConfigStore(initial.config, path, environ={"NODALWIRE_ADMIN_TOKEN": "env-only-secret"})
    assert store.admin_source == "environment"
    assert store.authenticate_admin("env-only-secret")
    assert not store.authenticate_admin("test-only-admin")
    with pytest.raises(EnvironmentManaged) as error:
        store.rotate_admin("new-token", expected_revision=0)
    assert error.value.code == "environment_managed"
    assert error.value.outcome == "no_effect"
    with pytest.raises(EnvironmentManaged):
        store.commit(
            replace(store.config, admin_verifier=make_verifier("new-token")), expected_revision=0
        )
    store.commit(changed(store), expected_revision=0)
    assert load_config(path).admin_verifier == verifier
    assert "env-only-secret" not in path.read_text()
    assert store._admin.verifier not in path.read_text()
    for invalid in ("", "bad token", "é"):
        with pytest.raises(ValueError):
            ConfigStore(initial.config, environ={"NODALWIRE_ADMIN_TOKEN": invalid})


def test_redaction_and_safe_reprs(file_store, verifier):
    _, store = file_store
    join = make_verifier("join-only-token")
    store.commit(replace(store.config, networks={"red": NetworkConfig(join)}), expected_revision=0)
    status = store.redacted()
    assert status["networks"]["red"] == {"protected": True}
    assert status["admin_source"] == "config"
    assert status["admin_configured"] is True
    text = json.dumps(status) + repr(store.config)
    for forbidden in (
        "admin_verifier",
        "join_verifier",
        verifier,
        join,
        "test-only-admin",
        "join-only-token",
    ):
        assert forbidden not in text
    status["networks"].clear()
    status["routing_groups"].clear()
    assert "red" in store.config.networks
    assert "writers" in store.config.routing_groups


def test_revision_conflict_and_single_winner(file_store):
    path, store = file_store
    candidate = changed(store)

    def attempt():
        try:
            return store.commit(candidate, expected_revision=0).revision
        except ConfigConflict as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(map(str, results)) == ["1", "revision_conflict"]
    assert load_config(path).revision == 1
    for expected in (True, -1, 0, 1.0):
        with pytest.raises(ConfigConflict):
            store.commit(changed(store), expected_revision=expected)
    with pytest.raises(ConfigConflict):
        store.commit(replace(store.config, revision=0), expected_revision=1)


def test_external_edit_or_deletion_never_overwritten(file_store):
    path, store = file_store
    edited = path.read_bytes() + b"\n# external edit\n"
    path.write_bytes(edited)
    with pytest.raises(ConfigConflict):
        store.commit(changed(store), expected_revision=0)
    assert path.read_bytes() == edited
    assert store.revision == 0
    path.unlink()
    with pytest.raises(ConfigConflict):
        store.commit(changed(store), expected_revision=0)
    assert not path.exists()


@pytest.mark.parametrize(
    "stage", ["mkstemp", "fdopen", "write", "flush", "close", "file_fsync", "replace"]
)
def test_precommit_failures_leave_live_and_file_unchanged(file_store, monkeypatch, stage):
    path, store = file_store
    before = path.read_bytes()
    original = store.config

    def fail(*args, **kwargs):
        raise OSError("sensitive-unfiltered-os-detail")

    if stage == "mkstemp":
        monkeypatch.setattr(module.tempfile, "mkstemp", fail)
    elif stage == "replace":
        monkeypatch.setattr(module.os, "replace", fail)
    elif stage == "file_fsync":
        monkeypatch.setattr(module.os, "fsync", fail)
    else:
        original_fdopen = module.os.fdopen

        class BadWriter:
            def __init__(self, target):
                self.target = target

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.target.close()
                if stage == "close":
                    fail()

            def write(self, data):
                if stage == "write":
                    fail()
                return self.target.write(data)

            def flush(self):
                if stage == "flush":
                    fail()
                return self.target.flush()

            def fileno(self):
                return self.target.fileno()

        def fdopen(fd, mode, **kwargs):
            if mode == "wb" and stage == "fdopen":
                fail()
            target = original_fdopen(fd, mode, **kwargs)
            return BadWriter(target) if mode == "wb" else target

        monkeypatch.setattr(module.os, "fdopen", fdopen)
    with pytest.raises(PersistenceError) as error:
        store.commit(changed(store), expected_revision=0)
    assert error.value.outcome == "no_effect"
    assert error.value.revision == 0
    assert "sensitive-unfiltered" not in str(error.value)
    assert store.config is original
    assert path.read_bytes() == before
    assert list(path.parent.iterdir()) == [path]


def test_postreplace_fsync_failure_publishes_but_is_indeterminate(file_store, monkeypatch):
    path, store = file_store
    original_fsync = module.os.fsync

    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("do-not-leak")
        original_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", fsync)
    new_verifier = make_verifier("rotated-admin")
    with pytest.raises(PersistenceIndeterminate) as error:
        store.commit(replace(store.config, admin_verifier=new_verifier), expected_revision=0)
    assert error.value.code == "persistence_indeterminate"
    assert error.value.outcome == "indeterminate"
    assert error.value.revision == 1
    assert error.value.committed_config is store.config
    assert load_config(path) == store.config
    assert store.authenticate_admin("rotated-admin")
    assert not store.authenticate_admin("test-only-admin")
    assert "do-not-leak" not in str(error.value)
    assert list(path.parent.iterdir()) == [path]
    # Explicit stale retry fails, not a second mutation.
    with pytest.raises(ConfigConflict):
        store.commit(changed(store), expected_revision=0)


def test_admin_rotation_and_runtime_boundaries(file_store):
    path, store = file_store
    for updates in (
        {"send_hwm": 10},
        {"endpoint": "tcp://127.0.0.1:3333"},
        {"allowed_names": None},
        {"admin_verifier": None},
    ):
        with pytest.raises(ValueError):
            store.commit(replace(store.config, **updates), expected_revision=0)
    rotated = store.rotate_admin("replacement-token", expected_revision=0)
    assert rotated.revision == 1
    assert store.authenticate_admin("replacement-token")
    assert not store.authenticate_admin("test-only-admin")
    assert "replacement-token" not in path.read_text()
    assert ConfigStore(load_config(path), path, environ={}).authenticate_admin("replacement-token")


def test_revision_exhaustion_and_default_normalization(verifier):
    store = ConfigStore(RelayConfig(admin_verifier=verifier, revision=MAX_REVISION), environ={})
    with pytest.raises(ValueError, match="revision exhausted"):
        store.commit(store.config, expected_revision=MAX_REVISION)
    assert "default" in replace(store.config, networks={}).networks


def test_reject_symlink_directory_and_mismatched_file(file_store, tmp_path):
    path, store = file_store
    link = tmp_path / "link.toml"
    link.symlink_to(path)
    for invalid in (link, tmp_path):
        with pytest.raises(ValueError):
            ConfigStore(store.config, invalid, environ={})
    with pytest.raises(ValueError, match="does not match"):
        ConfigStore(replace(store.config, revision=1), path, environ={})


def test_directory_open_failure_after_replace_is_indeterminate(file_store, monkeypatch):
    path, store = file_store
    original_open = module.os.open

    def opened(path, flags, *args, **kwargs):
        if flags & os.O_DIRECTORY:
            raise OSError("parent-unavailable")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", opened)
    with pytest.raises(PersistenceIndeterminate) as error:
        store.commit(changed(store), expected_revision=0)
    assert error.value.revision == 1
    assert load_config(path) == store.snapshot()
    assert "blue" in store.config.networks


def test_commit_after_explicit_indeterminate_reconciliation(file_store, monkeypatch):
    path, store = file_store
    original_fsync = module.os.fsync

    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("parent-sync-failed")
        return original_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", fsync)
    with pytest.raises(PersistenceIndeterminate):
        store.commit(changed(store), expected_revision=0)
    monkeypatch.setattr(module.os, "fsync", original_fsync)
    # This is a new explicit mutation after reading the visible committed revision.
    reconciled = store.snapshot()
    result = store.commit(reconciled, expected_revision=reconciled.revision)
    assert result.revision == 2
    assert load_config(path) == result
