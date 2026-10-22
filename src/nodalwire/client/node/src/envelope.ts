import { Buffer } from "node:buffer";
import { RelayError } from "./protocol.js";

/** Client correlation only: neither the ID nor sender name proves identity. */
export interface Envelope {
  readonly kind: "request" | "reply";
  readonly id: string;
  readonly payload: Uint8Array;
}

const prefix = Buffer.from("NWR1\n");
const idPattern = /^[0-9a-f]{32}$/;
const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

function validLimit(value: number): boolean {
  return Number.isSafeInteger(value) && value > 0;
}

export function encodeEnvelope(envelope: Envelope, maxBytes = 1048576): Uint8Array {
  if (
    !validLimit(maxBytes) || !envelope ||
    (envelope.kind !== "request" && envelope.kind !== "reply") ||
    typeof envelope.id !== "string" || !idPattern.test(envelope.id) ||
    !(envelope.payload instanceof Uint8Array)
  ) throw new TypeError("invalid request envelope");
  // Bound before base64 allocation; include exact overhead in the final check.
  if (envelope.payload.byteLength > maxBytes) throw new RelayError("payload_too_large");
  const encoded = Buffer.from(
    "NWR1\n" + JSON.stringify({
      v: 1,
      kind: envelope.kind,
      id: envelope.id,
      payload: Buffer.from(envelope.payload).toString("base64"),
    }),
  );
  if (encoded.length > maxBytes) throw new RelayError("payload_too_large");
  return encoded;
}

/** Parse only the flat scalar object the codec permits, detecting duplicate keys
 * after unescaping. JSON.parse alone would silently keep the last duplicate.
 */
function flatObject(text: string): Map<string, unknown> | undefined {
  let index = 0;
  const fields = new Map<string, unknown>();
  // JSON forbids unescaped control bytes within a string token.
  // deno-lint-ignore no-control-regex
  const string = /"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"/y;
  const number = /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/y;
  const whitespace = () => {
    while (index < text.length && /[\x20\t\r\n]/.test(text[index])) index++;
  };
  const token = (pattern: RegExp): unknown => {
    pattern.lastIndex = index;
    const match = pattern.exec(text);
    if (!match) throw new Error("invalid scalar");
    index = pattern.lastIndex;
    return JSON.parse(match[0]);
  };
  whitespace();
  if (text[index++] !== "{") return;
  whitespace();
  if (text[index] === "}") return;
  while (index < text.length) {
    const key = token(string) as string;
    if (fields.has(key) || fields.size >= 4) return;
    whitespace();
    if (text[index++] !== ":") return;
    whitespace();
    const valueStart = index;
    const value = token(text[index] === '"' ? string : number);
    // JSON.parse erases integer-vs-float lexical type (1.0 / 1e0 become 1).
    // The shared Python codec requires the version to be an integer token.
    if (key === "v" && text.slice(valueStart, index) !== "1") return;
    fields.set(key, value);
    whitespace();
    const separator = text[index++];
    if (separator === "}") {
      whitespace();
      return index === text.length ? fields : undefined;
    }
    if (separator !== ",") return;
    whitespace();
  }
}

/** Invalid/oversize input is ordinary opaque data, not a consumed protocol event. */
export function decodeEnvelope(
  payload: Uint8Array,
  maxBytes = 1048576,
): Envelope | undefined {
  if (
    !validLimit(maxBytes) || !(payload instanceof Uint8Array) ||
    payload.byteLength > maxBytes || payload.byteLength < prefix.length ||
    !prefix.every((byte, i) => payload[i] === byte)
  ) return;
  try {
    const fields = flatObject(decoder.decode(payload.subarray(prefix.length)));
    if (!fields || fields.size !== 4 || fields.get("v") !== 1) return;
    const kind = fields.get("kind");
    const id = fields.get("id");
    const base64 = fields.get("payload");
    if (
      (kind !== "request" && kind !== "reply") || typeof id !== "string" ||
      !idPattern.test(id) || typeof base64 !== "string" ||
      !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(base64)
    ) return;
    const bytes = Buffer.from(base64, "base64");
    if (bytes.toString("base64") !== base64) return;
    return { kind, id, payload: Uint8Array.from(bytes) };
  } catch {
    return;
  }
}
