"""Small foreground service; configuration is loaded once at startup."""

import asyncio
import signal
from pathlib import Path

from cyclopts import App

from .config import RelayConfig, load_config
from .server import Relay

app = App(help="Run the loopback-only byte relay for trusted local applications.")


async def _serve(config: RelayConfig) -> None:
    relay = Relay(config)
    endpoint = await relay.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    runner = asyncio.create_task(relay.run())
    waiter = asyncio.create_task(stop.wait())
    print(endpoint, flush=True)
    try:
        completed, _ = await asyncio.wait([runner, waiter], return_when=asyncio.FIRST_COMPLETED)
        if runner in completed:
            await runner  # Surface a service failure, not a false successful shutdown.
    finally:
        runner.cancel()
        waiter.cancel()
        await asyncio.gather(runner, waiter, return_exceptions=True)
        await relay.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


@app.default
def main(*, config: Path | None = None) -> None:
    """Start the relay; prints the bound endpoint after native bind succeeds.

    Parameters
    ----------
    config
        Startup cooperative TOML policy. Default: open admission on loopback.
    """
    asyncio.run(_serve(load_config(config) if config is not None else RelayConfig()))
