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

import asyncio
from typing import Any

from .exceptions import PromiseRejection, PromiseWarning


def with_async_addons(cls):
    def _ensure_future(item):
        try:
            return asyncio.ensure_future(item)
        except TypeError:
            future = asyncio.Future()
            future.set_result(item)
            return future

    def __await__(self):
        for i in self:
            yield from _ensure_future(i)
        if self.is_fulfilled:
            return self._value
        elif self.is_rejected:
            reason = self.value
            if isinstance(reason, BaseException):
                raise reason
            raise PromiseRejection(reason)

    def __aiter__(self):
        return self

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
                    a = asyncio.ensure_future(i)
                    await a
                except TypeError:
                    raise RuntimeError('Generator cannot yield non-awaitables during exit.')
                i = await self.__anext__()
        except (GeneratorExit, StopAsyncIteration):
            pass
        else:
            raise RuntimeError('Generator ignored GeneratorExit')

    async def awaitable(self) -> Any:
        return await self

    cls.awaitable = awaitable
    cls._dispatch_async_gen_method = _dispatch_async_gen_method
    cls.__await__ = __await__
    cls.__aiter__ = __aiter__
    cls.__anext__ = __anext__
    cls.asend = asend
    cls.athrow = athrow
    cls.aclose = aclose

    return cls
