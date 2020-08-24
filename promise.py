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

import warnings
from collections.abc import Generator
from enum import Enum
from functools import wraps
from inspect import isgeneratorfunction
from traceback import format_tb
from typing import Any


class __(Enum):
    PENDING = 'pending'
    FULFILLED = 'fulfilled'
    REJECTED = 'rejected'


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


def _format_warning(message, category, filename, lineno, file=None, line=None):
    return '------\n%s:%s: %s: %s\n------\n' % (filename, lineno, category.__name__, message)


class EmptyGeneratorFunction:

    @freezable(msg='Generator has already finished.')
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

        @property
        def value(self):
            if not self._frozen:
                raise ValueError('Generator has not been run.')
            return self._result

    def __init__(self, func):
        self._func = func

    def __call__(self, *args, **kwargs):
        return self.EmptyGenerator(self._func, *args, **kwargs)

    @classmethod
    def ensure(cls, func):
        if isgeneratorfunction(func):
            return func
        return cls(func)


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
        self.state: __ = __.PENDING
        self.value: Any = None
        self._func: Generator = as_generator_func(func)(self._resolve, self._reject, *args, **kwargs)

    def _resolve(self, value):
        self.state = __.FULFILLED
        self.value = value
        self._freeze()

    def _reject(self, reason):
        self.state = __.REJECTED
        self.value = reason
        self._freeze()

    @staticmethod
    def _default_on_fulfill(value):
        pass

    @staticmethod
    def _default_on_reject(exc):
        raise exc

    def then(self, on_fulfill=None, on_reject=None) -> Promise:
        if not on_fulfill:
            on_fulfill = self._default_on_fulfill
        if not on_reject:
            on_reject = self._default_on_reject

        on_fulfill = EmptyGeneratorFunction.ensure(on_fulfill)
        on_reject = EmptyGeneratorFunction.ensure(on_reject)

        def settle(resolve, reject):
            try:
                yield from self
                if self.state is __.FULFILLED:
                    fulfiller = on_fulfill(self.value)
                    yield from fulfiller
                    return resolve(fulfiller.value)
                elif self.state is __.REJECTED:
                    rejector = on_reject(self.value)
                    yield from rejector
                    return resolve(rejector.value)
                else:
                    raise ValueError(f'Unexpected Promise state {self.state}')
            except Exception as e:
                return reject(e)

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

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f'<Promise ({self.state.value}): {repr(self.value)}>'

    def send(self, value):
        return self._func.send(value)

    def throw(self, typ, val=None, tb=None):
        return self._func.throw(typ, val, tb)


class PromiseWarning(RuntimeWarning):
    pass


class UnhandledPromiseRejectionWarning(PromiseWarning):
    def __init__(self, exc):
        self.exc = exc

    def __str__(self):
        return (
            '\n' + '\n'.join(format_tb(tb=self.exc.__traceback__)) + '\n'
            f'{self.__class__.__name__}: from {repr(self.exc)}'
        )


def c(resolve, reject):
    return resolve(3)


def d(value):
    return 5


def e(_):
    raise RuntimeError()


def catch(_):
    print(repr(_))
    return 'Saved.'


if __name__ == '__main__':
    p = (
        Promise(c)
        .then(e)
        .catch(catch)
        .then(print)
        .then(d)
        .then(print)
        .then(lambda _: 15)
    )
    for _ in p:
        pass
    print(p)
