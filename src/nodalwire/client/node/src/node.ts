import { Buffer } from "node:buffer";
import { randomBytes } from "node:crypto";
import { Dealer } from "zeromq";
import { decodeEnvelope, encodeEnvelope } from "./envelope.js";
import { Inbox } from "./inbox.js";
import type { Message } from "./inbox.js";
import { Receipts } from "./receipts.js";
import {
  abortReason,
  ascii,
  credentialFrame,
  localEndpoint,
  ReceiptTimeout,
  RelayError,
  timeoutSeconds,
  validName,
  VERSION,
} from "./protocol.js";
import type { MembershipReceipt, OperationOptions, SendOptions } from "./protocol.js";

export interface ConnectOptions extends OperationOptions {
  sendHwm?: number;
  receiveHwm?: number;
  inboxSize?: number;
  /** Independent caps for control receipts and application reply waiters. */
  maxPending?: number;
}

interface ReplyWaiter {
  sender: string;
  network: string;
  resolve: (message: Message) => void;
  reject: (error: unknown) => void;
}

function limit(value: number): number {
  if (!Number.isSafeInteger(value) || value <= 0 || value > 2147483647) {
    throw new RangeError("queue limits must be positive native integers");
  }
  return value;
}

function emptyReceipt(frames: Buffer[]): void {
  if (frames.length !== 0) throw new RelayError("invalid_receipt");
}

function selectedNetwork(network = "default"): string {
  if (!validName(network)) throw new TypeError("invalid network name");
  return network;
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
  private readonly maxPending: number;
  private readonly replies = new Map<string, ReplyWaiter>();
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
    this.maxPending = limit(options.maxPending ?? 128);
    this.receipts = new Receipts(this.maxPending);
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

  /** Wait for Router admission; failure/cancellation always completes native cleanup.
   * Protected default permits admission with zero memberships; join it explicitly.
   */
  static async connect(
    name: string,
    endpoint = "tcp://127.0.0.1:5555",
    options: ConnectOptions = {},
  ): Promise<Node> {
    const node = new Node(name, endpoint, options);
    node.reader = node.read();
    try {
      const lease = await node.control(
        "HELLO",
        [Buffer.from(name)],
        options,
        (reply) => {
          if (reply.length !== 4) throw new RelayError("invalid_receipt");
          const token = ascii(reply[0]);
          const leaseText = ascii(reply[1]);
          const payloadText = ascii(reply[2]);
          const memberships = ascii(reply[3]);
          if (
            !token || !/^[0-9a-f]{32}$/.test(token) || !leaseText ||
            !/^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(leaseText) ||
            !payloadText || !/^[1-9][0-9]*$/.test(payloadText) ||
            reply[3].length > 32 ||
            (memberships !== "[]" && memberships !== '["default"]')
          ) throw new RelayError("invalid_receipt");
          const lease = Number(leaseText);
          const payloadLimit = Number(payloadText);
          if (
            !Number.isFinite(lease) || lease < 0.1 || lease > 3600 ||
            !Number.isSafeInteger(payloadLimit) || payloadLimit <= 0 ||
            payloadLimit > 2147479552
          ) throw new RelayError("invalid_receipt");
          // Fence subsequent DATA synchronously, only after full HELLO validation.
          node.token = Buffer.from(reply[0]);
          node.maxPayload = payloadLimit;
          return lease;
        },
        true,
      );
      node.socket.sendTimeout = 0;
      node.heartbeat = setInterval(() => {
        if (node.closed || node.closing || node.writing) return;
        void node.write([Buffer.from(VERSION), Buffer.from("HEARTBEAT"), node.token!])
          .catch(() => {/* No backlog; local congestion may expire the lease. */});
      }, lease * 1000 / 3);
      return node;
    } catch (error) {
      await node.dispose();
      throw error;
    }
  }

  /** Snapshot bytes immediately. Success means Router native-queue acceptance,
   * not execution. Timeout, abort and interrupted lifecycle have uncertain effects.
   */
  async send(
    destination: string,
    payload: Uint8Array,
    options: SendOptions = {},
  ): Promise<void> {
    this.checkOpen();
    if (!validName(destination)) throw new TypeError("invalid destination name");
    const network = selectedNetwork(options.network);
    if (!(payload instanceof Uint8Array)) {
      throw new TypeError("payload must be Uint8Array");
    }
    if (payload.byteLength > this.maxPayload) throw new RelayError("payload_too_large");
    await this.control(
      "SEND",
      [Buffer.from(network), Buffer.from(destination), Buffer.from(payload)],
      options,
      emptyReceipt,
    );
  }

  async join(
    network: string,
    credential?: string,
    options: OperationOptions = {},
  ): Promise<MembershipReceipt> {
    this.checkOpen();
    if (!validName(network)) throw new TypeError("invalid network name");
    const token = credentialFrame(credential);
    return await this.control(
      "JOIN",
      [Buffer.from(network), Buffer.from(token)],
      options,
      (frames) => this.membershipReceipt(frames, network, true),
    );
  }

  async leave(
    network: string,
    options: OperationOptions = {},
  ): Promise<MembershipReceipt> {
    this.checkOpen();
    if (!validName(network)) throw new TypeError("invalid network name");
    return await this.control(
      "LEAVE",
      [Buffer.from(network)],
      options,
      (frames) => this.membershipReceipt(frames, network, false),
    );
  }

  /** One deadline and first terminal event. Matching reply can succeed even if
   * SEND's routing receipt is missing; no retry, no silent unrelated-data loss.
   */
  async request(
    destination: string,
    payload: Uint8Array,
    options: SendOptions = {},
  ): Promise<Message> {
    this.checkOpen();
    if (!validName(destination)) throw new TypeError("invalid destination name");
    const network = selectedNetwork(options.network);
    const seconds = timeoutSeconds(options.timeout ?? this.timeout);
    options.signal?.throwIfAborted();
    if (this.replies.size >= this.maxPending) throw new RelayError("pending_full");
    const id = randomBytes(16).toString("hex");
    const encoded = encodeEnvelope({ kind: "request", id, payload }, this.maxPayload);
    const receiptAbort = new AbortController();
    // Timer and SEND begin in this synchronous turn: a single monotonic deadline,
    // not a fresh timeout after receipt acceptance.
    const reply = new Promise<Message>((resolve, reject) => {
      const finish = (): boolean => {
        if (!this.replies.delete(id)) return false;
        clearTimeout(timer);
        options.signal?.removeEventListener("abort", abort);
        receiptAbort.abort(); // Only our receipt wait, never native socket operations.
        return true;
      };
      const waiter: ReplyWaiter = {
        sender: destination,
        network,
        resolve: (message) => {
          if (finish()) resolve(message);
        },
        reject: (error) => {
          if (finish()) reject(error);
        },
      };
      const abort = () => waiter.reject(abortReason(options.signal!));
      const timer = setTimeout(
        () => waiter.reject(new ReceiptTimeout()),
        seconds * 1000,
      );
      this.replies.set(id, waiter); // Before SEND and before any native await.
      options.signal?.addEventListener("abort", abort, { once: true });
    });
    const failed = (error: unknown) => this.replies.get(id)?.reject(error);
    try {
      // Receipt failures settle app ownership synchronously in the reader, just
      // like replies; Promise continuation timing must not reverse wire order.
      void this.control(
        "SEND",
        [Buffer.from(network), Buffer.from(destination), Buffer.from(encoded)],
        { timeout: seconds, signal: receiptAbort.signal },
        emptyReceipt,
        false,
        failed,
      ).catch(failed);
    } catch (error) {
      failed(error);
    }
    return await reply;
  }

  /** Reply on the incoming request's explicit network; names are not identity. */
  async reply(
    incoming: Message,
    payload: Uint8Array,
    options: OperationOptions = {},
  ): Promise<void> {
    this.checkOpen();
    if (!incoming || "network" in options) throw new TypeError("invalid reply options");
    const envelope = decodeEnvelope(incoming.payload, this.maxPayload);
    if (!envelope || envelope.kind !== "request") {
      throw new TypeError("not a request envelope");
    }
    const encoded = encodeEnvelope(
      { kind: "reply", id: envelope.id, payload },
      this.maxPayload,
    );
    await this.send(incoming.sender, encoded, {
      ...options,
      network: incoming.network,
    });
  }

  /** Cancel only this waiter; queued data remains readable after close. */
  receive(options: Pick<OperationOptions, "signal"> = {}): Promise<Message> {
    return this.inbox.get(options.signal);
  }

  /** Only currently queued ordinary data, never a native read; empty even closed. */
  receiveNowait(): Message | undefined {
    return this.inbox.getNowait();
  }

  /** Attempt release; always finish shared cleanup even on timeout/cancellation.
   * Concurrent/repeated callers wait for cleanup; failed release stays uncertain.
   */
  async close(options: OperationOptions = {}): Promise<void> {
    if (this.closing) {
      await this.closeFinished;
      return;
    }
    this.closing = true;
    this.failReplies("closed");
    let finish!: () => void;
    this.closeFinished = new Promise<void>((resolve) => finish = resolve);
    try {
      if (this.token && !this.closed) {
        await this.control("CLOSE", [], options, emptyReceipt);
      }
    } finally {
      try {
        await this.dispose();
      } finally {
        finish();
      }
    }
  }

  private checkOpen(): void {
    if (this.closing || this.closed) throw new RelayError("closed");
  }

  private membershipReceipt(
    frames: Buffer[],
    network: string,
    joined: boolean,
  ): MembershipReceipt {
    if (
      frames.length !== 2 || ascii(frames[0]) !== network ||
      (ascii(frames[1]) !== "0" && ascii(frames[1]) !== "1")
    ) throw new RelayError("invalid_receipt");
    return Object.freeze({ network, joined, changed: ascii(frames[1]) === "1" });
  }

  private control<T>(
    command: string,
    frames: Buffer[],
    options: OperationOptions,
    validate: (frames: Buffer[]) => T,
    initial = false,
    onReject?: (error: unknown) => void,
  ): Promise<T> {
    if (this.closed) return Promise.reject(new RelayError("closed"));
    const seconds = timeoutSeconds(options.timeout ?? this.timeout);
    const token = initial ? Buffer.alloc(0) : this.token!;
    const request = this.receipts.begin(token, seconds, options, validate, onReject);
    const body: Buffer[] = [Buffer.from(VERSION), Buffer.from(command)];
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
        if (frames.length < 4 || ascii(frames[0]) !== VERSION) continue;
        const command = ascii(frames[1]);
        const token = frames[2];
        if (command === "DATA") {
          if (frames.length !== 6 || !this.token?.equals(token)) continue;
          const network = ascii(frames[3]);
          const sender = ascii(frames[4]);
          if (
            !validName(network) || !validName(sender) ||
            frames[5].length > this.maxPayload
          ) continue;
          const message: Message = {
            network,
            sender,
            payload: Uint8Array.from(frames[5]),
          };
          const envelope = this.replies.size
            ? decodeEnvelope(message.payload, this.maxPayload)
            : undefined;
          const waiter = envelope?.kind === "reply"
            ? this.replies.get(envelope.id)
            : undefined;
          if (waiter && waiter.sender === sender && waiter.network === network) {
            // Synchronous ownership before Promise continuations: accepted reply wins
            // a subsequent same-turn abort or receipt failure.
            waiter.resolve({ network, sender, payload: envelope!.payload });
          } else await this.inbox.put(message);
          continue;
        }
        const id = frames[3];
        if (!this.receipts.matches(id, token)) continue;
        this.receipts.accept(id, command, frames.slice(4));
      }
    } catch {
      if (!this.closed) {
        this.closed = true;
        this.receipts.fail("connection_failed");
        this.failReplies("connection_failed");
        this.inbox.close();
        if (this.heartbeat) clearInterval(this.heartbeat);
        this.socket.close();
      }
    }
  }

  private failReplies(code: string): void {
    for (const waiter of this.replies.values()) waiter.reject(new RelayError(code));
  }

  private dispose(): Promise<void> {
    if (!this.cleanup) {
      this.closed = true;
      if (this.heartbeat) clearInterval(this.heartbeat);
      this.receipts.fail("closed");
      this.failReplies("closed");
      this.inbox.close();
      this.socket.close(); // Interrupt, then join the one native pending receive.
      this.cleanup = (async () => {
        await Promise.allSettled([this.reader, this.writer]);
      })();
    }
    return this.cleanup;
  }
}
