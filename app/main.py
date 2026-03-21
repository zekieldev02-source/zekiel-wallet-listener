import asyncio

from app.core.logging import setup_logging
from app.workers.wallet_listener_worker import WalletListenerWorker


async def main() -> None:
    setup_logging()
    worker = WalletListenerWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
