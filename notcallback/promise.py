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

from collections import deque
from inspect import isgenerator
from typing import Any, Generator, Tuple

from .base import FULFILLED, PENDING, REJECTED, PromiseState
from .exceptions import (PromiseException, PromisePending, PromiseRejection,
                         PromiseWarning, StopEarly)
from .utils import _CachedGeneratorFunc, as_generator_func


def _passthrough(value):
    return value


def _reraise(exc):
    if isinstance(exc, BaseException):
        raise exc
    raise PromiseRejection(exc)


class Promise:
    def __init__(self, executor, *, named=None):
        self._state: PromiseState = PENDING
        self._value: Any = None

        self.__qualname__ = '%s at %s' % (self.__class__.__name__, hex(id(self)))

        self._exec: Generator
        self._hash: int
        self._name: str = None
        self._prepare(executor, named)

        self._resolvers = deque()

    def _prepare(self, executor, named=None):
        self._exec = as_generator_func(executor)(self._make_resolution, self._make_rejection)
        self._hash = hash(self._exec)
        if not self._name or named:
            self._name = named or executor.__name__

    @property
    def state(self) -> PromiseState:
        return self._state

    @property
    def value(self) -> Any:
        if self._state is PENDING:
            raise PromisePending()
        return self._value

    @property
    def is_pending(self) -> bool:
        return self._state is PENDING

    @property
    def is_settled(self) -> bool:
        return self._state is not PENDING

    @property
    def is_fulfilled(self) -> bool:
        return self._state is FULFILLED

    @property
    def is_rejected(self) -> bool:
        return self._state is REJECTED

    def is_rejected_due_to(self, exc_class) -> bool:
        return self._state is REJECTED and isinstance(self._value, exc_class)

    def _add_resolver(self, resolver):
        self._resolvers.append(resolver)

    def _make_resolution(self, value=None):
        yield from self._resolve_promise(self, value)

    def _make_rejection(self, reason=None):
        yield from self._reject(reason)

    def _resolve(self, value):
        if self._state is PENDING:
            self._state = FULFILLED
            self._value = value
        yield from self._run_resolvers()

    def _reject(self, reason):
        if self._state is PENDING:
            self._state = REJECTED
            if isinstance(reason, PromiseRejection):
                reason = reason.value
            self._value = reason
        yield from self._run_resolvers()

    def _run_resolvers(self):
        while self._resolvers:
            yield from self._resolvers.popleft()(self)

    def _adopt(self, other: Promise):
        if other._state is FULFILLED:
            yield from self._resolve(other._value)
        if other._state is REJECTED:
            yield from self._reject(other._value)

    @classmethod
    def _resolve_promise(cls, this: Promise, returned: Any):
        if this is returned:
            raise PromiseException() from TypeError('A Promise cannot resolve to itself.')

        if isinstance(returned, cls):
            yield from returned
            yield from this._adopt(returned)
            return returned

        if getattr(returned, 'then', None) and callable(returned.then):
            return (yield from cls._resolve_promise_like(this, returned))

        return (yield from this._resolve(returned))

    def _successor_executor(self, resolve=None, reject=None):
        if self._state is PENDING:
            yield from self
        else:
            yield from self._run_resolvers()

    def then(self, on_fulfill=_passthrough, on_reject=_reraise) -> Promise:
        cls = self.__class__
        promise = cls(
            self._successor_executor,
            named='%s|%s,%s' % (self._name, on_fulfill.__name__, on_reject.__name__),
        )
        handlers = {
            FULFILLED: _CachedGeneratorFunc(on_fulfill),
            REJECTED: _CachedGeneratorFunc(on_reject),
        }

        def resolver(settled: cls):
            try:
                handler = handlers[settled._state](settled._value)
                yield from handler
                yield from self._resolve_promise(promise, handler.result)
            except PromiseException:
                raise
            except Exception as e:
                yield from promise._reject(e)
        self._add_resolver(resolver)

        return promise

    def catch(self, on_reject=_reraise) -> Promise:
        return self.then(_passthrough, on_reject)

    def finally_(self, on_settle=lambda: None) -> Promise:
        cls = self.__class__
        promise = cls(self._successor_executor, named='chained:%s' % self._name)
        on_settle = _CachedGeneratorFunc(on_settle)

        def resolver(settled: cls):
            try:
                yield from on_settle()
                yield from promise._adopt(self)
            except PromiseException:
                raise
            except Exception as e:
                yield from promise._reject(e)
        self._add_resolver(resolver)

        return promise

    @classmethod
    def resolve(cls, value=None) -> Promise:
        return cls(lambda resolve, _: (yield from resolve(value)))

    @classmethod
    def reject(cls, reason=None) -> Promise:
        return cls(lambda _, reject: (yield from reject(reason)))

    @classmethod
    def settle(cls, promise: Promise) -> Promise:
        if not isinstance(promise, cls):
            raise TypeError(type(promise))
        for i in promise:
            pass
        return promise

    @classmethod
    def _make_multi_executor(cls, promises):
        def executor(resolve, reject):
            for p in promises:
                try:
                    yield from p._successor_executor()
                except StopEarly:
                    raise StopIteration
        return executor

    @classmethod
    def all(cls, *promises) -> Promise:
        fulfillments = {}
        promise = cls(cls._make_multi_executor(promises), named='all')

        def resolver(settled: cls):
            if promise._state is not PENDING:
                return
            if settled._state is REJECTED:
                yield from promise._reject(settled._value)
                raise StopEarly
            fulfillments[settled] = settled._value
            if len(fulfillments) == len(promises):
                results = [fulfillments[p] for p in promises]
                yield from promise._resolve(results)
                raise StopEarly

        for p in promises:
            p._add_resolver(resolver)
        return promise

    @classmethod
    def race(cls, *promises):
        promise = cls(cls._make_multi_executor(promises), named='race')

        def resolver(settled: cls):
            if promise._state is not PENDING:
                return
            yield from promise._adopt(settled)
            raise StopEarly

        for p in promises:
            p._add_resolver(resolver)
        return promise

    def __iter__(self):
        return self

    def __next__(self):
        return self._dispatch_gen_method(self._exec.__next__)

    def send(self, value):
        return self._dispatch_gen_method(self._exec.send, value)

    def throw(self, typ, val=None, tb=None):
        return self._dispatch_gen_method(self._exec.throw, typ, val, tb)

    def close(self):
        try:
            self.throw(GeneratorExit)
        except (GeneratorExit, StopIteration):
            pass
        else:
            raise RuntimeError('Generator ignored GeneratorExit')

    def _dispatch_gen_method(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (StopIteration, PromiseWarning):
            raise
        except Exception as e:
            self._exec = self._reject(e)
            return next(self._exec)

    def __eq__(self, value):
        return (
            self.__class__ is value.__class__
            and self._state is not PENDING
            and self._state is value._state
            and self._value == value._value
        )

    def __hash__(self):
        return hash((self.__class__, self._hash))

    def __str__(self):
        s1 = "<Promise '%s' at %s (%s)" % (self._name, hex(id(self)), self._state.value)
        if self._state is PENDING:
            return s1 + '>'
        elif self._state is FULFILLED:
            return s1 + ' => ' + str(self._value) + '>'
        else:
            return s1 + ' => ' + repr(self._value) + '>'

    def __repr__(self):
        return '<%s %s at %s (%s): %s>' % (
            self.__class__.__name__, repr(self._exec), hex(id(self)),
            self._state.value, repr(self._value),
        )

    @property
    def __name__(self):
        return self.__str__()

    @classmethod
    def _resolve_promise_like(cls, this: Promise, obj):
        calls: Tuple[PromiseState, Any] = []

        def on_fulfill(val):
            calls.append((FULFILLED, val))

        def on_reject(reason):
            calls.append((REJECTED, reason))

        try:
            promise = obj.then(on_fulfill, on_reject)
            if isgenerator(obj):
                yield from promise
        except PromiseException:
            raise
        except Exception as e:
            if not calls:
                calls.append((REJECTED, e))
        finally:
            if not calls:
                return (yield from this._resolve(obj))
            state, value = calls[0]
            if state is FULFILLED:
                return (yield from this._resolve(value))
            return (yield from this._reject(value))

    def _not_async(self, *args, **kwargs):
        raise NotImplementedError(
            '%s is not async-compatible.\n'
            'To enable async functionality, use notcallback.async_.Promise'
            % (repr(self.__class__)),
        )

    awaitable = _not_async
    __await__ = _not_async
    __aiter__ = _not_async
    __anext__ = _not_async
    asend = _not_async
    athrow = _not_async
    aclose = _not_async
