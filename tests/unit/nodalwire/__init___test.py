def test_public_imports_preserved_and_new_client_contracts_available():
    import nodalwire
    from nodalwire.client import Envelope, MembershipReceipt, Message, Node
    from nodalwire.client.python import Message as PythonMessage
    from nodalwire.client.python import Node as PythonNode
    from nodalwire.client.python import decode_envelope, encode_envelope
    from nodalwire.server import Relay

    assert nodalwire.Node is Node is PythonNode
    assert nodalwire.Message is Message is PythonMessage
    assert nodalwire.Relay is Relay
    assert nodalwire.Envelope is Envelope
    assert nodalwire.MembershipReceipt is MembershipReceipt
    assert nodalwire.decode_envelope is decode_envelope
    assert nodalwire.encode_envelope is encode_envelope
    assert nodalwire.AdminClient and nodalwire.AdminError and nodalwire.AdminReceipt
    assert nodalwire.RelayConfig and nodalwire.load_config
    assert nodalwire.RelayError and nodalwire.ReceiptTimeout
    assert Message("name", b"payload").network == "default"
