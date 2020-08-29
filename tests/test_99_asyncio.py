import asyncio
import time

import pytest

from notcallback import Promise

LEEWAY = 1.014


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
async def test_concurrent_await():
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
        assert end_timestamps[i] - start_timestamps[i] > duration
        assert end_timestamps[i] - start_timestamps[i] < duration * LEEWAY

    return promises


@pytest.mark.asyncio
# @pytest.mark.skip(reason='Time-consuming')
async def test_rand():
    # Worse version of https://realpython.com/async-io-python/#the-asyncio-package-and-asyncawait
    import random

    random.seed(444)
    # ANSI colors
    c = (
        '\033[0m',   # End of color
        '\033[36m',  # Cyan
        '\033[91m',  # Red
        '\033[35m',  # Magenta
    )

    conf = {i: 10 - i - 1 for i in range(3)}
    expected_wait_times = {i: 5e-4 for i in range(3)}
    run_times = {}

    def makerandom(idx: int, threshold: int = 6) -> Promise:
        print(c[idx + 1] + f'Initiated makerandom({idx}).' + c[0])

        def start(resolve, reject):
            run_times[idx] = time.perf_counter()
            yield from resolve()

        def make(_):
            return random.randint(0, 10)

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

    promises = [makerandom(i, 10 - i - 1) for i in range(3)]
    start = time.perf_counter()
    results = dict(await asyncio.gather(*(p.awaitable() for p in promises)))

    assert time.perf_counter() - start < max(expected_wait_times.values()) * LEEWAY
    for k in conf:
        assert run_times[k] < expected_wait_times[k] * LEEWAY
    for k, v in conf.items():
        assert results[k] > v
