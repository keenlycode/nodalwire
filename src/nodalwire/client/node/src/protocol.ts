import { isIP } from "node:net";

export function validName(name: unknown): name is string {
  return typeof name === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(name);
}

/** Validate loopback TCP before allocating a socket; never resolve DNS. */
export function localEndpoint(endpoint: string): string {
  if (typeof endpoint !== "string" || !endpoint.startsWith("tcp://")) {
    throw new TypeError("local relay endpoint must use tcp://");
  }
  const match = /^tcp:\/\/(.*):([0-9]+)$/.exec(endpoint);
  if (!match || Number(match[2]) < 1 || Number(match[2]) > 65535) {
    throw new TypeError("invalid TCP endpoint port");
  }
  let host = match[1];
  if (host === "localhost") host = "127.0.0.1";
  const ipv4 = isIP(host) === 4 && host.startsWith("127.");
  if (!ipv4 && host !== "[::1]") {
    throw new TypeError("endpoint must use a literal loopback address or localhost");
  }
  return `tcp://${host}:${match[2]}`;
}

/** A relay/local rejection or lifecycle interruption, never a remote execution result.
 * `closed` / `connection_failed` may interrupt a request after forwarding.
 */
export class RelayError extends Error {
  constructor(public readonly code: string) {
    super(code);
    this.name = "RelayError";
  }
}

/** Missing receipt: effect uncertain. Do not blindly retry. */
export class ReceiptTimeout extends Error {
  constructor() {
    super("routing receipt timed out; effect uncertain");
    this.name = "ReceiptTimeout";
  }
}

export interface OperationOptions {
  /** Seconds, matching Python; defaults to the connect timeout (5 seconds). */
  timeout?: number;
  /** Cancellation may occur after forwarding; no replay is performed. */
  signal?: AbortSignal;
}

export function timeoutSeconds(value: number): number {
  if (!Number.isFinite(value) || value <= 0 || value * 1000 > 2147483647) {
    throw new RangeError("timeout must be positive and fit a native timer");
  }
  return value;
}

export function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("Operation aborted", "AbortError");
}
