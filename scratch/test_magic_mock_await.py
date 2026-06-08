from unittest.mock import MagicMock
import asyncio

async def test_magic_mock():
    m = MagicMock()
    try:
        await m()
    except TypeError as e:
        print(f"Caught: {e}")

if __name__ == "__main__":
    asyncio.run(test_magic_mock())
