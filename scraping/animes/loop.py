import asyncio
from main import main


async def main():
    while True:
        await main()
        await asyncio.sleep(600)


if __name__ == "__main__":
    asyncio.run(main())
