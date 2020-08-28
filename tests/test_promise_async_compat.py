import pytest

from notcallback.promise import FULFILLED, PENDING, REJECTED, Promise
from notcallback.exceptions import PromiseRejection

from .suppliers import (exceptional_reject, incorrect_resolve, simple_reject,
                        simple_resolve)


@pytest.mark.asyncio
async def test_async_pending():
    p = Promise(simple_resolve)
    assert p.state is PENDING


@pytest.mark.asyncio
async def test_async_resolve():
    p = Promise(simple_resolve)
    await p
    assert p.state is FULFILLED


@pytest.mark.asyncio
async def test_async_reject():
    p = Promise(simple_reject)
    with pytest.raises(PromiseRejection) as excinfo:
        await p
        assert p.state is REJECTED
        assert excinfo.value.value == 6


@pytest.mark.asyncio
async def test_async_exceptional_reject():
    p = Promise(exceptional_reject)
    with pytest.raises(RecursionError):
        await p
        assert p.state is REJECTED


@pytest.mark.asyncio
async def test_async_return_resolved():
    p = Promise(incorrect_resolve)
    v = await p
    assert p.state is FULFILLED
    assert v is True
