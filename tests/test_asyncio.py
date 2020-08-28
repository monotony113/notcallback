import pytest

from notcallback import Promise


async def simple_resolve(resolve, reject):
    yield 1
    yield 3
    for _ in resolve(5):
        yield _


@pytest.mark.asyncio
async def test_await():
    value = await Promise(simple_resolve)
    assert value == 5
