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
