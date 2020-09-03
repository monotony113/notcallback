import random

import pytest

from notcallback import Promise
from notcallback.exceptions import PromiseAggregateError

pytestmark = pytest.mark.filterwarnings('ignore::notcallback.exceptions.UnhandledPromiseRejectionWarning')


def test_all_resolved():
    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i) for i in num]

    p = Promise.all(*promises).then(sum)
    Promise.settle(p)

    assert p.is_fulfilled
    assert p.value == sum(num)


def test_all_reject_one():
    resolution_order = []

    def record(item):
        resolution_order.append(item)
        return item

    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i).then(record) for i in num]

    def r(_):
        raise ArithmeticError()

    promises[2] = promises[2].then(r).finally_(lambda: record('error'))

    p = Promise.all(*promises).then(sum)
    Promise.settle(p)

    assert p.is_rejected
    assert p.is_rejected_due_to(ArithmeticError)

    for i in range(5):
        if i == 2:
            assert promises[i].is_rejected
        else:
            assert promises[i].is_fulfilled

    expected_order = num[:3] + ['error'] + num[3:]
    assert all(i == j for i, j in zip(resolution_order, expected_order))


def test_race_resolve():
    resolution_order = []

    def record(item):
        resolution_order.append(item)
        return item

    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i).then(record) for i in num]

    p = Promise.race(*promises)
    p.then(lambda _: record('1st'))
    Promise.settle(p)

    assert p.is_fulfilled
    assert p.value == num[0]

    expected_order = num[:1] + ['1st'] + num[1:]
    assert all(i == j for i, j in zip(resolution_order, expected_order))


def test_race_reject():
    resolution_order = []

    def record(item):
        resolution_order.append(item)
        return item

    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i).then(record) for i in num]

    def r(_):
        raise ArithmeticError()
    promises[0] = promises[0].then(r)

    p = Promise.race(*promises)
    p.finally_(lambda: record('error'))
    Promise.settle(p)

    assert p.is_rejected_due_to(ArithmeticError)

    for i in range(5):
        if i == 0:
            assert promises[i].is_rejected
        else:
            assert promises[i].is_fulfilled

    expected_order = num[:1] + ['error'] + num[1:]
    assert all(i == j for i, j in zip(resolution_order, expected_order))


def test_all_settled():
    def task1(r, _):
        yield from r(100)

    def task2(_, r):
        yield from r(-100)

    def task3(r, _):
        raise BufferError

    def check(results):
        assert results[0].is_fulfilled
        assert results[0].value == 100
        assert results[1].is_rejected
        assert results[1].value == -100
        assert results[2].is_rejected_due_to(BufferError)

    p = Promise.all_settled(*[Promise(t) for t in [task1, task2, task3]]).then(check)
    Promise.settle(p)
    assert p.is_fulfilled


def test_any():
    resolution_order = []

    def record(item):
        resolution_order.append(item)
        return item

    num = [random.randint(0, 100) for i in range(5)]
    promises = [
        *[Promise.reject(i).then(record) for i in num[:2]],
        Promise.resolve(num[2]).then(record),
        *[Promise.resolve(i).then(record) for i in num[3:]],
    ]

    p = Promise.any(*promises)
    p.then(lambda _: record('1st_resolved'))
    Promise.settle(p)

    assert p.is_fulfilled
    assert p.value == num[2]

    expected_order = num[2:3] + ['1st_resolved'] + num[3:]
    assert all(i == j for i, j in zip(resolution_order, expected_order))


def test_any_no_resolve():
    resolution_order = []

    def record(item):
        resolution_order.append(item)
        return item

    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.reject(i).then(record) for i in num]

    p = Promise.any(*promises)
    Promise.settle(p)

    assert p.is_rejected_due_to(PromiseAggregateError)


def test_empty():
    Promise.settle(Promise.all())
    Promise.settle(Promise.race())
    Promise.settle(Promise.all_settled())
    Promise.settle(Promise.any())
