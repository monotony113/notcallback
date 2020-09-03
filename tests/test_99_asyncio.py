import asyncio
import random
import sys  # noqa
import time

import pytest

from notcallback.async_ import Promise
from notcallback.exceptions import PromiseAggregateError

pytestmark = pytest.mark.filterwarnings('ignore::notcallback.exceptions.UnhandledPromiseRejectionWarning')

LEEWAY = 1.014
# SEED = random.randrange(sys.maxsize)
SEED = 8848235470363262384
RNG = random.Random(SEED)
print(f'RNG seed: {SEED}')


def timer():
    start = time.perf_counter()
    yield start
    yield time.perf_counter() - start


def on_time(timed, expected, *, precision=3):
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
async def test_all_reject_one():
    splits = {}

    def wait(s):
        def e(r, _):
            yield asyncio.sleep(s)
            yield from r(s)
        return e

    def record(k):
        splits[k] = time.perf_counter()
        return k

    def throw(_):
        raise BlockingIOError

    num = [RNG.randint(0, 10) for i in range(5)]
    promises = [
        *[Promise(wait(i)).then(record) for i in num[:2]],
        Promise(wait(num[2])).then(throw),
        *[Promise(wait(i)).then(record) for i in num[3:]],
    ]

    p = Promise.all(*promises, concurrently=True)
    p.catch(lambda _: record('err'))

    t = timer()
    start = next(t)
    try:
        with pytest.raises(BlockingIOError):
            await p
    except BlockingIOError:
        pass
    duration = next(t)
    splits = {k: v - start for k, v in splits.items()}

    assert p.is_rejected_due_to(BlockingIOError)

    latest = max(num)
    assert on_time(splits['err'], num[2])
    assert on_time(duration, latest)
    for k, v in splits.items():
        if isinstance(k, int):
            assert on_time(v, k)


@pytest.mark.asyncio
# @pytest.mark.skip(reason='Time-consuming')
async def test_race_resolve():
    splits = {}

    def wait(s):
        def e(r, _):
            yield asyncio.sleep(s)
            yield from r(s)
        return e

    def record(k):
        splits[k] = time.perf_counter()
        return k

    num = [RNG.randint(0, 10) for i in range(5)]
    promises = [Promise(wait(i)).then(record) for i in num]

    p = Promise.race(*promises, concurrently=True)
    p.then(lambda _: record('1st'))

    t = timer()
    start = next(t)
    result = await p
    duration = next(t)
    splits = {k: v - start for k, v in splits.items()}

    assert p.is_fulfilled

    earliest = min(num)
    latest = max(num)
    assert result == earliest
    assert on_time(splits['1st'], earliest)
    assert on_time(duration, latest)
    for k, v in splits.items():
        if isinstance(k, int):
            assert on_time(v, k)


@pytest.mark.asyncio
# @pytest.mark.skip(reason='Time-consuming')
async def test_race_reject():
    def wait(s):
        def e(r, _):
            yield asyncio.sleep(s)
            yield from r(s)
        return e

    def r(_):
        raise EOFError

    num = [RNG.randint(0, 10) for i in range(5)]
    promises = [Promise(wait(i)) for i in num]

    earliest = min(num)
    index = num.index(earliest)
    promises[index] = promises[index].then(r)

    p = Promise.race(*promises, concurrently=True)

    t = timer()
    next(t)
    try:
        with pytest.raises(EOFError):
            await p
    except EOFError:
        pass

    duration = next(t)
    latest = max(num)
    assert on_time(duration, latest)

    assert p.is_rejected_due_to(EOFError)
    for i in range(5):
        if i == index:
            assert promises[i].is_rejected_due_to(EOFError)
        else:
            assert promises[i].is_fulfilled


@pytest.mark.asyncio
# @pytest.mark.skip(reason='Time-consuming')
async def test_all_settled():
    def task1(r, _):
        yield from r(100)

    def task2(_, r):
        yield from r(-100)

    def task3(r, _):
        yield asyncio.sleep(.5)
        yield from r(.5)

    def task4(r, _):
        raise BufferError

    def check(results):
        assert results[0].is_fulfilled
        assert results[0].value == 100
        assert results[1].is_rejected
        assert results[1].value == -100
        assert results[2].is_fulfilled
        assert results[2].value == .5
        assert results[3].is_rejected_due_to(BufferError)

    p = Promise.all_settled(*[Promise(t) for t in [task1, task2, task3, task4]], concurrently=True).then(check)
    await p
    assert p.is_fulfilled


@pytest.mark.asyncio
async def test_any():
    splits = {}

    def wait(s):
        def e(r, _):
            yield asyncio.sleep(s)
            yield from r(s)
        return e

    def record(k):
        splits[k] = time.perf_counter()
        return k

    num = sorted(RNG.randint(0, 10) for i in range(5))
    promises = [
        Promise(wait(num[0])).then(lambda _: Promise.reject(_)),
        *[Promise(wait(i)).then(record) for i in num[1:]],
    ]

    p = Promise.any(*promises, concurrently=True)
    p.then(lambda _: record('found'))

    t = timer()
    start = next(t)
    result = await p
    duration = next(t)
    splits = {k: v - start for k, v in splits.items()}

    assert p.is_fulfilled

    latest = max(num)
    assert result == num[1]
    assert on_time(splits['found'], num[1])
    assert on_time(duration, latest)
    for k, v in splits.items():
        if isinstance(k, int):
            assert on_time(v, k)


@pytest.mark.asyncio
async def test_any_no_resolve():

    def wait(s):
        def e(_, r):
            yield asyncio.sleep(s)
            yield from r(s)
        return e

    num = [RNG.randint(0, 10) for i in range(5)]
    promises = [Promise(wait(i)) for i in num]

    p = Promise.any(*promises, concurrently=True)

    t = timer()
    next(t)
    try:
        with pytest.raises(PromiseAggregateError):
            await p
    except PromiseAggregateError:
        pass
    duration = next(t)

    assert p.is_rejected_due_to(PromiseAggregateError)

    latest = max(num)
    assert on_time(duration, latest)
