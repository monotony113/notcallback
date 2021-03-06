import pytest

from notcallback.async_ import Promise
from notcallback.exceptions import PromiseRejection
from notcallback.promise import FULFILLED, PENDING, REJECTED

from .suppliers import exceptional_reject, simple_reject, simple_resolve

pytestmark = pytest.mark.filterwarnings('ignore::notcallback.exceptions.UnhandledPromiseRejectionWarning')


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
