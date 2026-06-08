from unittest.mock import AsyncMock
import asyncio

async def test_async_mock():
    m = AsyncMock()
    inner = AsyncMock()
    m.side_effect = [inner]
    print(f"Calling m()...")
    coro = m()
    print(f"Coro type: {type(coro)}")
    print(f"Awaiting coro...")
    res = await coro
    print(f"Result: {res}")
    print(f"Result type: {type(res)}")

if __name__ == "__main__":
    asyncio.run(test_async_mock())
