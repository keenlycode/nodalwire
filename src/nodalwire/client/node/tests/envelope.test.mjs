import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import test from "node:test";
import { decodeEnvelope, encodeEnvelope, RelayError } from "../dist/index.js";

const id = "0123456789abcdef0123456789abcdef";
const wire = (json) => Buffer.from("NWR1\n" + json);
const object = { v: 1, kind: "request", id, payload: "AP+A" };

test("codec preserves arbitrary/empty bytes with exact encoded bounds and snapshots", () => {
  for (
    const payload of [
      new Uint8Array(),
      Uint8Array.from({ length: 256 }, (_, i) => i),
    ]
  ) {
    const encoded = encodeEnvelope({ kind: "request", id, payload });
    assert.deepEqual(decodeEnvelope(encoded), { kind: "request", id, payload });
    assert.equal(decodeEnvelope(encoded, encoded.length - 1), undefined);
    assert.deepEqual(
      encodeEnvelope({ kind: "request", id, payload }, encoded.length),
      encoded,
    );
    assert.throws(
      () => encodeEnvelope({ kind: "request", id, payload }, encoded.length - 1),
      (error) => error instanceof RelayError && error.code === "payload_too_large",
    );
  }
  const payload = Uint8Array.of(1);
  const encoded = encodeEnvelope({ kind: "reply", id, payload });
  payload[0] = 2;
  assert.equal(decodeEnvelope(encoded).payload[0], 1);
  const decoded = decodeEnvelope(encoded);
  decoded.payload[0] = 3;
  assert.equal(decodeEnvelope(encoded).payload[0], 1);
});

test("codec rejects duplicate/escaped duplicate keys, noncanonical base64 and malformed JSON", () => {
  const valid = JSON.stringify(object);
  assert.deepEqual(decodeEnvelope(wire(valid)), {
    kind: "request",
    id,
    payload: Uint8Array.of(0, 255, 128),
  });
  const invalid = [
    valid.replace('"v":1', '"v":1,"v":1'),
    valid.replace('"v":1', '"v":1,"\\u0076":1'),
    valid.replace('"v":1', '"v":1,"extra":0'),
    valid.replace('"v":1,', ""),
    valid.replace('"v":1', '"v":true'),
    valid.replace('"v":1', '"v":"1"'),
    valid.replace('"v":1', '"v":2'),
    valid.replace('"kind":"request"', '"kind":"other"'),
    valid.replace(id, id.toUpperCase()),
    valid.replace('"AP+A"', '"AA"'),
    valid.replace('"AP+A"', '"AB=="'), // Nonzero unused padding bits.
    valid.replace('"AP+A"', '"AA-_"'),
    valid.replace('"AP+A"', '" AA=="'),
    valid.replace('"AP+A"', '"AA==\n"'),
    valid.replace('"AP+A"', '"A==="'),
    valid.replace('"AP+A"', "null"),
    valid.replace('"AP+A"', "[]"),
    valid.replace('"AP+A"', "{}"),
    valid.slice(0, -1) + ",}",
    valid + " false",
    "[" + valid + "]",
    "{}",
    "",
  ];
  for (const json of invalid) assert.equal(decodeEnvelope(wire(json)), undefined, json);
  assert.equal(decodeEnvelope(Buffer.from("NWR2\n" + valid)), undefined);
  assert.equal(
    decodeEnvelope(Buffer.concat([wire(valid), Buffer.from([255])])),
    undefined,
  );
  assert.equal(decodeEnvelope(Buffer.from("NWR1\n\ufeff" + valid)), undefined);
  assert.equal(decodeEnvelope("not bytes"), undefined);
  assert.equal(decodeEnvelope(wire(valid), 0), undefined);
  // JSON whitespace and escaped keys are valid, unless they duplicate another key.
  assert.ok(decodeEnvelope(wire(valid.replace('"v":1', '"\\u0076" : 1'))));
});

test("encoder rejects invalid input without reflecting supplied values", () => {
  for (
    const envelope of [null, {}, { kind: "bad", id, payload: new Uint8Array() }, {
      kind: "request",
      id: "bad",
      payload: new Uint8Array(),
    }, { kind: "request", id, payload: "secret-fixture" }]
  ) {
    assert.throws(() => encodeEnvelope(envelope), {
      name: "TypeError",
      message: "invalid request envelope",
    });
  }
});
