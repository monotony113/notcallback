# MIT License
#
# Copyright (c) 2020 Tony Wu <tony[dot]wu(at)nyu[dot]edu>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import asyncio
import warnings
from typing import Any

from .exceptions import AsyncPromiseWarning, PromiseRejection, PromiseWarning, StopEarly
from .promise import Promise as BasePromise
from .utils import one_line_warning_format


class Promise(BasePromise):
    @classmethod
    def _ensure_future(cls, item):
        try:
            return asyncio.ensure_future(item)
        except TypeError:
            future = asyncio.Future()
            future.set_result(item)
            return future

    async def awaitable(self) -> Any:
        while True:
            try:
                try:
                    await self._ensure_future(next(self))
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.throw(e)
            except StopIteration:
                break
        if self.is_fulfilled:
            return self._value
        elif self.is_rejected:
            reason = self.value
            if isinstance(reason, BaseException):
                raise reason
            raise PromiseRejection(reason)
        with one_line_warning_format():
            warnings.warn(AsyncPromiseWarning(
                'Future is done but promise was not settled:\n%s'
                % self.__str__(),
            ))

    @classmethod
    async def _async_cancellable(cls, promise, futures):
        try:
            return await promise
        except StopEarly:
            for f in futures:
                f.cancel()

    @classmethod
    def _make_concurrent_executor(cls, this: Promise, promises):
        def executor(resolve, reject):
            futures = [asyncio.ensure_future(p.awaitable()) for p in promises]
            awaitables = asyncio.as_completed(futures)
            yield from awaitables
        return executor

    @classmethod
    def _dispatch_aggregate_methods(cls, func, *promises, concurrently=False):
        promise = func(*promises)
        if not concurrently:
            return promise
        promise._prepare(cls._make_concurrent_executor(promise, promises))
        return promise

    @classmethod
    def all(cls, *args, **kwargs):
        return cls._dispatch_aggregate_methods(super().all, *args, **kwargs)

    @classmethod
    def race(cls, *args, **kwargs):
        return cls._dispatch_aggregate_methods(super().race, *args, **kwargs)

    async def _dispatch_async_gen_method(self, func, *args, **kwargs):
        try:
            item = self._dispatch_gen_method(func, *args, **kwargs)
        except StopIteration:
            raise StopAsyncIteration()
        try:
            future = asyncio.ensure_future(item)
        except TypeError:
            return item
        try:
            return await self.asend(await future)
        except (GeneratorExit, StopAsyncIteration, PromiseWarning):
            raise
        except Exception as e:
            return await self.athrow(e)

    def __await__(self):
        return self.awaitable().__await__()

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self._dispatch_async_gen_method(self._exec.__next__)

    async def asend(self, val):
        return await self._dispatch_async_gen_method(self._exec.send, val)

    async def athrow(self, typ, val=None, tb=None):
        return await self._dispatch_async_gen_method(self._exec.throw, typ, val, tb)

    async def aclose(self):
        try:
            i = await self.athrow(GeneratorExit)
            while True:
                try:
                    await asyncio.ensure_future(i)
                except TypeError:
                    raise RuntimeError('Generator cannot yield non-awaitables during exit.')
                i = await self.__anext__()
        except (GeneratorExit, StopAsyncIteration):
            pass
        else:
            raise RuntimeError('Generator ignored GeneratorExit')
