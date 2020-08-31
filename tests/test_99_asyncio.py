import asyncio
import random
import sys  # noqa
import time

import pytest

from notcallback.async_ import Promise

LEEWAY = 1.014
# SEED = random.randrange(sys.maxsize)
SEED = 7914905441759771169
RNG = random.Random(SEED)
print(f'RNG seed: {SEED}')


def timer():
    start = time.perf_counter()
    yield
    yield time.perf_counter() - start


def on_time(timed, expected, *, precision=4):
    precision = 10 ** precision
    timed = int(timed * precision) / precision
    return timed >= expected and timed <= expected * LEEWAY


@pytest.mark.asyncio
async def test_await():
    values = {}

    def t(resolve, reject):
        values['intermediate'] = yield asyncio.sleep(0.01)
        yield from resolve(5)

    values['final'] = await Promise(t)

    assert values['intermediate'] is None
    assert values['final'] == 5


@pytest.mark.asyncio
async def test_concurrently_await():
    start_timestamps = {}
    end_timestamps = {}
    duration = .5
    count = 10

    def create_timer(i):
        def start(resolve, reject):
            start_timestamps[i] = time.perf_counter()
            yield asyncio.sleep(duration)
            yield from resolve(i)
        return start

    def end(i):
        end_timestamps[i] = time.perf_counter()

    promises = [Promise(create_timer(i)).then(end) for i in range(count)]

    await asyncio.gather(*[p.awaitable() for p in promises])

    for p in promises:
        assert p.is_fulfilled

    for i in range(1, count):
        assert start_timestamps[i] < end_timestamps[i - 1]
        timed = end_timestamps[i] - start_timestamps[i]
        assert on_time(timed, duration)

    return promises


def _rand_setup():
    # Worse version of https://realpython.com/async-io-python/#the-asyncio-package-and-asyncawait

    # ANSI colors
    c = (
        '\033[0m',   # End of color
        '\033[36m',  # Cyan
        '\033[91m',  # Red
        '\033[35m',  # Magenta
    )

    records = {i: 10 - i - 1 for i in range(3)}
    expected_wait_times = {i: 0 for i in range(3)}
    run_times = {}

    def makerandom(idx: int, threshold: int = 6) -> Promise:
        print(c[idx + 1] + f'Initiated makerandom({idx}).' + c[0])

        def start(resolve, reject):
            run_times[idx] = time.perf_counter()
            yield from resolve()

        def make(_):
            return RNG.randint(0, 10)

        def evaluate(i):
            if i <= threshold:
                print(c[idx + 1] + f'makerandom({idx}) == {i} too low; retrying.' + c[0])
                expected_wait_times[idx] += idx + 1
                yield asyncio.sleep(idx + 1)
                return Promise.resolve().then(make).then(evaluate)
            else:
                print(c[idx + 1] + f'---> Finished: makerandom({idx}) == {i}' + c[0])
                run_times[idx] -= time.perf_counter()
                run_times[idx] *= -1
                return (idx, i)

        return Promise(start).then(make).then(evaluate)

    return records, expected_wait_times, run_times, makerandom


@pytest.mark.asyncio
@pytest.mark.skip(reason='Time-consuming')
async def test_rand():
    records, expected_wait_times, run_times, makerandom = _rand_setup()

    promises = [makerandom(i, 10 - i - 1) for i in range(3)]
    t = timer()
    next(t)
    results = dict(await asyncio.gather(*(p.awaitable() for p in promises)))
    duration = next(t)

    assert on_time(duration, max(expected_wait_times.values()))
    for k in records:
        assert on_time(run_times[k], expected_wait_times[k])
    for k, v in records.items():
        assert results[k] > v


@pytest.mark.asyncio
# @pytest.mark.skip(reason='Time-consuming')
async def test_rand_all():
    records, expected_wait_times, run_times, makerandom = _rand_setup()

    promises = [makerandom(i, 10 - i - 1) for i in range(3)]
    t = timer()
    next(t)
    results = dict(await Promise.all(*promises, concurrently=True))
    duration = next(t)

    assert on_time(duration, max(expected_wait_times.values()))
    for k in records:
        assert on_time(run_times[k], expected_wait_times[k])
    for k, v in records.items():
        assert results[k] > v


@pytest.mark.asyncio
# @pytest.mark.skip(reason='Time-consuming')
async def test_all_resolved():
    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i) for i in num]

    p = Promise.all(*promises, concurrently=True).then(sum)
    await p

    assert p.is_fulfilled
    assert p.value == sum(num)


@pytest.mark.asyncio
# @pytest.mark.skip(reason='Time-consuming')
async def test_all_reject_one():
    num = [random.randint(0, 100) for i in range(5)]
    promises = [Promise.resolve(i) for i in num]

    def r(_):
        raise ArithmeticError()

    promises[3] = promises[3].then(r)

    p = Promise.all(*promises, concurrently=True)
    with pytest.raises(ArithmeticError):
        await p


@pytest.mark.asyncio
# @pytest.mark.skip(reason='Time-consuming')
async def test_race_resolve():
    def wait(s):
        def e(r, _):
            yield asyncio.sleep(s)
            yield from r(s)
        return e

    num = [random.randint(0, 10) for i in range(5)]
    promises = [Promise(wait(i)) for i in num]

    p = Promise.race(*promises, concurrently=True)

    t = timer()
    next(t)
    await p
    duration = next(t)

    shortest = min(num)
    assert p.is_fulfilled
    assert p.value == shortest
    assert on_time(duration, shortest, precision=3)
