import { Buffer } from "node:buffer";
import { randomBytes } from "node:crypto";
import {
  abortReason,
  ascii,
  ReceiptTimeout,
  RELAY_CODES,
  RelayError,
} from "./protocol.js";
import type { OperationOptions } from "./protocol.js";

interface Pending {
  token: Buffer;
  accept: (frames: Buffer[]) => void;
  reject: (error: unknown) => void;
}

/** Correlation is capped; timeout/abort removes entries but cannot recall packets. */
export class Receipts {
  private readonly pending = new Map<string, Pending>();
  constructor(private readonly capacity: number) {}

  begin<T>(
    token: Buffer,
    seconds: number,
    options: OperationOptions,
    validate: (frames: Buffer[]) => T,
    onReject?: (error: unknown) => void,
    explicitId?: string,
  ) {
    if (options.signal?.aborted) throw abortReason(options.signal);
    if (this.pending.size >= this.capacity) throw new RelayError("pending_full");
    const id = explicitId ?? randomBytes(16).toString("hex");
    if (!/^[0-9a-f]{32}$/.test(id) || this.pending.has(id)) {
      throw new RelayError("pending_full");
    }
    let entry: Pending;
    const promise = new Promise<T>((resolve, reject) => {
      const finish = () => {
        clearTimeout(timer);
        options.signal?.removeEventListener("abort", abort);
        this.pending.delete(id);
      };
      const abort = () => entry.reject(abortReason(options.signal!));
      const timer = setTimeout(
        () => entry.reject(new ReceiptTimeout()),
        seconds * 1000,
      );
      entry = {
        token,
        accept: (frames) => {
          try {
            const result = validate(frames);
            finish();
            resolve(result);
          } catch {
            entry.reject(new RelayError("invalid_receipt"));
          }
        },
        reject: (error) => {
          finish();
          onReject?.(error);
          reject(error);
        },
      };
      this.pending.set(id, entry);
      options.signal?.addEventListener("abort", abort, { once: true });
    });
    return {
      id,
      promise,
      reject: (error: unknown) => this.pending.get(id)?.reject(error),
    };
  }

  has(id: string): boolean {
    return this.pending.has(id);
  }

  matches(id: Buffer, token: Buffer): boolean {
    const key = ascii(id);
    return key !== undefined && (this.pending.get(key)?.token.equals(token) ?? false);
  }

  accept(id: Buffer, command: string | undefined, frames: Buffer[]): void {
    const key = ascii(id);
    const entry = key === undefined ? undefined : this.pending.get(key);
    if (!entry) return;
    if (command === "OK") entry.accept(frames);
    else if (command === "ERROR" && frames.length === 1) {
      const code = ascii(frames[0]);
      entry.reject(
        new RelayError(code && RELAY_CODES.has(code) ? code : "invalid_receipt"),
      );
    } else entry.reject(new RelayError("invalid_receipt"));
  }

  fail(code: string): void {
    for (const entry of this.pending.values()) entry.reject(new RelayError(code));
  }
}
