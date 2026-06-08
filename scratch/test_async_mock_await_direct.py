from unittest.mock import AsyncMock
import asyncio

async def test_async_mock_direct():
    m = AsyncMock()
    try:
        await m
    except TypeError as e:
        print(f"Caught: {e}")

if __name__ == "__main__":
    asyncio.run(test_async_mock_direct())
