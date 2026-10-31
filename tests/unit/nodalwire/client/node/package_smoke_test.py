"""Fast failure boundaries for the installed-artifact smoke command."""

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[5]
SMOKE = ROOT / "tests/integration/nodalwire/client/node/package_smoke.py"


@pytest.mark.parametrize("conflicting_skip", [False, True])
def test_python_artifact_invalid_arguments_fail_before_build(tmp_path, conflicting_skip):
    artifact = tmp_path / "nodalwire.whl"
    arguments = ["--python-artifact", str(artifact)]
    if conflicting_skip:
        artifact.touch()
        arguments.append("--skip-interop")
    result = subprocess.run(
        [sys.executable, str(SMOKE), *arguments],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 2
    assert not list(tmp_path.glob("*.tgz"))


def test_distribution_inventory_rejects_stale_and_missing_outputs(tmp_path):
    spec = importlib.util.spec_from_file_location("artifact_smoke", SMOKE)
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    sources, dist = tmp_path / "src", tmp_path / "dist"
    sources.mkdir()
    dist.mkdir()
    (sources / "index.ts").write_text("export const value = 1;\n")
    (dist / "index.js").write_text("export const value = 1;\n")
    (dist / "index.d.ts").write_text("export declare const value = 1;\n")
    smoke.validate_distribution(dist, sources)
    obsolete = dist / "obsolete.js"
    obsolete.write_text("export const legacy = true;\n")
    with pytest.raises(ValueError, match="extra="):
        smoke.validate_distribution(dist, sources)
    obsolete.unlink()
    (dist / "index.d.ts").unlink()
    with pytest.raises(ValueError, match="missing="):
        smoke.validate_distribution(dist, sources)


def write_fake_wheel(path, version="0.3.0.dev0"):
    with ZipFile(path, "w") as wheel:
        wheel.writestr(
            f"nodalwire-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: nodalwire\nVersion: {version}\n",
        )


def test_installed_evidence_cannot_use_checkout_as_consumer(tmp_path, pytestconfig):
    artifact = tmp_path / "nodalwire.whl"
    write_fake_wheel(artifact)
    cache = pytestconfig.cache.mkdir("artifact-boundary")
    with tempfile.TemporaryDirectory(prefix="artifact-test-", dir=cache) as work:
        result = subprocess.run(
            [sys.executable, str(SMOKE), "--python-artifact", str(artifact),
             "--python-version", "0.3.0.dev0"],
            cwd=tmp_path, env={**os.environ, "NODALWIRE_EVIDENCE_DIR": work},
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 2
        assert "outside checkout" in result.stderr
        assert not list(Path(work).glob("*.tgz"))


def test_python_artifact_expected_version_is_independent_and_exact(tmp_path):
    artifact = tmp_path / "nodalwire.whl"
    write_fake_wheel(artifact)
    result = subprocess.run(
        [sys.executable, str(SMOKE), "--python-artifact", str(artifact),
         "--python-version", "0.3.0-dev.0"],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 2
    assert "independent expected name/version" in result.stderr
    assert not list(tmp_path.glob("*.tgz"))
