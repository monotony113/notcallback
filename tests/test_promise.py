import pytest
from promise.promise import Promise, PENDING, FULFILLED, REJECTED

from .suppliers import simple_resolve, simple_reject, exceptional_reject, incorrect_resolve


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
    with pytest.raises(ValueError) as excinfo:
        p.value
    assert str(excinfo.value) == 'Promise is not settled yet.'


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


def test_immutability():
    p = Promise(exceptional_reject)
    for _ in p:
        pass
    with pytest.raises(ValueError) as excinfo:
        p._frozen = False
        p._state = FULFILLED
    assert str(excinfo.value) == 'Promise is already settled.'
