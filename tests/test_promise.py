import pytest

from notcallback.promise import (FULFILLED, PENDING, REJECTED, Promise,
                                 PromisePending)

from .suppliers import (exceptional_reject, incorrect_resolve, simple_reject,
                        simple_resolve)


def non_generator(resolve, reject):
    for _ in resolve(32):
        pass


def multiple_settles(resolve, reject):
    yield from resolve(1)
    yield from reject(-1)


def test_pending():
    p = Promise(simple_resolve)
    assert p.state is PENDING


def test_resolve():
    p = Promise(simple_resolve)
    for _ in p:
        pass
    assert p.state is FULFILLED


def test_value_accessor():
    p = Promise(simple_resolve)
    with pytest.raises(PromisePending):
        p.value


def test_reject():
    p = Promise(simple_reject)
    for _ in p:
        pass
    assert p.state is REJECTED


def test_non_exception_reject():
    p = Promise(simple_reject)
    for _ in p:
        pass
    assert p.value == 6


def test_exceptional_reject():
    p = Promise(exceptional_reject)
    for _ in p:
        pass
    assert p.state is REJECTED
    assert isinstance(p.value, RecursionError)


def test_incorrect_resolve():
    p = Promise(incorrect_resolve)
    for _ in p:
        pass
    assert p.state is PENDING


def test_regular_func():
    p = Promise(non_generator)
    for _ in p:
        pass
    assert p.state is FULFILLED
    assert p.value == 32


def test_multiple_settles():
    p = Promise(multiple_settles)
    for _ in p:
        pass
    assert p.state is FULFILLED
    assert p.value == 1


# def test_immutability():
#     with pytest.warns(UnhandledPromiseRejectionWarning):
#         p = Promise(exceptional_reject)
#         for _ in p:
#             pass
#     with pytest.raises(PromiseLocked):
#         p._frozen = False
#         p._state = FULFILLED


def test_send():
    def raise_on_truthy(resolve, reject):
        if (yield 1):
            raise ArithmeticError()
        yield from resolve(True)

    p = Promise(raise_on_truthy)
    p.send(None)
    p.send(True)
    Promise.resolve(p)
    assert p.state is REJECTED
    assert isinstance(p.value, ArithmeticError)


def test_throw():
    p = Promise(simple_resolve)
    p.send(None)
    p.throw(RuntimeError())
    Promise.resolve(p)
    assert p.state is REJECTED
    assert isinstance(p.value, RuntimeError)
