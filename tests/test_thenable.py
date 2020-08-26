from promise.promise import Promise, PENDING, FULFILLED, REJECTED

from .suppliers import simple_resolve, simple_reject, exceptional_reject, incorrect_resolve


def test_typecheck():
    p = Promise(simple_resolve).then()
    assert isinstance(p, Promise)
    p = Promise(simple_resolve).catch()
    assert isinstance(p, Promise)
    p = Promise(simple_resolve).finally_()
    assert isinstance(p, Promise)


def test_on_fulfill():
    values = {}

    p = Promise(simple_resolve)
    p2 = p.then(lambda val: values.__setitem__('result', val))
    for _ in p2:
        pass

    assert p.state is FULFILLED
    assert p.value == 5
    assert p2.state is FULFILLED
    assert values['result'] == 5


def test_default_fulfill():
    p = Promise(lambda resolve, reject: (yield from resolve(12))).then()
    for _ in p:
        pass
    assert p.is_fulfilled
    assert p.value == 12


def test_on_fulfill_cascade():
    values = {}

    p = Promise(simple_resolve)
    p2 = p.then(lambda val: values.__setitem__('result1', val))
    p3 = p2.then(lambda val: values.__setitem__('result2', val) or 24)

    for _ in p2:
        pass

    assert p.state is FULFILLED
    assert p.value == 5
    assert values['result1'] == 5

    assert p2.state is FULFILLED
    assert p2.value is None
    assert values['result2'] is None

    assert p3.state is FULFILLED
    assert p3.value == 24


def test_fulfiller_exception():
    values = {}

    def throw(val):
        raise TypeError()

    p = Promise(simple_resolve)
    p2 = p.then(throw)
    p3 = p2.then(lambda val: values.__setitem__('result1', val) or 24)

    for _ in p2:
        pass

    assert p.state is FULFILLED
    assert p.value == 5

    assert p2.state is REJECTED
    assert isinstance(p2.value, TypeError)

    assert p3.state is REJECTED
    assert isinstance(p3.value, TypeError)

    assert p2.value is p3.value
    assert not values


def test_unhandled_reject():
    values = {}

    p = Promise(simple_reject)
    p2 = p.then(lambda val: values.__setitem__('result', val))
    for _ in p2:
        pass

    assert p.state is REJECTED
    assert p.value == 6
    assert p2.state is REJECTED
    assert p2.value == p.value
    assert not values


def test_on_reject():
    values = {}

    p = Promise(exceptional_reject)
    p2 = p.catch(lambda reason: values.__setitem__('reason', reason))

    for _ in p2:
        pass

    assert p.state is REJECTED
    assert isinstance(p.value, RecursionError)

    assert p2.state is FULFILLED
    assert p2.value is None
    assert isinstance(values['reason'], RecursionError)


def test_fulfiller_chain():
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

    for _ in p:
        pass

    assert p.state is FULFILLED
    assert p.value is None
    assert values['sum'] == 18


def test_rejection_bubbling():
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

    for _ in p0:
        pass

    assert p0.state is FULFILLED
    assert p0.value == -1

    assert p1.state is FULFILLED
    assert p1.value == 2

    assert p2.state is REJECTED
    assert isinstance(p2.value, ArithmeticError)

    assert p3.state is REJECTED
    assert isinstance(p3.value, ArithmeticError)

    assert p4.state is REJECTED
    assert isinstance(p4.value, ArithmeticError)

    assert not values


def test_rejection_recovery():
    values = {}

    p = Promise(exceptional_reject)
    p1 = p.then()
    p2 = p1.catch(lambda _: 128)
    p3 = p2.then(lambda v: values.__setitem__('result', v ** v))

    for _ in p2:
        pass

    assert p2.state is FULFILLED
    assert p2.value == 128

    assert p3.state is FULFILLED
    assert p3.value is None
    assert values['result'] == 128 ** 128


def test_pending_predecessor():
    p = Promise(incorrect_resolve).then()
    for _ in p:
        pass

    assert p.state is PENDING


def test_dynamic_chain1():
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

    for _ in p:
        pass

    assert p.state is FULFILLED
    assert p.value is None
    assert values['container1']['item'] == 2 ** 32


def test_dynamic_chain2():
    values = {}
    p0 = Promise(lambda _, reject: (yield from reject(Promise(lambda resolve, _: (yield from resolve(16 * 4))))))  # noqa: ECE001
    p1 = p0.catch(lambda _: _)
    p2 = p1.then(lambda _: values.__setitem__('fixed', _))

    for _ in p0:
        pass

    assert p0.state is REJECTED
    assert isinstance(p0.value, Promise)
    assert p0.value.value == 64

    assert p1.state is FULFILLED
    assert p1.value == p0.value.value

    assert p2.state is FULFILLED
    assert values['fixed'] == 64


def test_cyclic_promise1():
    def executor(resolve, reject):
        yield from resolve(Promise(executor))

    def on_fulfill(promise):
        return promise

    p = Promise(executor).then(on_fulfill)

    for _ in p:
        pass

    assert p.state is REJECTED
    assert isinstance(p.value, RecursionError)


def test_cyclic_promise2():
    def f(r, _):
        yield from r(Promise(f))

    p = Promise(f)

    for _ in p:
        pass

    assert p.state is REJECTED
    assert isinstance(p.value, RecursionError)


def test_cyclic_promise3():
    def on_fulfill(_):
        return Promise.resolve(True).then(on_fulfill)

    p = Promise.resolve(True).then(on_fulfill)

    for _ in p:
        pass

    assert p.state is REJECTED
    assert isinstance(p.value, RecursionError)
