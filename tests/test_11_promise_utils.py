import random

from notcallback import Promise


def test_all_resolved():
    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i) for i in num]

    p = Promise.all(*promises).then(sum)
    Promise.settle(p)

    assert p.is_fulfilled
    assert p.value == sum(num)


def test_all_reject_one():
    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i) for i in num]

    def r(_):
        raise ArithmeticError()

    promises[3] = promises[3].then(r)

    p = Promise.all(*promises).then(sum)
    Promise.settle(p)

    assert p.is_rejected
    assert p.is_rejected_due_to(ArithmeticError)

    for i in range(5):
        if i < 3:
            assert promises[i].is_fulfilled
        elif i == 3:
            assert promises[i].is_rejected
        else:
            assert promises[i].is_pending

    Promise.settle(promises[4])
    assert promises[4].is_fulfilled
    assert p.is_rejected


def test_race_resolve():
    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i) for i in num]

    p = Promise.race(*promises)
    Promise.settle(p)

    assert p.is_fulfilled
    assert p.value == num[0]

    for i in range(1, 5):
        assert promises[i].is_pending


def test_race_reject():
    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i) for i in num]

    def r(_):
        raise ArithmeticError()
    promises[0] = promises[0].then(r)

    p = Promise.race(*promises)
    Promise.settle(p)

    assert p.is_rejected_due_to(ArithmeticError)

    for i in range(1, 5):
        assert promises[i].is_pending

    Promise.settle(promises[4])
    assert promises[4].is_fulfilled
    assert p.is_rejected
