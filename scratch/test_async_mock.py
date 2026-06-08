from unittest.mock import AsyncMock
import asyncio

async def test_async_mock():
    m = AsyncMock()
    m.return_value = "success"
    # m() returns a coroutine. Awaiting it gives "success"
    res = await m()
    print(f"Result 1: {res}")

    m.side_effect = ["first", "second"]
    # Calling m() returns a coroutine. Awaiting it gives "first"
    res = await m()
    print(f"Result 2: {res}")
    res = await m()
    print(f"Result 3: {res}")

    # What if side_effect is a list of objects?
    m.side_effect = [Exception("error"), "third"]
    try:
        await m()
    except Exception as e:
        print(f"Caught: {e}")
    res = await m()
    print(f"Result 4: {res}")

if __name__ == "__main__":
    asyncio.run(test_async_mock())
