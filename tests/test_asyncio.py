import asyncio
import time

import pytest

from notcallback import Promise


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
            yield from asyncio.ensure_future(asyncio.sleep(duration))
            yield from resolve(i)
        return start

    def end(i):
        end_timestamps[i] = time.perf_counter()

    tasks = [Promise(create_timer(i)).then(end) for i in range(count)]

    await asyncio.gather(*tasks)

    for p in tasks:
        assert p.is_fulfilled

    for i in range(1, count):
        assert start_timestamps[i] < end_timestamps[i - 1]
        assert end_timestamps[i] - start_timestamps[i] > duration
        assert end_timestamps[i] - start_timestamps[i] < duration * 1.015

    return tasks
