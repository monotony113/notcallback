import pytest

from notcallback import Promise

from .suppliers import simple_resolve


@pytest.mark.asyncio
async def test_await():
    value = await Promise(simple_resolve)
    assert value == 5
