import asyncio
from main import main


async def loop():
    while True:
        await main()
        await asyncio.sleep(600)


if __name__ == "__main__":
    asyncio.run(loop())
