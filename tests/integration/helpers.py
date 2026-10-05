"""Real TCP relay fixtures; all sockets, tasks and contexts are test-owned."""

import asyncio
import contextlib
import secrets
from contextlib import asynccontextmanager

import zmq
import zmq.asyncio

from nodalwire import Node, ReceiptTimeout, Relay, RelayConfig, RelayError
from nodalwire.protocol import HELLO, VERSION


class Harness:
    def __init__(self, **config):
        self.relay = Relay(RelayConfig(endpoint="tcp://127.0.0.1:*", **config))
        self.endpoint = ""
        self.nodes = []

    async def node(self, name, **options):
        node = await Node.connect(name, self.endpoint, **options)
        self.nodes.append(node)
        return node


@asynccontextmanager
async def running_relay(**config):
    harness = Harness(**config)
    harness.endpoint = await harness.relay.start()
    task = asyncio.create_task(harness.relay.run())
    try:
        yield harness
    finally:
        for node in harness.nodes:
            with contextlib.suppress(ReceiptTimeout, RelayError):
                await node.close(timeout=0.2)
            assert node.socket.closed and node.context.closed
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await harness.relay.close()
        assert harness.relay.socket.closed and harness.relay.context.closed


@asynccontextmanager
async def raw_node(endpoint, name, *, identity=None, receive_hwm=1):
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.DEALER)
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.RCVHWM, receive_hwm)
    socket.setsockopt(zmq.IDENTITY, identity or secrets.token_bytes(16))
    socket.connect(endpoint)
    try:
        reply = await raw_request(socket, HELLO, name.encode("ascii"), initial=True)
        assert reply[1] == b"OK", reply
        yield socket, reply[4]
    finally:
        socket.close(linger=0)
        context.term()


async def raw_request(socket, command, *frames, initial=False):
    request = secrets.token_hex(16).encode("ascii")
    body = (
        [VERSION, command, request, *frames]
        if initial
        else [VERSION, command, frames[0], request, *frames[1:]]
    )
    async with asyncio.timeout(2):
        await socket.send_multipart(body)
        while True:
            reply = await socket.recv_multipart()
            if len(reply) >= 4 and reply[0] == VERSION and reply[3] == request:
                return reply
