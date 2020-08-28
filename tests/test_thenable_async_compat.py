import random

import pytest

from notcallback.promise import FULFILLED, PENDING, REJECTED, Promise
from notcallback.exceptions import PromiseRejection

from .suppliers import simple_resolve

pytestmark = pytest.mark.filterwarnings('ignore::notcallback.exceptions.UnhandledPromiseRejectionWarning')


@pytest.mark.asyncio
async def test_async_default_fulfill():
    p = Promise(lambda resolve, reject: (yield from resolve(12))).then()
    v = await p
    assert p.is_fulfilled
    assert v == 12


@pytest.mark.asyncio
async def test_async_on_fulfill_cascade():
    values = {}

    p = Promise(simple_resolve)
    p2 = p.then(lambda val: values.__setitem__('result1', val))
    p3 = p2.then(lambda val: values.__setitem__('result2', val) or 24)

    v2 = await p2

    assert p.state is FULFILLED
    assert p.value == 5
    assert values['result1'] == 5

    assert p2.state is FULFILLED
    assert v2 is None
    assert values['result2'] is None

    assert p3.state is FULFILLED
    assert p3.value == 24


@pytest.mark.asyncio
async def test_async_fulfiller_exception():
    values = {}

    def throw(val):
        raise TypeError()

    p = Promise(simple_resolve)
    p2 = p.then(throw)
    p3 = p2.then(lambda val: values.__setitem__('result1', val) or 24)

    with pytest.raises(TypeError):
        v2 = await p2

        assert p.state is FULFILLED
        assert p.value == 5

        assert p2.state is REJECTED
        assert isinstance(v2, TypeError)

        assert p3.state is REJECTED
        assert isinstance(p3.value, TypeError)

        assert p2.value is p3.value
        assert not values



@pytest.mark.asyncio
async def test_async_fulfiller_chain():
    values = {}

    def add(delta):
        def accumulate(val):
            return val + delta
        return accumulate

    p = (  # noqa: ECE001
        Promise(lambda resolve, _: (yield from resolve(-1)))
        .then(add(3))
        .then(add(6))
        .then(add(10))
        .then(lambda v: values.__setitem__('sum', v))
    )

    v = await p

    assert p.state is FULFILLED
    assert v is None
    assert values['sum'] == 18


@pytest.mark.asyncio
async def test_async_rejection_bubbling():
    values = {}

    def add(delta):
        def accumulate(val):
            return val + delta
        return accumulate

    def err(_):
        raise ArithmeticError()

    p0 = Promise(lambda resolve, _: (yield from resolve(-1)))
    p1 = p0.then(add(3))
    p2 = p1.then(err)
    p3 = p2.then(add(10))
    p4 = p3.then(lambda v: values.__setitem__('sum', v))

    v0 = await p0

    assert p0.state is FULFILLED
    assert v0 == -1

    assert p1.state is FULFILLED
    assert p1.value == 2

    assert p2.state is REJECTED
    assert isinstance(p2.value, ArithmeticError)

    assert p3.state is REJECTED
    assert isinstance(p3.value, ArithmeticError)

    assert p4.state is REJECTED
    assert isinstance(p4.value, ArithmeticError)

    assert not values


@pytest.mark.asyncio
async def test_async_dynamic_chain1():
    values = {}

    def executor1(resolve, reject):
        yield from resolve(values)

    def on_fulfill1(values):
        def executor2(resolve, reject):
            yield from resolve(values.setdefault('container1', {}))
        return Promise(executor2)

    def on_fulfill2(container):
        container['item'] = 2 ** 32

    p = Promise(executor1).then(on_fulfill1).then(on_fulfill2)

    await p

    assert p.state is FULFILLED
    assert p.value is None
    assert values['container1']['item'] == 2 ** 32


@pytest.mark.asyncio
async def test_async_dynamic_chain2():
    values = {}
    p0 = Promise(lambda _, reject: (yield from reject(Promise(lambda resolve, _: (yield from resolve(16 * 4))))))  # noqa: ECE001
    p1 = p0.catch(lambda _: _)
    p2 = p1.then(lambda _: values.__setitem__('fixed', _))

    with pytest.raises(PromiseRejection) as excinfo:
        await p0

        assert p0.state is REJECTED
        assert isinstance(excinfo.value.value, Promise)
        assert p0.value.value == 64

    assert p1.state is FULFILLED
    assert p1.value == p0.value.value

    assert p2.state is FULFILLED
    assert values['fixed'] == 64


@pytest.mark.asyncio
async def test_async_cyclic_promise2():
    def f(r, _):
        yield from r(Promise(f))

    p = Promise(f)

    for _ in p:
        pass

    assert p.state is REJECTED
    assert isinstance(p.value, RecursionError)


@pytest.mark.asyncio
async def test_async_static_resolve():
    p = Promise.resolve(3)
    v = await p
    assert p.state is FULFILLED
    assert v == 3


@pytest.mark.asyncio
async def test_async_static_reject():
    p = Promise.reject(12)
    with pytest.raises(PromiseRejection):
        v = await p
        assert p.state is REJECTED
        assert v == 12


@pytest.mark.asyncio
async def test_async_static_reject_with_resolution():
    p = Promise(lambda _, reject: (yield from reject(Promise.resolve(1))))
    with pytest.raises(PromiseRejection):
        v = await p
        assert p.state is REJECTED
        assert isinstance(p.value, Promise)
        assert v.state is PENDING


@pytest.mark.asyncio
async def test_async_static_reject_catch():
    p = Promise(lambda _, reject: (yield from reject(Promise.resolve(1)))).catch(lambda v: v)
    v = await p
    assert p.is_fulfilled
    assert v == 1


@pytest.mark.asyncio
async def test_async_branching():
    values = {}

    def power_of(p):
        def calc(val):
            return val ** p
        return calc

    def setitem(k):
        def s(v):
            values[k] = v
        return s

    p0 = Promise(lambda r, _: (yield from r(random.randint(0, 64))))
    promises = {}

    for i in range(16):
        promises[i] = p0.then(power_of(i)).then(setitem(i))

    await p0

    for i in range(16):
        assert promises[i].is_fulfilled
        assert values[i] == p0.value ** i
