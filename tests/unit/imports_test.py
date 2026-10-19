"""The source layout preserves the public Python API and module exports."""

import nodalwire
from nodalwire.client import Message, Node
from nodalwire.client.python import Message as PythonMessage
from nodalwire.client.python import Node as PythonNode
from nodalwire.server import Relay


def test_public_exports_match_language_and_service_packages():
    assert nodalwire.Node is Node is PythonNode
    assert nodalwire.Message is Message is PythonMessage
    assert nodalwire.Relay is Relay
