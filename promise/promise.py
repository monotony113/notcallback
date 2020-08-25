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

# Let there be no callback hell ...

from __future__ import annotations

from collections.abc import Generator
from enum import Enum
from functools import wraps
from inspect import isgenerator, isgeneratorfunction
from queue import Empty, Queue
from typing import Any, Tuple


class PromiseState(Enum):
    PENDING = 'pending'
    FULFILLED = 'fulfilled'
    REJECTED = 'rejected'

    def __str__(self):
        return self.value


_ = PromiseState


def freezable(*, msg=None):
    def wrapper(cls):

        def _freeze(self):
            if self._frozen:
                return
            self._frozen = True

        def __setattr__(self, name, value):
            if self._frozen:
                raise ValueError(msg)
            return super(cls, self).__setattr__(name, value)

        cls.__setattr__ = __setattr__
        cls._freeze = _freeze
        cls._frozen = False
        return cls
    return wrapper


class CachedGeneratorFunc:

    @freezable(msg='Generator has already finished.')
    class CachedGenerator(Generator):
        def __init__(self, func, *args, **kwargs):
            self._func = func
            self._result = None

            self._func_is_generator = isgeneratorfunction(func)
            if self._func_is_generator:
                self._func = self._func(*args, **kwargs)
            else:
                self._args = args
                self._kwargs = kwargs

        def __next__(self):
            if not self._frozen:
                if not self._func_is_generator:
                    self._result = self._func(*self._args, **self._kwargs)
                else:
                    try:
                        return next(self._func)
                    except StopIteration as stop:
                        self._result = stop.value
                self._freeze()
            raise StopIteration(self._result)

        def send(self, value):
            if self._func_is_generator:
                return self._func.send(value)
            return super().send(value)

        def throw(self, typ, val=None, tb=None):
            if self._func_is_generator:
                return self._func.throw(typ, val=val, tb=tb)
            return super().throw(typ, val=val, tb=tb)

        @property
        def result(self):
            if not self._frozen:
                raise ValueError('Generator has not been run.')
            return self._result

    def __init__(self, func):
        if not callable(func):
            raise HandlerNotCallableError(repr(func) + ' is not callable.')
        if isinstance(func, self.__class__):
            self._func = func._func
        else:
            self._func = func

    def __call__(self, *args, **kwargs) -> CachedGeneratorFunc.CachedGenerator:
        return self.CachedGenerator(self._func, *args, **kwargs)

    @classmethod
    def noop(cls):
        def noop(*args, **kwargs):
            pass
        return CachedGeneratorFunc(noop)

    @classmethod
    def wrap(cls, func):
        return wraps(func)(cls(func))


def as_generator_func(func):
    if isgeneratorfunction(func):
        return func

    @wraps(func)
    def gen(*args, **kwargs):
        yield func(*args, **kwargs)
    return gen


def _resolve_promise(this: Promise, returned: Any):
    if this is returned:
        raise PromiseException() from TypeError('A Promise cannot resolve to itself.')

    if isinstance(returned, Promise):
        yield from returned
        this._adopt(returned)
        return returned

    if getattr(returned, 'then', None) and callable(returned.then):
        return (yield from _resolve_promise_like(this, returned))

    return (yield from this._resolve(returned))


def _resolve_promise_like(this: Promise, obj):
    calls: Tuple[PromiseState, Any] = []

    def on_fulfill(val):
        calls.append((_.FULFILLED, val))

    def on_reject(reason):
        calls.append((_.REJECTED, reason))

    try:
        promise = obj.then(on_fulfill, on_reject)
        if isgenerator(obj):
            yield from promise
    except PromiseException:
        raise
    except Exception as e:
        if not calls:
            calls.append((_.REJECTED, e))
    finally:
        if not calls:
            return (yield from this._resolve(obj))
        state, value = calls[0]
        if state is _.FULFILLED:
            return (yield from this._resolve(value))
        return (yield from this._reject(value))


def _make_executor(self):
    def start_predecessor(resolve, reject):
        if self._state is _.PENDING:
            yield from self
        else:
            yield from self._settle()
    return start_predecessor


@freezable(msg='Promise is already settled.')
class Promise(Generator):

    def __init__(self, executor, *args, **kwargs):
        self._state: _ = _.PENDING
        self._value: Any = None
        self._exec: Generator = as_generator_func(executor)(self._resolve, self._reject, *args, **kwargs)
        self._resolution = None

        self._resolvers: Queue = Queue()

    def _resolve(self, value):
        if self._state is _.PENDING:
            self._state = _.FULFILLED
            self._value = value
            self._freeze()
            yield from self._settle()

    def _reject(self, reason):
        if self._state is _.PENDING:
            self._state = _.REJECTED
            self._value = reason
            self._freeze()
            yield from self._settle()

    def _settle(self):
        try:
            while True:
                resolver = self._resolvers.get_nowait()
                yield from resolver(self)
                self._resolvers.task_done()
        except Empty:
            pass

    def _adopt(self, other: Promise):
        if other._state is _.FULFILLED:
            yield from self._resolve(other._value)
        if other._state is _.REJECTED:
            yield from self._reject(other._value)

    @staticmethod
    def _default_on_fulfill(value):
        return value

    @staticmethod
    def _default_on_reject(exc):
        if isinstance(exc, BaseException):
            raise exc
        raise PromiseRejection(exc)

    @property
    def state(self) -> PromiseState:
        return self._state

    @property
    def value(self) -> Any:
        if self._state is _.PENDING:
            raise ValueError('Promise is not settled yet.')
        return self._value

    @property
    def is_pending(self) -> bool:
        return self._state is _.PENDING

    @property
    def is_fulfilled(self) -> bool:
        return self._state is _.FULFILLED

    def then(self, on_fulfill=None, on_reject=None) -> Promise:
        if not on_fulfill:
            on_fulfill = self._default_on_fulfill
        if not on_reject:
            on_reject = self._default_on_reject

        on_fulfill = CachedGeneratorFunc(on_fulfill)
        on_reject = CachedGeneratorFunc(on_reject)

        promise = Promise(_make_executor(self))

        def resolver(settled: Promise):
            try:
                if settled._state is _.FULFILLED:
                    handler = on_fulfill(settled._value)
                elif settled._state is _.REJECTED:
                    handler = on_reject(settled._value)
                else:
                    raise UnexpectedPromiseStateError()

                yield from handler
                yield from _resolve_promise(promise, handler.result)

            except PromiseException:
                raise
            except Exception as e:
                yield from promise._reject(e)
        self._resolvers.put_nowait(resolver)

        return promise

    def catch(self, on_reject=None) -> Promise:
        return self.then(None, on_reject)

    def finally_(self, on_settle=None) -> Promise:
        if not on_settle:
            on_settle = CachedGeneratorFunc(lambda: None)
        else:
            on_settle = CachedGeneratorFunc(on_settle)

        promise = Promise(self._make_executor())

        def resolver(settled: Promise):
            try:
                yield from on_settle()
                yield from promise._adopt(self)
            except PromiseException:
                raise
            except Exception as e:
                yield from promise._reject(e)
        self._resolvers.put_nowait(resolver)

        return promise

    @classmethod
    def resolve(cls, value=None) -> Promise:
        p = Promise(CachedGeneratorFunc.noop())
        p._state = _.FULFILLED
        p._value = value
        p._freeze()
        return p

    @classmethod
    def reject(cls, reason=None) -> Promise:
        p = Promise(CachedGeneratorFunc.noop())
        p._state = _.REJECTED
        p._value = reason
        p._freeze()
        return p

    @classmethod
    def settle(cls, promise: Promise) -> Promise:
        if not isinstance(promise, Promise):
            raise TypeError(type(promise))
        for i in promise:
            pass
        return promise

    def __next__(self):
        try:
            return next(self._resolution) if self._resolution else next(self._exec)
        except StopIteration:
            raise
        except Exception as e:
            self._resolution = self._reject(e)
            return next(self._resolution)

    def __str__(self):
        s1 = '<Promise at %s (%s)' % (hex(id(self)), self._state.value)
        if self._state is _.PENDING:
            return s1 + '>'
        elif self._state is _.FULFILLED:
            return s1 + ' => ' + str(self._value) + '>'
        else:
            return s1 + ' => ' + repr(self._value) + '>'

    def __repr__(self):
        return repr(self.__str__())

    def send(self, value):
        return self._exec.send(value)

    def throw(self, typ, val=None, tb=None):
        return self._exec.throw(typ, val, tb)

    def __eq__(self, value):
        return (
            self.__class__ is value.__class__
            and self._state is not _.PENDING
            and self._state is value._state
            and self._value == value._value
        )


class PromiseException(Exception):
    pass


class PromiseRejection(RuntimeError):
    def __init__(self, non_exc):
        self.value = non_exc

    def __str__(self):
        return self.__class__.__name__ + ': ' + str(self.value)


class HandlerNotCallableError(PromiseException, TypeError):
    pass


class UnexpectedPromiseStateError(PromiseException, RuntimeError):
    pass
