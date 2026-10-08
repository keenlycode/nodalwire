import { Buffer } from "node:buffer";
import { randomBytes } from "node:crypto";
import { Dealer } from "zeromq";
import { Inbox } from "./inbox.js";
import type { Message } from "./inbox.js";
import { Receipts } from "./receipts.js";
import { localEndpoint, RelayError, timeoutSeconds, validName } from "./protocol.js";
import type { OperationOptions } from "./protocol.js";

export interface ConnectOptions extends OperationOptions {
  sendHwm?: number;
  receiveHwm?: number;
  inboxSize?: number;
  maxPending?: number;
}

function limit(value: number): number {
  if (!Number.isSafeInteger(value) || value <= 0 || value > 2147483647) {
    throw new RangeError("queue limits must be positive native integers");
  }
  return value;
}

/** One admitted DEALER, bounded inbox/receipts, no retries or outbound backlog.
 * Use connect(), drain receive() concurrently with send() in long-lived applications.
 */
export class Node {
  readonly name: string;
  readonly endpoint: string;
  readonly timeout: number;
  private readonly socket: Dealer;
  private readonly inbox: Inbox;
  private readonly receipts: Receipts;
  private token?: Buffer;
  private maxPayload = 0;
  private reader?: Promise<void>;
  private heartbeat?: ReturnType<typeof setInterval>;
  private writing = false;
  private writer?: Promise<void>;
  private closed = false;
  private closing = false;
  private cleanup?: Promise<void>;
  private closeFinished?: Promise<void>;

  private constructor(name: string, endpoint: string, options: ConnectOptions) {
    if (!validName(name)) throw new TypeError("invalid logical node name");
    this.name = name;
    this.endpoint = localEndpoint(endpoint);
    this.timeout = timeoutSeconds(options.timeout ?? 5);
    const sendHwm = limit(options.sendHwm ?? 64);
    const receiveHwm = limit(options.receiveHwm ?? 64);
    this.inbox = new Inbox(limit(options.inboxSize ?? 64));
    this.receipts = new Receipts(limit(options.maxPending ?? 128));
    options.signal?.throwIfAborted();
    this.socket = new Dealer({
      linger: 0,
      ipv6: this.endpoint.startsWith("tcp://["),
      routingId: randomBytes(16).toString("hex"),
      immediate: true,
      sendHighWaterMark: sendHwm,
      receiveHighWaterMark: receiveHwm,
      // Admission is bounded by the receipt deadline; failed connect closes this send.
      sendTimeout: -1,
    });
    try {
      this.socket.connect(this.endpoint);
    } catch (error) {
      this.socket.close();
      throw error;
    }
  }

  /** Wait for Router admission; failure/cancellation always completes native cleanup. */
  static async connect(
    name: string,
    endpoint = "tcp://127.0.0.1:5555",
    options: ConnectOptions = {},
  ): Promise<Node> {
    const node = new Node(name, endpoint, options);
    node.reader = node.read();
    try {
      const reply = await node.request("HELLO", [Buffer.from(name)], options, true);
      const lease = Number(reply[1]?.toString());
      if (
        reply.length !== 3 || !node.token?.length || !Number.isFinite(lease) ||
        lease <= 0 ||
        !Number.isSafeInteger(node.maxPayload) || node.maxPayload <= 0
      ) {
        throw new RelayError("connection_failed");
      }
      node.socket.sendTimeout = 0;
      node.heartbeat = setInterval(() => {
        if (node.closed || node.closing || node.writing) return;
        void node.write([Buffer.from("AR1"), Buffer.from("HEARTBEAT"), node.token!])
          .catch(
            () => {/* No heartbeat backlog; local congestion may expire the lease. */},
          );
      }, lease * 1000 / 3);
      return node;
    } catch (error) {
      await node.dispose();
      throw error;
    }
  }

  /** Snapshot bytes immediately. Success means Router queue acceptance, not execution.
   * Timeout, abort and interrupted lifecycle have uncertain effects.
   */
  async send(
    destination: string,
    payload: Uint8Array,
    options: OperationOptions = {},
  ): Promise<void> {
    if (this.closing || this.closed) throw new RelayError("closed");
    if (!validName(destination)) throw new TypeError("invalid destination name");
    if (!(payload instanceof Uint8Array)) {
      throw new TypeError("payload must be Uint8Array");
    }
    if (payload.byteLength > this.maxPayload) throw new RelayError("payload_too_large");
    await this.request(
      "SEND",
      [Buffer.from(destination), Buffer.from(payload)],
      options,
    );
  }

  /** Cancellation affects only this inbox waiter, never the single native reader.
   * Queued messages remain readable after close; an empty closed inbox rejects.
   */
  receive(options: Pick<OperationOptions, "signal"> = {}): Promise<Message> {
    return this.inbox.get(options.signal);
  }

  /** Attempt release; always finish shared cleanup even on timeout/cancellation.
   * Concurrent/repeated callers wait for native cleanup; failed release stays uncertain.
   */
  async close(options: OperationOptions = {}): Promise<void> {
    if (this.closing) {
      await this.closeFinished;
      return;
    }
    this.closing = true;
    // Publish the shared completion before starting the release attempt.
    let finish!: () => void;
    this.closeFinished = new Promise<void>((resolve) => finish = resolve);
    try {
      if (this.token && !this.closed) await this.request("CLOSE", [], options);
    } finally {
      try {
        await this.dispose();
      } finally {
        finish();
      }
    }
  }

  private request(
    command: string,
    frames: Buffer[],
    options: OperationOptions,
    initial = false,
  ): Promise<Buffer[]> {
    if (this.closed) return Promise.reject(new RelayError("closed"));
    const seconds = timeoutSeconds(options.timeout ?? this.timeout);
    const token = initial ? Buffer.alloc(0) : this.token!;
    const request = this.receipts.begin(token, seconds, options);
    const body: Buffer[] = [Buffer.from("AR1"), Buffer.from(command)];
    if (!initial) body.push(token);
    body.push(Buffer.from(request.id), ...frames);
    // No queued writer: a busy/blocked native send is a local rejection.
    void this.write(body).catch(request.reject);
    return request.promise;
  }

  private write(frames: Buffer[]): Promise<void> {
    if (this.closed) return Promise.reject(new RelayError("closed"));
    if (this.writing) return Promise.reject(new RelayError("local_queue_full"));
    this.writing = true;
    this.writer = (async () => {
      try {
        await this.socket.send(frames);
      } catch (error) {
        if (this.closed) throw new RelayError("closed");
        const code = (error as { code?: string }).code;
        throw new RelayError(
          code === "EAGAIN" || code === "EBUSY"
            ? "local_queue_full"
            : "connection_failed",
        );
      } finally {
        this.writing = false;
      }
    })();
    return this.writer;
  }

  private async read(): Promise<void> {
    try {
      while (!this.closed) {
        const frames = await this.socket.receive();
        if (frames.length < 4 || frames[0].toString() !== "AR1") continue;
        const command = frames[1].toString();
        const token = frames[2];
        if (command === "DATA" && frames.length === 5 && this.token?.equals(token)) {
          const sender = frames[3].toString("ascii");
          if (validName(sender) && frames[4].length <= this.maxPayload) {
            await this.inbox.put({ sender, payload: Uint8Array.from(frames[4]) });
          }
          continue;
        }
        const id = frames[3];
        if (!this.receipts.matches(id, token)) continue;
        if (command === "OK" && token.length === 0 && frames.length === 7) {
          // Fence subsequent DATA immediately, before connect's continuation runs.
          this.token = Buffer.from(frames[4]);
          this.maxPayload = Number(frames[6].toString());
        }
        this.receipts.accept(id, command, frames.slice(4));
      }
    } catch {
      if (!this.closed) {
        this.closed = true;
        this.receipts.fail("connection_failed");
        this.inbox.close();
        if (this.heartbeat) clearInterval(this.heartbeat);
        this.socket.close();
      }
    }
  }

  private dispose(): Promise<void> {
    if (!this.cleanup) {
      this.closed = true;
      if (this.heartbeat) clearInterval(this.heartbeat);
      this.receipts.fail("closed");
      this.inbox.close();
      this.socket.close(); // Interrupt, then join the one native pending receive.
      this.cleanup = (async () => {
        await Promise.allSettled([this.reader, this.writer]);
      })();
    }
    return this.cleanup;
  }
}
