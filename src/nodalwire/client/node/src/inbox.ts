import { abortReason, RelayError } from "./protocol.js";

export interface Message {
  readonly network: string;
  readonly sender: string;
  /** Caller-owned mutable bytes, independent of the native socket's buffers. */
  readonly payload: Uint8Array;
}

/** One bounded ordered inbox; the reader may hold one extra DATA while full. */
export class Inbox {
  private readonly messages: Message[] = [];
  private readonly waiters = new Set<{
    resolve: (message: Message) => void;
    reject: (error: unknown) => void;
  }>();
  private space?: () => void;
  private closed = false;

  constructor(private readonly capacity: number) {}

  async put(message: Message): Promise<void> {
    if (this.messages.length >= this.capacity && !this.closed) {
      await new Promise<void>((resolve) => this.space = resolve);
    }
    if (this.closed) return;
    const waiter = this.waiters.values().next().value;
    if (waiter) {
      this.waiters.delete(waiter);
      waiter.resolve(message);
    } else {
      this.messages.push(message);
    }
  }

  get(signal?: AbortSignal): Promise<Message> {
    if (signal?.aborted) return Promise.reject(abortReason(signal));
    const message = this.getNowait();
    if (message) return Promise.resolve(message);
    if (this.closed) return Promise.reject(new RelayError("closed"));
    return new Promise<Message>((resolve, reject) => {
      const finish = () => {
        this.waiters.delete(waiter);
        signal?.removeEventListener("abort", abort);
      };
      const waiter = {
        resolve: (value: Message) => {
          finish();
          resolve(value);
        },
        reject: (error: unknown) => {
          finish();
          reject(error);
        },
      };
      const abort = () => waiter.reject(abortReason(signal!));
      this.waiters.add(waiter);
      signal?.addEventListener("abort", abort, { once: true });
    });
  }

  /** Only queued ordinary data; empty is undefined even after close. */
  getNowait(): Message | undefined {
    const message = this.messages.shift();
    if (message) {
      this.space?.();
      this.space = undefined;
    }
    return message;
  }

  close(): void {
    this.closed = true;
    this.space?.();
    this.space = undefined;
    for (const waiter of this.waiters) waiter.reject(new RelayError("closed"));
  }
}
