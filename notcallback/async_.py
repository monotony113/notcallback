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

"""Promise with asyncio."""

import asyncio
import warnings

from .exceptions import (AsyncPromiseWarning, PromiseException,
                         PromiseRejection, PromiseWarning)
from .promise import Promise as BasePromise
from .utils import one_line_warning_format

try:
    from .promise import PromiseType
except ImportError:
    pass


class Promise(BasePromise):
    """The Promise class extended with async/await support via asyncio.

    This class is API-compatible with `notcallback.promise.Promise` but comes with additional
    methods that enable true asynchronous programming.

    Features
    --------
    - Promises can be `await`ed
        - `yield`ing an async function when the Promise is being `await`ed will schedule and `await` that function
        - If an `await`ed Promise eventually rejects, the rejection is raised as an exception, allowing exception
        handling using try-except; this mimics the `async/await` behavior in JavaScript.
    - Promises are `AsyncIterator`s, meaning they can be used in `async for`
        - Any regular values are `yield`ed, and any async functions are `await`ed
    - `Promise.all()`, `Promise.race()`, `Promise.all_settled()`, and `Promise.any()` support concurrent execution
    of Promises via `asyncio.as_completed()` (default disabled)

    Interfaces
    ----------
    This class will now be a subclass to all of the following ABCs from the collections.abc module:
    - `Iterable`: `__iter__`
    - `Iterator`: `__iter__`, `__next__`
    - `Generator`: `__iter__`, `__next__`, `send`, `throw`, `close`
    - `Awaitable`: `__await__`
    - `Coroutine`: `__await__`, `__iter__`, `__next__`, `send`, `throw`, `close`,
    - `AsyncIterable`: `__aiter__`,
    - `AsyncIterator`: `__aiter__`, `__anext__`,
    - `AsyncGenerator`: `__aiter__`, `__anext__`, `asend`, `athrow`, `aclose`

    This class supports asyncio by translating methods supported by traditional generators to their
    async/await equivalents, thus acting as a middle layer between asyncio and user-defined functions.

    Note that the "support" here means interface-level support only: you can use Promise in async/await functions,
    but you cannot promisify async functions or use async functions as on-fulfill handlers. Because you should not:
    if you already have a function defined with `async def`, you should work with asyncio directly.

    Arguably, this is doing the opposite of what PEP 492 and 525 are trying to do: whereas these 2 PEPs make clear
    the distinction between a traditional generator, a coroutine, and an async generator, such that,

    - you cannot `yield from` or iterate over an `async def` function,
    - you cannot (in the future) `await` a generator-based coroutine,
    - you must use `async for` for async iterators,

    The Promise class here allows you to use all of them:

    >>> for item in Promise(...): ...
    >>> return next(Promise(...))

    >>> return Promise(...).send(...)
    >>> yield from Promise(...)

    >>> await Promise(...)
    >>> async for item in Promise(...): ...
    >>> await Promise(...).athrow(...)

    Note on Coroutines vs Generators:
    ---------------------------------
    Except for `__await__`, Python generators and coroutines share the same method signatures (a relic of generator-
    based coroutines).

    Because it it not possibe at run time to determine whether a Promise is being used as a generator or a coroutine,
    this Promise class only implements `send()`, `throw()`, and `close()` to be suitable for use as a generator.
    This means that although Promise is a subclass of collections.abc.Coroutine, it should not be used like one in an
    async context, and attempts to do so most likely will result in unexpected behaviors.

    Some asyncio functions, such as `asyncio.gather`, perform runtime check to see whether it is receiving a
    `Awaitable` or a `Coroutine`, and act differently based on this information. Notably, asyncio explicitly forbids
    the use of `yield from` in a coroutine via a cryptic runtime check, and will throw a `RuntimeError` when it sees
    a Promise containing at least one `yield from` expressions.

    Within an async function, if you want Promises with async functionality and do not need to yield intermediate values,
    use `await` (there is also a `Promise().awaitable()` method). If you do need intermedia values, use `async for`.
    """

    @classmethod
    def _ensure_future(cls, item):
        try:
            return asyncio.ensure_future(item)
        except TypeError:
            future = asyncio.Future()
            future.set_result(item)
            return future

    async def awaitable(self):
        """Return an `Awaitable`. `await`ing which will settle the Promise.

        Raises
        ------
        reason
        PromiseRejection
            If the Promise eventually rejects, the reason is raised.
        """
        value = None
        while True:
            try:
                try:
                    value = await self._ensure_future(self.send(value))
                except asyncio.CancelledError:
                    break
                except BaseException as e:
                    value = self.throw(e)
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
                'Future is done but Promise was not settled:\n%s'
                % self.__str__(),
            ))

    @classmethod
    async def _ensure_completion(cls, promise):
        try:
            return await promise.awaitable()
        except (PromiseException, GeneratorExit, KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            pass

    @classmethod
    def _make_concurrent_executor(cls, this: PromiseType, promises):
        def executor(resolve, reject):
            futures = [asyncio.ensure_future(cls._ensure_completion(p)) for p in promises]
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
    def all(cls, *args, **kwargs) -> PromiseType:
        """Return a new Promise that fulfills when all the provided Promises are FULFILLED and rejects if any of them is rejected.

        Parameters
        ----------
        *promises : Promise
            Promises to be evaluated
        concurrently : bool, optional
            whether to run the Promises concurrently using asyncio; if not, Promises are run sequetially, by default False

        Description
        -----------
        Employs the same logic as the non-async version (`notcallback.promise.Promise.all`), but with optional support
        for concurrency.

        Notes
        -----
        Like its non-async counterpart, all Promises are `await`ed and run to completion whether or not `Promise.all()`
        rejects early. This is so that asyncio event loops can properly shutdown without complaining about never-awaited coroutines.
        If the Promise rejects early, the `on_reject` handler is scheduled immediately.

        Returns
        -------
        Promise
            The new Promise
        """
        return cls._dispatch_aggregate_methods(super().all, *args, **kwargs)

    @classmethod
    def race(cls, *args, **kwargs) -> PromiseType:
        """Return a new Promise that fulfills/rejects as soon as one of the Promises fulfills/rejects.

        Parameters
        ----------
        *promises : Promise
            Promises to be evaluated
        concurrently : bool, optional
            whether to run the Promises concurrently using asyncio; if not, Promises are run sequetially, by default False

        Description
        -----------
        Employs the same logic as the non-async version (`notcallback.promise.Promise.race`), but with optional support
        for concurrency.

        Notes
        -----
        Like its non-async counterpart, all Promises are `await`ed and run to completion in all cases.
        This is so that asyncio event loops can properly shutdown without complaining about never-awaited coroutines.

        This means that `Promise.race()`, when `await`ed, will finish after the Promise that took _longest_ to settle,
        and not the _shortest_ one. However, the Promise itself settles as soon as the one of the Promises is settled,
        and the handlers are scheduled immediately.

        Returns
        -------
        Promise
            The new Promise
        """
        return cls._dispatch_aggregate_methods(super().race, *args, **kwargs)

    @classmethod
    def all_settled(cls, *args, **kwargs) -> PromiseType:
        """Return a new Promise that fulfills when all the Promises have settled i.e. either FULFILLED or REJECTED.

        Parameters
        ----------
        *promises : Promise
            Promises to be evaluated
        concurrently : bool, optional
            whether to run the Promises concurrently using asyncio; if not, Promises are run sequetially, by default False

        Description
        -----------
        Employs the same logic as the non-async version (`notcallback.promise.Promise.all_settled`), but with optional support
        for concurrency.

        This Promise always fulfills with the list of Promises provided.
        """
        return cls._dispatch_aggregate_methods(super().all_settled, *args, **kwargs)

    @classmethod
    def any(cls, *args, **kwargs) -> PromiseType:
        """Return a new Promise that ignore rejections among the provided Promises and fulfills upon the first fulfillment.

        If all Promises reject, it will reject with a PromiseAggregateError.

        Parameters
        ----------
        *promises : Promise
            Promises to be evaluated
        concurrently : bool, optional
            whether to run the Promises concurrently using asyncio; if not, Promises are run sequetially, by default False

        Description
        -----------
        Employs the same logic as the non-async version (`notcallback.promise.Promise.any`), but with optional support
        for concurrency.

        Note
        ----
        Like its non-async counterpart, all Promises are `await`ed and run to completion in all cases.
        This is so that asyncio event loops can properly shutdown without complaining about never-awaited coroutines.

        This means that `Promise.any()`, when `await`ed, will finish after the Promise that took _longest_ to settle,
        and not as long as the first Promise to fulfill. However, the Promise itself settles as soon as the the first Promise
        to fulfill and the handlers are scheduled immediately.
        """
        return cls._dispatch_aggregate_methods(super().any, *args, **kwargs)

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
        except (PromiseException, PromiseWarning, GeneratorExit, KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:
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
