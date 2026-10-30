import { Router } from "./deps.mjs";

export const TOKEN = "0123456789abcdef0123456789abcdef";

/** Owned ephemeral NWM3 socket. Every test closes/joins its sole reader. */
export async function fakeRelay(handler = () => {}, options = {}) {
  const router = new Router({ linger: 0 });
  await router.bind("tcp://127.0.0.1:*");
  const seen = [];
  const peers = new Map();
  const send = (...frames) => router.send(frames);
  const reader = (async () => {
    try {
      for await (const frames of router) {
        const [route, version, command] = frames;
        const initial = command.toString() === "HELLO";
        const rid = frames[initial ? 3 : 4];
        const peer = {
          route,
          command: command.toString(),
          frames,
          rid,
          token: TOKEN,
          ok: (...extra) =>
            send(route, "NWM3", "OK", initial ? "" : TOKEN, rid, ...extra),
          error: (code) =>
            send(route, "NWM3", "ERROR", initial ? "" : TOKEN, rid, code),
          data: (id, network, sender, replyTo, payload, token = TOKEN) =>
            send(route, "NWM3", "DATA", token, id, network, sender, replyTo, payload),
          raw: (...body) => send(route, ...body),
        };
        seen.push(frames);
        if (initial) peers.set(frames[4].toString(), peer);
        if (await handler(peer)) continue;
        if (version.toString() !== "NWM3") continue;
        switch (peer.command) {
          case "HELLO":
            await peer.ok(TOKEN, "10", "1048576", options.memberships ?? '["default"]');
            break;
          case "JOIN":
          case "LEAVE":
            await peer.ok(frames[5], "1");
            break;
          case "SEND":
          case "CLOSE":
            await peer.ok();
            break;
        }
      }
    } catch (error) {
      if (!router.closed) throw error;
    }
  })();
  return {
    endpoint: router.lastEndpoint,
    seen,
    peers,
    async close() {
      router.close();
      await reader;
    },
  };
}
