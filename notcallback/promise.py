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

import warnings
from collections import deque
from collections.abc import Coroutine, Generator
from contextlib import contextmanager
from enum import Enum
from functools import wraps
from inspect import isgenerator, isgeneratorfunction
from traceback import format_tb
from typing import Any, Tuple


class PromiseState(Enum):
    PENDING = 'pending'
    FULFILLED = 'fulfilled'
    REJECTED = 'rejected'

    def __str__(self):
        return self.value


PENDING = PromiseState.PENDING
FULFILLED = PromiseState.FULFILLED
REJECTED = PromiseState.REJECTED


class _CachedGeneratorFunc:

    class _CachedGenerator(Generator):
        def __init__(self, func, *args, **kwargs):
            self._func = func
            self._result = None
            self._finished = False

            self._func_is_generator = isgeneratorfunction(func)
            if self._func_is_generator:
                self._func = self._func(*args, **kwargs)
            else:
                self._args = args
                self._kwargs = kwargs

        def __next__(self):
            if not self._finished:
                if not self._func_is_generator:
                    self._result = self._func(*self._args, **self._kwargs)
                else:
                    try:
                        return next(self._func)
                    except StopIteration as stop:
                        self._result = stop.value
                self._finished = True
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
            if not self._finished:
                raise ValueError('Generator has not been run.')
            return self._result

    def __init__(self, func):
        if not callable(func):
            raise HandlerNotCallableError(repr(func) + ' is not callable.')
        if isinstance(func, self.__class__):
            self._func = func._func
        else:
            self._func = func

    def __call__(self, *args, **kwargs) -> _CachedGeneratorFunc._CachedGenerator:
        return self._CachedGenerator(self._func, *args, **kwargs)

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


def _passthrough(value):
    return value


def _reraise(exc):
    if isinstance(exc, BaseException):
        raise exc
    raise PromiseRejection(exc)


class Promise(Coroutine, Generator):
    def __init__(self, executor):
        self._state: PromiseState = PENDING
        self._value: Any = None
        self._exec: Generator = as_generator_func(executor)(self._make_resolution, self._make_rejection)

        self._resolvers = deque()
        self._has_resolver = False
        self._in_progress = None

    def _add_resolver(self, resolver):
        self._resolvers.append(resolver)

    def _remove_default_resolver(self):
        if not self._has_resolver:
            self._resolvers.pop()
            self._has_resolver = True

    def _make_resolution(self, value):
        yield from self._resolve_promise(self, value)

    def _make_rejection(self, reason):
        yield from self._reject(reason)

    def _resolve(self, value):
        if self._state is PENDING:
            self._state = FULFILLED
            self._value = value
        yield from self._settle()

    def _reject(self, reason):
        if self._state is PENDING:
            self._state = REJECTED
            if isinstance(reason, PromiseRejection):
                reason = reason.value
            self._value = reason
        yield from self._settle()

    def _settle(self):
        while self._resolvers:
            yield from self._resolvers.popleft()(self)

    def _adopt(self, other: Promise):
        if other._state is FULFILLED:
            yield from self._resolve(other._value)
        if other._state is REJECTED:
            yield from self._reject(other._value)

    def _make_executor(self):
        def resolve_predecessor(resolve, reject):
            if self._state is PENDING:
                yield from self
            else:
                yield from self._settle()
        return resolve_predecessor

    @classmethod
    def _resolve_promise(cls, this: Promise, returned: Any):
        if this is returned:
            raise PromiseException() from TypeError('A Promise cannot resolve to itself.')

        if isinstance(returned, Promise):
            yield from returned
            yield from this._adopt(returned)
            return returned

        if getattr(returned, 'then', None) and callable(returned.then):
            return (yield from cls._resolve_promise_like(this, returned))

        return (yield from this._resolve(returned))

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

    def _begin_to(self, method=None, value=None):
        if not self._in_progress:
            self._in_progress = method(value)
        return self._in_progress

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
    def is_fulfilled(self) -> bool:
        return self._state is FULFILLED

    def then(self, on_fulfill=_passthrough, on_reject=_reraise) -> Promise:
        promise = Promise(self._make_executor())
        handlers = {
            FULFILLED: _CachedGeneratorFunc(on_fulfill),
            REJECTED: _CachedGeneratorFunc(on_reject),
        }

        def resolver(settled: Promise):
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
        promise = Promise(self._make_executor())
        on_settle = _CachedGeneratorFunc(on_settle)

        def resolver(settled: Promise):
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
        if not isinstance(promise, Promise):
            raise TypeError(type(promise))
        for i in promise:
            pass
        return promise

    @classmethod
    def all(cls, *promises) -> Promise:
        pass

    def __next__(self):
        try:
            if self._in_progress:
                return next(self._in_progress)
            return next(self._exec)
        except (StopIteration, PromiseWarning):
            raise
        except Exception as e:
            try:
                return next(self._begin_to(self._reject, e))
            except StopIteration:
                pass

    def send(self, value):
        try:
            if self._in_progress:
                return self._in_progress.send(value)
            return self._exec.send(value)
        except (StopIteration, PromiseWarning):
            raise
        except Exception as e:
            try:
                return self._begin_to(self._reject, e).send(None)
            except StopIteration:
                pass

    def throw(self, typ, val=None, tb=None):
        try:
            if self._in_progress:
                return self._in_progress.throw(typ, val, tb)
            return self._exec.throw(typ, val, tb)
        except (StopIteration, PromiseWarning):
            raise
        except Exception as e:
            try:
                return self._begin_to(self._reject, e).send(None)
            except StopIteration:
                pass

    def __await__(self):
        yield from self
        return self._value

    def __eq__(self, value):
        return (
            self.__class__ is value.__class__
            and self._state is not PENDING
            and self._state is value._state
            and self._value == value._value
        )

    def __str__(self):
        s1 = '<Promise at %s (%s)' % (hex(id(self)), self._state.value)
        if self._state is PENDING:
            return s1 + '>'
        elif self._state is FULFILLED:
            return s1 + ' => ' + str(self._value) + '>'
        else:
            return s1 + ' => ' + repr(self._value) + '>'

    def __repr__(self):
        return '<Promise at %s (%s): %s>' % (hex(id(self)), self._state.value, repr(self._value))


class PromiseRejection(RuntimeError):
    def __init__(self, non_exc):
        self.value = non_exc

    def __str__(self):
        return self.__class__.__name__ + ': ' + str(self.value)


class PromiseException(Exception):
    pass


class PromisePending(PromiseException):
    def __init__(self, *args, **kwargs):
        super().__init__('Promise has not been settled.', *args, **kwargs)


class PromiseLocked(PromiseException):
    def __init__(self, *args, **kwargs):
        super().__init__('Cannot change the state of an already settled Promise.', *args, **kwargs)


class HandlerNotCallableError(PromiseException, TypeError):
    pass


class PromiseWarning(RuntimeWarning):
    pass


class UnhandledPromiseRejectionWarning(PromiseWarning):
    def __init__(self, reason, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reason = reason

    def _print_warning(self):
        reason = self.reason
        warn = self.__class__.__name__ + ': Unhandled promise rejection: '
        if isinstance(reason, BaseException):
            tb = format_tb(reason.__traceback__)
            return (
                'Traceback (most recent call last):\n%s%s%s: %s\n'
                % (''.join(tb), warn, reason.__class__.__name__, str(reason))
            )
        else:
            return warn + str(reason)

    def __str__(self):
        return self.__class__.__name__ + ': ' + str(self.reason)

    @classmethod
    @contextmanager
    def about_to_warn(cls):
        fmt = warnings.formatwarning
        warnings.formatwarning = cls._formatwarning
        try:
            yield
        finally:
            warnings.formatwarning = fmt

    @classmethod
    def _formatwarning(cls, message, category, filename, lineno, file=None, line=None):
        return message._print_warning()


@as_generator_func
def _unhandled_rejection_warning(promise: Promise):
    if promise._state is REJECTED:
        with UnhandledPromiseRejectionWarning.about_to_warn():
            warnings.warn(UnhandledPromiseRejectionWarning(promise._value))
