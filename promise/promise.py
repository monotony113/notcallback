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
from inspect import isgeneratorfunction
from queue import Empty, Queue
from typing import Any


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


class CachedGeneratorFunction:

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
        def value(self):
            if not self._frozen:
                raise ValueError('Generator has not been run.')
            return self._result

    def __init__(self, func):
        if not callable(func):
            raise HandlerNotCallableError(repr(func) + ' is not callable.')
        self._func = func

    def __call__(self, *args, **kwargs) -> CachedGeneratorFunction.CachedGenerator:
        return self.CachedGenerator(self._func, *args, **kwargs)

    @classmethod
    def noop(cls):
        def noop(*args, **kwargs):
            pass
        return CachedGeneratorFunction(noop)


def as_generator_func(func):
    if isgeneratorfunction(func):
        return func

    @wraps(func)
    def gen(*args, **kwargs):
        yield func(*args, **kwargs)
    return gen


@freezable(msg='Promise is already settled.')
class Promise(Generator):

    def __init__(self, func, *args, **kwargs):
        self._state: _ = _.PENDING
        self._value: Any = None
        self._func: Generator = as_generator_func(func)(self._resolve, self._reject, *args, **kwargs)

        self._settlers: Queue = Queue()

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
                settler = self._settlers.get_nowait()
                yield from settler(self)
                self._settlers.task_done()
        except Empty:
            pass

    @staticmethod
    def _default_on_fulfill(value):
        pass

    @staticmethod
    def _default_on_reject(exc):
        if isinstance(exc, BaseException):
            raise exc
        raise PromiseRejection(exc)

    def create_successor(self):
        def start_predecessor(resolve, reject):
            if self._state is _.PENDING:
                yield from self
            else:
                yield from self._settle()
        return start_predecessor

    @property
    def state(self) -> PromiseState:
        return self._state

    @property
    def value(self) -> Any:
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

        on_fulfill = CachedGeneratorFunction(on_fulfill)
        on_reject = CachedGeneratorFunction(on_reject)

        promise = Promise(self.create_successor())

        def respond(settled: Promise):
            try:
                if settled._state is _.FULFILLED:
                    responder = on_fulfill(settled.value)
                elif settled._state is _.REJECTED:
                    responder = on_reject(settled.value)
                else:
                    raise UnexpectedPromiseStateError()
                yield from responder
                yield from promise._resolve(responder.value)
            except PromiseException:
                raise
            except Exception as e:
                yield from promise._reject(e)
        self._settlers.put_nowait(respond)

        return promise

    def catch(self, on_reject=None) -> Promise:
        return self.then(None, on_reject)

    def finally_(self, on_settle=None) -> Promise:
        if not on_settle:
            on_settle = CachedGeneratorFunction(lambda: None)
        else:
            on_settle = CachedGeneratorFunction(on_settle)

        promise = Promise(self.create_successor())

        def respond(settled: Promise):
            try:
                yield from on_settle()
                if settled._state is _.FULFILLED:
                    yield from promise._resolve(settled._value)
                elif settled._state is _.REJECTED:
                    yield from promise._reject(settled._value)
                else:
                    raise UnexpectedPromiseStateError()
            except PromiseException:
                raise
            except Exception as e:
                yield from promise._reject(e)
        self._settlers.put_nowait(respond)

        return promise

    @classmethod
    def resolve(cls, value=None) -> Promise:
        p = Promise(CachedGeneratorFunction.noop())
        p._state = _.FULFILLED
        p._value = value
        p._freeze()
        return p

    @classmethod
    def reject(cls, reason=None) -> Promise:
        p = Promise(CachedGeneratorFunction.noop())
        p._state = _.REJECTED
        p._value = reason
        p._freeze()
        return p

    @classmethod
    def settle(cls, promise: Promise) -> Promise:
        for i in promise:
            pass
        return promise

    def __next__(self):
        try:
            return next(self._func)
        except StopIteration:
            raise
        except Exception as e:
            self._reject(e)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return '<Promise (' + self._state.value + ') => ' + repr(self._value) + '>'

    def send(self, value):
        return self._func.send(value)

    def throw(self, typ, val=None, tb=None):
        return self._func.throw(typ, val, tb)


class PromiseException(Exception):
    pass


class PromiseRejection(PromiseException):
    def __init__(self, non_exc):
        self.value = non_exc

    def __str__(self):
        return self.__class__.__name__ + ': ' + str(self.value)


class HandlerNotCallableError(PromiseException, TypeError):
    pass


class UnexpectedPromiseStateError(PromiseException, RuntimeError):
    pass
