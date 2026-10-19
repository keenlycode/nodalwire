import { Buffer } from "node:buffer";
import { randomBytes } from "node:crypto";
import { abortReason, ReceiptTimeout, RelayError } from "./protocol.js";
import type { OperationOptions } from "./protocol.js";

interface Pending {
  token: Buffer;
  resolve: (frames: Buffer[]) => void;
  reject: (error: unknown) => void;
}

/** Correlation is capped; timeout/abort removes entries but cannot recall packets. */
export class Receipts {
  private readonly pending = new Map<string, Pending>();
  constructor(private readonly capacity: number) {}

  begin(token: Buffer, seconds: number, options: OperationOptions) {
    if (options.signal?.aborted) throw abortReason(options.signal);
    if (this.pending.size >= this.capacity) throw new RelayError("pending_full");
    const id = randomBytes(16).toString("hex");
    let entry: Pending;
    const promise = new Promise<Buffer[]>((resolve, reject) => {
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
        resolve: (frames) => {
          finish();
          resolve(frames);
        },
        reject: (error) => {
          finish();
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

  matches(id: Buffer, token: Buffer): boolean {
    return this.pending.get(id.toString())?.token.equals(token) ?? false;
  }

  accept(id: Buffer, command: string, frames: Buffer[]): void {
    const entry = this.pending.get(id.toString());
    if (command === "OK") entry?.resolve(frames);
    else if (command === "ERROR" && frames.length === 1) {
      entry?.reject(new RelayError(frames[0].toString("ascii")));
    }
  }

  fail(code: string): void {
    for (const entry of this.pending.values()) entry.reject(new RelayError(code));
  }
}
