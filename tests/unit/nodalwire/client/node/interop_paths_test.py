"""Behavioral boundaries for installed artifact import provenance."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture
def validate_paths(monkeypatch):
    monkeypatch.delenv("NODALWIRE_PYTHON_INSTALLED", raising=False)
    path = ROOT / "tests/integration/nodalwire/client/node/interop.py"
    spec = importlib.util.spec_from_file_location("interop_path_fixture", path)
    module = importlib.util.module_from_spec(spec)
    original = sys.path[:]
    try:
        spec.loader.exec_module(module)
        yield module.validate_installed_paths
    finally:
        sys.path[:] = original


def test_task_managed_stdlib_is_allowed_but_package_stays_external(validate_paths, tmp_path):
    repo = tmp_path / "repo"
    runtime = repo / ".agents/python/managed"
    venv = tmp_path / "consumer/venv"
    validate_paths(venv / "site-packages/nodalwire", venv, runtime,
                   [runtime / "lib/python3.12", venv / "site-packages"], repo, venv.parent)


def test_external_runtime_is_allowed(validate_paths, tmp_path):
    repo, venv, runtime = (tmp_path / name for name in ("repo", "consumer/venv", "runtime"))
    validate_paths(venv / "site-packages/nodalwire", venv, runtime,
                   [runtime / "lib", venv / "site-packages"], repo, venv.parent)


@pytest.mark.parametrize("leak", ["src", "src/nodalwire", ".", ".agents/unrelated"])
def test_source_root_and_unrelated_checkout_paths_are_rejected(validate_paths, tmp_path, leak):
    repo = tmp_path / "repo"
    venv = tmp_path / "consumer/venv"
    with pytest.raises(AssertionError):
        validate_paths(venv / "site-packages/nodalwire", venv, repo / ".agents/managed",
                       [repo / leak], repo, venv.parent)


@pytest.mark.parametrize("runtime_path", [".", "src/python"])
def test_repository_source_cannot_be_declared_runtime(validate_paths, tmp_path, runtime_path):
    repo, venv = tmp_path / "repo", tmp_path / "consumer/venv"
    with pytest.raises(AssertionError):
        validate_paths(venv / "site-packages/nodalwire", venv, repo / runtime_path,
                       [], repo, venv.parent)


def test_checkout_package_is_rejected(validate_paths, tmp_path):
    repo, venv = tmp_path / "repo", tmp_path / "consumer/venv"
    with pytest.raises(AssertionError):
        validate_paths(repo / "src/nodalwire", venv, tmp_path / "runtime", [], repo, venv.parent)


def test_checkout_consumer_is_rejected(validate_paths, tmp_path):
    repo, venv = tmp_path / "repo", tmp_path / "consumer/venv"
    with pytest.raises(AssertionError):
        validate_paths(venv / "site-packages/nodalwire", venv, tmp_path / "runtime", [], repo, repo)


def test_provenance_helper_import_needs_no_source_or_installed_environment(monkeypatch):
    monkeypatch.delenv("NODALWIRE_PYTHON_SOURCE", raising=False)
    monkeypatch.delenv("NODALWIRE_PYTHON_INSTALLED", raising=False)
    path = ROOT / "tests/integration/nodalwire/client/node/interop.py"
    spec = importlib.util.spec_from_file_location("interop_without_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.validate_installed_paths)
    with pytest.raises(RuntimeError, match="NODALWIRE_PYTHON_SOURCE"):
        module.load_interop_runtime()
