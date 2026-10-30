import dataclasses

import pytest

from nodalwire import Message


def test_native_message_is_frozen_and_requires_all_native_fields():
    message = Message(id="1" * 32, sender="alpha", network="red", payload=b"\x00\xff")
    assert message.reply_to is None
    assert message.payload == b"\x00\xff"
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.id = "2" * 32
    with pytest.raises(TypeError):
        Message(sender="alpha", payload=b"old missing metadata")
