def simple_resolve(resolve, reject):
    yield 1
    yield 3
    yield from resolve(5)


def simple_reject(resolve, reject):
    yield 2
    yield 4
    yield from reject(6)


def exceptional_reject(resolve, reject):
    raise RecursionError()


def incorrect_resolve(resolve, reject):
    return resolve(True)
