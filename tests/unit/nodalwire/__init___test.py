from dataclasses import fields


def test_public_imports_preserved_and_native_message_contract_available():
    import nodalwire
    import nodalwire.client as client
    import nodalwire.client.python as python
    from nodalwire.server import Relay

    assert nodalwire.Node is client.Node is python.Node
    assert nodalwire.Message is client.Message is python.Message
    assert nodalwire.MembershipReceipt is client.MembershipReceipt is python.MembershipReceipt
    assert nodalwire.Relay is Relay
    assert nodalwire.AdminClient and nodalwire.AdminError and nodalwire.AdminReceipt
    assert nodalwire.RelayConfig and nodalwire.load_config
    assert nodalwire.RelayError and nodalwire.ReceiptTimeout
    assert [field.name for field in fields(nodalwire.Message)] == [
        "id", "sender", "network", "payload", "reply_to",
    ]
    for module in (nodalwire, client, python):
        for removed in ("Envelope", "decode_envelope", "encode_envelope"):
            assert not hasattr(module, removed)
    message = nodalwire.Message(id="a" * 32, sender="name", network="default", payload=b"raw")
    assert message.reply_to is None
