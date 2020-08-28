import pytest

from notcallback.promise import FULFILLED, PENDING, REJECTED, Promise

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
    await p
    assert p.state is REJECTED


@pytest.mark.asyncio
async def test_async_non_exception_reject():
    p = Promise(simple_reject)
    v = await p
    assert v == 6


@pytest.mark.asyncio
async def test_async_exceptional_reject():
    p = Promise(exceptional_reject)
    exc = await p
    assert p.state is REJECTED
    assert isinstance(exc, RecursionError)


@pytest.mark.asyncio
async def test_async_return_resolved():
    p = Promise(incorrect_resolve)
    v = await p
    assert p.state is FULFILLED
    assert v is True
