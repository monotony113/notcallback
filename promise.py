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
from typing import Any


class __(Enum):
    PENDING = 'pending'
    FULFILLED = 'fulfilled'
    REJECTED = 'rejected'


def freezable(error_func):
    def wrapper(cls):

        def _freeze(self):
            if self._frozen:
                return
            self._frozen = True

        def __setattr__(self, name, value):
            if self._frozen:
                raise error_func()
            return super(cls, self).__setattr__(name, value)

        cls.__setattr__ = __setattr__
        cls._freeze = _freeze
        cls._frozen = False
        return cls
    return wrapper


class EmptyGeneratorFunction:

    @freezable(lambda: ValueError('Generator has already finished.'))
    class EmptyGenerator(Generator):
        def __init__(self, func, *args, **kwargs):
            self._func = func
            self._args = args
            self._kwargs = kwargs
            self._result = None

        def __next__(self):
            if not self._frozen:
                self._result = self._func(*self._args, **self._kwargs)
                self._freeze()
            raise StopIteration(self._result)

        def send(self, value):
            return super().send(value)

        def throw(self, typ, val=None, tb=None):
            return super().throw(typ, val=val, tb=tb)

    def __init__(self, func):
        self._func = func

    def __call__(self, *args, **kwargs):
        return self.EmptyGenerator(self._func, *args, **kwargs)


def _as_generator_func(func):
    if isgeneratorfunction(func):
        return func

    @wraps(func)
    def gen(*args, **kwargs):
        yield func(*args, **kwargs)
    return gen


@freezable(lambda: ValueError('Promise is already settled.'))
class Promise(Generator):

    def __init__(self, func, *args, **kwargs):
        self.state: __ = __.PENDING
        self.value: Any = None
        self._func: Generator = _as_generator_func(func)(self._resolve, self._reject, *args, **kwargs)

    def _resolve(self, value):
        self.state = __.FULFILLED
        self.value = value
        self._freeze()

    def _reject(self, reason):
        self.state = __.REJECTED
        self.value = reason
        self._freeze()

    @staticmethod
    @_as_generator_func
    def _default_on_fulfill(value):
        pass

    @staticmethod
    @_as_generator_func
    def _default_on_reject(reason):
        raise UnhandledPromiseRejection() from reason

    def then(self, on_fulfill=None, on_reject=None) -> Promise:
        if not on_fulfill:
            on_fulfill = self._default_on_fulfill
        if not on_reject:
            on_reject = self._default_on_reject

        on_fulfill = _as_generator_func(on_fulfill)
        on_reject = _as_generator_func(on_reject)

        def settle(resolve, reject):
            try:
                try:
                    yield from self
                    yield from resolve(self.value)
                except Exception as e:
                    yield from on_reject(e)
            except Exception as e:
                yield from reject(e)

        new_promise = Promise(settle)
        return new_promise

    def catch(self, on_reject):
        return self.then(None, on_reject)

    def __next__(self):
        try:
            return next(self._func)
        except StopIteration:
            raise
        except Exception as e:
            self._reject(e)
            raise

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f'<Promise ({self.state.value}): {repr(self.value)}>'

    def send(self, value):
        return self._func.send(value)

    def throw(self, typ, val=None, tb=None):
        return self._func.throw(typ, val, tb)


class PromiseException(BaseException):
    pass


class UnhandledPromiseRejection(PromiseException):
    def __str__(self):
        s = super().__str__()
        if self.__cause__:
            s += f'from {repr(self.__cause__)}'
        return s


def c(resolve, reject):
    yield 3
    yield from resolve(4)


def d(value):
    print(value)
    return 5


if __name__ == '__main__':
    a = EmptyGeneratorFunction(d)
    b = a(3)
    [_ for _ in b]
    b._result = 5
