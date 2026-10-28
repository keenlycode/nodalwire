"""Source-mode fixtures for authored package-name import examples.

Installed-artifact acceptance is separately exercised by package_smoke.py. These
fixtures expose the reviewed built SDK under its public name without installing
or changing a developer's application.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def node_application(tmp_path):
    sdk = ROOT / "src/nodalwire/client/node"
    assert (sdk / "dist/index.js").is_file(), "Build the matching SDK first"
    namespace = tmp_path / "node_modules/@devcapsule"
    namespace.mkdir(parents=True)
    (namespace / "nodalwire-client").symlink_to(sdk, target_is_directory=True)
    return tmp_path
