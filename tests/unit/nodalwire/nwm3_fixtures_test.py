"""Check shared NWM3 fixture integrity, not unimplemented protocol behavior."""

import base64
import json
import re
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "nwm3" / "wire.json"
WIRE = json.loads(FIXTURE.read_text())
ID = re.compile(rb"[0-9a-f]{32}\Z")


def decode_frame(frame):
    assert isinstance(frame, dict) and len(frame) == 1
    if "ascii" in frame:
        assert isinstance(frame["ascii"], str)
        return frame["ascii"].encode("ascii")
    assert set(frame) == {"hex"}
    assert isinstance(frame["hex"], str)
    assert re.fullmatch(r"(?:[0-9a-f]{2})*", frame["hex"])
    return bytes.fromhex(frame["hex"])


def decode_frames(frames):
    return [decode_frame(frame) for frame in frames]


def test_fixture_encoding_and_schema():
    assert WIRE["schema_version"] == 1
    assert WIRE["protocol"] == "NWM3"

    def visit(value):
        if isinstance(value, dict):
            if "ascii" in value or "hex" in value:
                decode_frame(value)
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(WIRE)


@pytest.mark.parametrize("route", WIRE["routes"], ids=lambda item: item["name"])
def test_routed_triplets_preserve_bytes_and_identity(route):
    sent, received, receipt = map(
        decode_frames, (route["send"], route["data"], route["receipt"])
    )
    assert len(sent) == len(received) == 8
    assert sent[:2] == [b"NWM3", b"SEND"]
    assert received[:2] == [b"NWM3", b"DATA"]
    assert receipt == [b"NWM3", b"OK", sent[2], sent[3]]
    assert ID.fullmatch(sent[3])
    assert sent[6] == b"" or ID.fullmatch(sent[6])
    assert received[3:5] == sent[3:5]
    assert received[6:] == sent[6:]
    assert len(sent[7]) <= WIRE["context"]["max_payload_bytes"]
    assert sent[5].decode("ascii") == route["destination"]
    assert received[5].decode("ascii") == route["source"]
    registrations = {item["name"]: item for item in WIRE["context"]["registrations"]}
    assert sent[2].decode("ascii") == registrations[route["source"]]["token"]
    assert received[2].decode("ascii") == registrations[route["destination"]]["token"]
    assert route["message"] == {
        "id": sent[3].decode("ascii"),
        "reply_to": sent[6].decode("ascii") if sent[6] else None,
        "network": sent[4].decode("ascii"),
        "sender": route["source"],
        "payload_hex": sent[7].hex(),
    }


@pytest.mark.parametrize("case", WIRE["relay_rejections"], ids=lambda item: item["name"])
def test_rejection_fixture_correlation(case):
    sent = decode_frames(case["send"])
    assert case["action"] in {"drop", "error"}
    if case["action"] == "drop":
        assert "response" not in case
    else:
        response = decode_frames(case["response"])
        assert response[:2] == [b"NWM3", b"ERROR"]
        assert response[2:4] == sent[2:4]
        assert 1 <= len(response[3]) <= 64
        assert len(response) == 5


def test_correlation_fixture_expected_owners():
    waiter = WIRE["correlation"]["waiter"]
    for case in WIRE["correlation"]["cases"]:
        packet = decode_frames(case["data"])
        matches = (
            packet[6].decode("ascii") == waiter["id"]
            and packet[5].decode("ascii") == waiter["sender"]
            and packet[4].decode("ascii") == waiter["network"]
        )
        assert case["owner"] == ("request" if matches else "inbox")


def test_cli_fixture_bytes_and_new_reply_id():
    cli = WIRE["cli"]
    assert set(cli["message"]) == {"event", "id", "reply_to", "network", "sender", "payload"}
    assert cli["message"]["reply_to"] is None
    assert base64.b64decode(cli["message"]["payload"], validate=True) == b"\x00\xff"
    assert cli["reply"]["reply_to"] == cli["message"]["id"]
    assert cli["reply"]["id"] != cli["message"]["id"]
    assert base64.b64decode(cli["reply"]["payload"], validate=True) == b"answer\x00\xff"
    assert cli["send_accepted"]["id"] == cli["message"]["id"]
    assert cli["reply_accepted"]["id"] == cli["reply"]["id"]
