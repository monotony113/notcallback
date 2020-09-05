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

"""The Promise class."""

import warnings
from collections import deque
from inspect import isgenerator

from .base import FULFILLED, PENDING, REJECTED, PromiseState
from .exceptions import (PromiseAggregateError, PromiseException,
                         PromisePending, PromiseRejection, PromiseWarning,
                         UnhandledPromiseRejectionWarning)
from .utils import (_CachedGeneratorFunc, as_generator_func,
                    one_line_warning_format)

try:
    from typing import (Any, Callable, Generator, List, Optional, Tuple, Type,
                        TypeVar, Union)
    PromiseType = TypeVar('PromiseType', bound='Promise')
    NoReturnCallable = Callable[..., None]
    NoReturnGenerator = Generator[Any, Any, None]
    GeneratorFunc = Callable[..., NoReturnGenerator]
except ImportError:
    pass

warnings.simplefilter('always', UnhandledPromiseRejectionWarning)


def _passthrough(value):
    """Return the value unmodified.

    This is the default on-fulfillment handler.
    """
    return value


def _reraise(exc):
    """Re-raise the exception.

    This is the default on-rejection handler.
    """
    if isinstance(exc, BaseException):
        raise exc
    raise PromiseRejection(exc)


class Promise:
    """The Promise class.

    This class is written using the Promise/A+ specification as the reference. It mimics most of the behaviors outlined
    in Promise/A+, except for one significant difference:

    This is **not** an asynchronous programming framework. The primary goal of Promise is to turn existing code that
    follows the callback-style paradigm into better-structured and easier-to-understand Promise-style workflow.

    The Promise class, on its own, does not offer any async capabilities. You must already be working with an existing
    async framework (such as Twisted) for it to be any useful.

    See also `notcallback.async_.Promise`, a subclass of this Promise that harnesses Python's own `asyncio` library.

    Interfaces
    ----------
    Promise conforms to `collections.abc.Iterator` and `.Generator`, meaning you can:

    - iterate over it:

    >>> for item in Promise(...): ...
    >>> next(Promise(...))

    - or use it as a generator:

    >>> Promise(...).send(None)
    >>> yield from Promise(...)


    A Promise can be in one of 3 states at any time: PENDING, FULFILLED, or REJECTED. It is PENDING
    when it is newly created or still running. When it is exhausted, that is, when it raises `StopIteration`,
    it is said to have been "settled": either FULFILLED or REJECTED. Whether it is fulfilled or rejected
    depends on how the Promise is configured.
    """

    def __init__(self, executor: Union[NoReturnCallable, GeneratorFunc], *, named=None):
        """Turn a function into a Promise.

        Parameters
        ----------
        executor : Callable
            A function to be turned into a Promise
        named : str, optional
            A name for the Promise, used only in str(), by default None

        Description
        -----------
        The `Promise()` initializer accepts a function called an "executor," which is either a regular function
        or a generator function. If a generator function is passed, the Promise will yield the values
        the generator yields during its evaluation.

        The executor must accept exactly 2 arguments, one called `resolve` and one called `reject`. Currently
        the Promise class does not allow passing any other additional arguments, you will need to encapsulate the
        objects you need in your function.

        Both `resolve` and `reject` are generator functions. At some point during the execution, the executor should
        call one of them with exactly 1 argument:

        - calling `resolve(value)` sets the Promise's state to FULFILLED and set its value to `value`;
        - calling `reject(reason)` sets the Promise's state to REJECTED and set its value to `reason`.

        Additionally, calling either `resolve` or `reject` will start the evaluation of any chained
        Promises created by methods such as `Promise.then()`, if any (and their `.then` Promises, too, until
        the entire Promise chain has been settled).

        As they are generator functions, you must manually exhaust them for the Promise to settle, and for
        chained Promises to run:

        >>> yield from resolve(value)
        >>> for _ in reject(reason): ...

        Merely calling them will NOT start the settle process.

        Ideally, the executor should return as soon as it has exhausted the resolve/reject handlers.
        However, if there are any code after finishing handler, they will still be executed. Only the first call to either
        `resolve` or `reject` will have an effect on the Promise, later calls will be silently ignored.

        The return value of the executor does not have significance and will be discarded.
        """
        self._state: PromiseState = PENDING
        self._value: Any = None

        self.__qualname__ = '%s at %s' % (self.__class__.__name__, hex(id(self)))

        self._exec: NoReturnGenerator
        self._hash: int
        self._name: Optional[str] = None
        self._prepare(executor, named)

        self._resolvers: deque = deque()

    def _prepare(self, executor, named=None):
        self._exec = as_generator_func(executor)(self._make_resolution, self._make_rejection)
        self._hash = hash(self._exec)
        if not self._name or named:
            self._name = named or executor.__name__

    @property
    def state(self) -> PromiseState:
        """Return the state of the Promise."""
        return self._state

    @property
    def value(self) -> Any:
        """Return the value of the Promise if it is FULFILLED, or the reason of rejection if its REJECTED.

        Attempting to retrieve the value of the Promise when it is still PENDING will result in a `PromisePending`
        exception. This is so that the `None` that the Promise initially has as its "value" does not get mistaken
        as a fulfillment or rejection whose value/reason is `None`.
        """
        if self._state is PENDING:
            raise PromisePending()
        return self._value

    @property
    def is_pending(self) -> bool:
        """Return True if the Promise's state is PENDING, and False otherwise."""
        return self._state is PENDING

    @property
    def is_settled(self) -> bool:
        """Return True if the Promise's state is either FULFILLED or REJECTED (settled)."""
        return self._state is not PENDING

    @property
    def is_fulfilled(self) -> bool:
        """Return True if the Promise's state is FULFILLED, and False otherwise."""
        return self._state is FULFILLED

    @property
    def is_rejected(self) -> bool:
        """Return True if the Promise's state is REJECTED, and False otherwise."""
        return self._state is REJECTED

    def get(self, default=None) -> Any:
        """Return the value of the Promise if it is FULFILLED, or the reason of rejection if its REJECTED.

        Unlike the `Promise().value` property, which raises if the Promise is not settled, this method
        will return `default` if the Promise's value is None regardless of its state.
        """
        return self._value if self._value is not None else default

    def fulfilled(self, default=None) -> Any:
        """Return the value of the Promise if it is FULFILLED, otherwise return None."""
        if self._state is FULFILLED and self._value is not None:
            return self._value
        return default

    def rejected(self, default=None) -> Any:
        """Return the reason for rejection of the Promise if it is REJECTED, otherwise return None."""
        if self._state is REJECTED and self._value is not None:
            return self._value
        return default

    def is_rejected_due_to(self, exc_class) -> bool:
        """Check whether the Promise was rejected due to a specific type of exception.

        Return True if the Promise is REJECTED and its value is an instance of `exc_class`, and False in
        all other cases.
        """
        return self._state is REJECTED and isinstance(self._value, exc_class)

    def _add_resolver(self, resolver):
        """Add a new resolver to the resolver queue."""
        self._resolvers.append(resolver)

    def _make_resolution(self, value=None):
        """Begin fulfilling this Promise with `value`.

        This is the handler interface exposed to the executor.
        """
        yield from self._resolve_promise(self, value)

    def _make_rejection(self, reason=None):
        """Begin rejecting this Promise with `reason`.

        This is the handler interface exposed to the executor.
        """
        yield from self._reject(reason)

    def _resolve(self, value):
        """Actually fulfill the Promise, and begin processing resolvers."""
        if self._state is PENDING:
            self._state = FULFILLED
            self._value = value
        yield from self._run_resolvers()

    def _reject(self, reason):
        """Actually reject the Promise, and begin processing resolvers."""
        if self._state is PENDING:
            self._state = REJECTED
            if isinstance(reason, PromiseRejection):
                reason = reason.value
            self._value = reason
        yield from self._run_resolvers()

    def _run_resolvers(self):
        """Process resolvers."""
        if not self._resolvers and self._state is REJECTED:
            with one_line_warning_format():
                warnings.warn(UnhandledPromiseRejectionWarning(self))
            return
        while self._resolvers:
            yield from self._resolvers.popleft()(self)

    def _adopt(self, other: PromiseType):
        """Make this Promise copy the state and value of another Promise."""
        if other._state is FULFILLED:
            yield from self._resolve(other._value)
        if other._state is REJECTED:
            yield from self._reject(other._value)

    @classmethod
    def _resolve_promise(cls, this: PromiseType, returned: Any):
        """Follow the Promise Resolution Procedure in the Promise/A+ specification."""
        if this is returned:
            raise PromiseException() from TypeError('A Promise cannot resolve to itself.')

        if isinstance(returned, cls):
            yield from returned
            yield from returned.then(this._make_resolution, this._make_rejection)
            return returned

        if getattr(returned, 'then', None) and callable(returned.then):
            return (yield from cls._resolve_promise_like(this, returned))

        return (yield from this._resolve(returned))

    def _successor_executor(self, resolve=None, reject=None):
        """Executor to be used in Promises created with Promise.then(), etc."""
        if self._state is PENDING:
            yield from self
        else:
            yield from self._run_resolvers()

    def then(self: PromiseType, on_fulfill=_passthrough, on_reject=_reraise) -> PromiseType:
        """Return a new Promise that waits for this Promise to settle and then reacts accordingly.

        Parameters
        ----------
        on_fulfill : Union[Callable, GeneratorFunction], optional
            handler that will be called when this Promise fulfills, by default _passthrough
        on_reject : Union[Callable, GeneratorFunction], optional
            handler that will be called when this Promise rejects, by default _reraise

        Returns
        -------
        Promise
            A new Promise that reacts to the resolution of this Promise.

        Description
        -----------
        `then()` takes at most 2 functions as arguments: `on_fulfill` and `on_reject`. Both should
        take exactly one argument, which is the result of the previous Promise (the Promise whose
        `.then()` method was called.

        Rules of Promise resolution
        ---------------------------
        When the previous Promise becomes settled, exactly one of the handlers will be called,

        - If it is FULFILLED, then `on_fulfill` will be called with the fulfilled value;
        - If it is REJECTED, then `on_reject` will be called with the reason of rejection;

        `on_fulfill` and `on_reject` can be regular functions or generator functions. If they are generator
        functions, the Promise will yield their intermediate values.

        Regardless of whether they are generator functions, their return value will be used to settle this new
        Promise (the previous Promise is unaffected):

        - If a handler returns a non-Promise object, the "then" Promise will be FULFILLED with that object.
        (`on_reject` returning a value has the meaning "it has successfully handled the rejection raised
        by the previous Promise);
        - If a handler returns an already fulfilled Promise, the "then" Promise will be FULFILLED with the
        value of that Promise;
        - If a handler returns an already rejected Promise, the "then" Promise will be REJECTED with the
        reason of that Promise;
        - If a handler returns a PENDING Promise, that returned Promise gets settled first, and the
        "then" Promise will adopt the state and value of that Promise;
        - If an exception was raised at any moment and was not caught, the "then" Promise is REJECTED with
        the exception.

        If you only provide `on_fulfill`, then the new Promise will have an implicit `on_reject` that reraises the
        Promise rejection if there is one.

        Chaining
        --------
        Because `Promise().then()` returns a new Promise, you can write chained Promises:

        >>> Promise(open_login).then(get_headers).then(parse_account_info).then(open_profile)

        Because any Promises returned by `on_fulfill` and `on_reject` are also resolved, you can dynamically insert
        new Promise into the chain:

        >>> def read_api(json):
        >>>     ...
        >>>     return Promise(fetch_additional_page)
        >>> Promise(open_login).then(read_api).then(parse_account_info).then(open_profile)
        #                                     ^
        #                                     .will fetch_additional_page here

        And because any rejection that was not handled is propagated down the chain, you can have a common
        exception handler for multiple actions:

        >>> Promise(open_connection).then(fetch_metadata).then(fetch_rows).then(on_reject=handle_exceptions)
            # or .catch(handle_exceptions)

        Branching
        ---------
        A Promise can have multiple `.then` handlers associated with it. When the Promise is settled, all of its
        handlers will be run, in the order that they were declared.

        >>> page = Promise(open_page)
        >>> page.then(validate_headers)
        >>> page.then(parse_html).then(fetch_additional_pages)

        Note: do remember that every call to `.then()` will return a new Promise, and the original Promise remain
        unchanged (except that it now has a new handler). The two `promise` variables in the following snippets
        reference two different Promise objects:

        >>> promise = Promise(...).then(...)

        >>> promise = Promise(...)
        >>> Promise.then(...)  # returns a new Promise

        However, regardless of which Promise in a chain/branch you decide to hold reference to, evaluating any Promise
        within a Promise chain/branch will cause the entire chain/tree to be evaluated.

        >>> p1 = Promise(...)
        >>> p2 = p1.then(...).catch(...)
        >>> p3 = p1.finally_(...).then(...)
        >>> p4 = p2.then(...)
        >>> # Evaluating any of p1, p2, p3, or p4 will cause all Promises in this snippet to settle.
        """
        cls: Type[PromiseType] = self.__class__
        promise = cls(
            self._successor_executor,
            named='%s|%s,%s' % (self._name, on_fulfill.__name__, on_reject.__name__),
        )
        handlers = {
            FULFILLED: _CachedGeneratorFunc(on_fulfill),
            REJECTED: _CachedGeneratorFunc(on_reject),
        }

        def resolver(settled: PromiseType):
            try:
                handler = handlers[settled._state](settled._value)
                yield from handler
                yield from self._resolve_promise(promise, handler.result)
            except (PromiseException, PromiseWarning, GeneratorExit, KeyboardInterrupt, SystemExit):
                raise
            except BaseException as e:
                yield from promise._reject(e)
        self._add_resolver(resolver)

        return promise

    def catch(self, on_reject=_reraise) -> PromiseType:
        """Return `Promise().then(<on_fulfill_passthrough>, on_reject)`.

        Parameters
        ----------
        on_reject : Union[Callable, GeneratorFunction], optional
            handler that will be called when this Promise rejects, by default _reraise

        Returns
        -------
        Promise
            A new Promise that catches and handles the rejection raised by previous Promises.
        """
        return self.then(_passthrough, on_reject)

    def finally_(self: PromiseType, on_settle=lambda: None) -> PromiseType:
        """Return a Promise whose handler will run regardless of how the previous Promise was settled.

        Parameters
        ----------
        on_settle : Union[Callable, GeneratorFunction], optional
            A function that should be run regardless of whether the previous Promise FULFILLED or REJECTED,

        Returns
        -------
        Promise
            A new Promise that will execute on_settle() and then adopt the state and value of the previous Promise.

        Description
        -----------
        Much like Python's `try-finally` block, the handler given to `.finally_()` will run no matter
        the previous Promise was FULFILLED or REJECTED.

        The `on_settle` function will receive no arguments. The idea is that a `finally_()` handler
        should perform tasks no matter what values the previous Promises have returned, such as closing
        files and cleaning up. The function should also not return anything, anything that's returned
        will be discarded.

        When the `on_settle` function finishes running, the "finally" Promise will adopt the state and value
        of the previous Promise.
        """
        cls: Type[PromiseType] = self.__class__
        promise = cls(self._successor_executor, named='chained:%s' % self._name)
        on_settle = _CachedGeneratorFunc(on_settle)

        def resolver(settled: PromiseType):
            try:
                yield from on_settle()
                yield from promise._adopt(self)
            except (PromiseException, PromiseWarning, GeneratorExit, KeyboardInterrupt, SystemExit):
                raise
            except BaseException as e:
                yield from promise._reject(e)
        self._add_resolver(resolver)

        return promise

    @classmethod
    def resolve(cls: Type[PromiseType], value=None) -> PromiseType:
        """Return a Promise that is already FULFILLED with `value`.

        If the `value` is another Promise, this Promise will adopt the state and value of that Promise.
        """
        return cls(lambda resolve, _: (yield from resolve(value)))

    @classmethod
    def reject(cls: Type[PromiseType], reason=None) -> PromiseType:
        """Return a Promise that is already REJECTED with `reason`."""
        return cls(lambda _, reject: (yield from reject(reason)))

    @classmethod
    def settle(cls, promise: PromiseType) -> PromiseType:
        """Run the Promise until it's settled.

        All intermediate values are discarded.
        """
        if not isinstance(promise, cls):
            raise TypeError(type(promise))
        for i in promise:
            pass
        return promise

    @classmethod
    def _make_multi_executor(cls, promises):
        def executor(resolve, reject):
            for p in promises:
                yield from p._successor_executor()
        return executor

    @classmethod
    def _ensure_promise(cls, promises):
        for p in promises:
            if not isinstance(p, cls):
                raise TypeError('%s is not an instance of %s' % (repr(p), repr(cls)))

    @classmethod
    def all(cls: Type[PromiseType], *promises: PromiseType) -> PromiseType:
        """Return a new Promise that fulfills when all the provided Promises are FULFILLED and rejects if any of them is REJECTED.

        If it fulfills, meaning all the provided Promises are fulfilled, its handlers will receive a `list` that contains
        the values of all the Promises, with order preserved.

        If it rejects, it is rejected with the reason of the first rejection that occured.

        Note
        ----
        - The Promises are evaluated sequentially.
        - All of the Promises will be evaluated even if one of them rejects; only the execution order is different.

        For a call that looks like:

            >>> Promise.all(promise1, promise2, promise3).then(on_fulfill).catch(on_reject)

        if all Promises fulfill successfully, the execution order will be

            promise1 => promise2 => promise3 => on_fulfill()

        If e.g. promise2 rejects or raises an exception, it will be

            promise1 => promise2 => on_reject() => promise3

        - If there are multiple rejections, only the first one will have any effect.
        """
        cls._ensure_promise(promises)
        fulfillments = {}
        promise = cls(cls._make_multi_executor(promises), named='Promise.all')

        def resolver(settled: PromiseType):
            if settled._state is REJECTED:
                yield from promise._reject(settled._value)
            fulfillments[settled] = settled._value
            if len(fulfillments) == len(promises):
                results = [fulfillments[p] for p in promises]
                yield from promise._resolve(results)

        for p in promises:
            p._add_resolver(resolver)
        return promise

    @classmethod
    def race(cls: Type[PromiseType], *promises: PromiseType) -> PromiseType:
        """Return a new Promise that fulfills/rejects as soon as one of the Promises fulfills/rejects.

        It will adopt the state and value of the FULFILLED/REJECTED Promise.

        Note
        ----
        - The Promises are evaluated sequentially. This means that if your does not have actual async capabilities,
        the first Promise in the list will always be the one that "wins the race."
        - All of the Promises will be evaluated in all cases; only the execution order is different: the Promise's
        `on_fulfill`/`on_reject` handlers are run immediately after the first Promise has settled.
        """
        cls._ensure_promise(promises)
        promise = cls(cls._make_multi_executor(promises), named='Promise.race')

        def resolver(settled: PromiseType):
            yield from promise._adopt(settled)

        for p in promises:
            p._add_resolver(resolver)
        return promise

    @classmethod
    def all_settled(cls: Type[PromiseType], *promises: PromiseType) -> PromiseType:
        """Return a new Promise that fulfills when all the Promises have settled i.e. either FULFILLED or REJECTED.

        This Promise always fulfills with the list of Promises provided.
        """
        cls._ensure_promise(promises)
        settle_count = 0
        promise = cls(cls._make_multi_executor(promises), named='Promise.all_settled')

        def resolver(settled: PromiseType):
            nonlocal settle_count
            settle_count += 1
            if settle_count == len(promises):
                yield from promise._resolve(promises)

        for p in promises:
            p._add_resolver(resolver)
        return promise

    @classmethod
    def any(cls: Type[PromiseType], *promises: PromiseType) -> PromiseType:
        """Return a new Promise that ignore rejections among the provided Promises and fulfills upon the first fulfillment.

        If all Promises reject, it will reject with a PromiseAggregateError.

        Note
        ----
        - All Promises are evaluated regardless of fulfillments.
        """
        cls._ensure_promise(promises)
        settle_count = 0
        promise = cls(cls._make_multi_executor(promises), named='Promise.any')

        def resolver(settled: PromiseType):
            nonlocal settle_count
            settle_count += 1
            if settled._state is FULFILLED:
                yield from promise._adopt(settled)
            if settle_count == len(promises) and promise.is_pending:
                yield from promise._reject(PromiseAggregateError())

        for p in promises:
            p._add_resolver(resolver)
        return promise

    def __iter__(self):
        """Return self as the iterable."""
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
        except (PromiseException, PromiseWarning, StopIteration, GeneratorExit, KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:
            self._exec = self._reject(e)
            return self._dispatch_gen_method(self._exec.__next__)

    def __eq__(self, value):
        """Implement == (equality testing).

        Rules:
        -----
        - All PENDING Promises test unequal to all other Promises.
        - Two Promises are equal if they have the same state and their values test equal; if one or both of
        the values do not implement __eq__, return False.
        - Promises do not need to have the same executor to be considered equal.
        """
        try:
            return (
                self.__class__ is value.__class__
                and self._state is not PENDING
                and self._state is value._state
                and self._value == value._value
            )
        except NotImplementedError:
            return False

    def __hash__(self):
        """Implement hashing.

        The hash is produced by hashing the combination (tuple) the Promise class and the hash of the
        executor function.
        """
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
    def _resolve_promise_like(cls, this: PromiseType, obj):
        calls: List[Tuple[PromiseState, Any]] = []

        def on_fulfill(val):
            calls.append((FULFILLED, val))

        def on_reject(reason):
            calls.append((REJECTED, reason))

        try:
            promise = obj.then(on_fulfill, on_reject)
            if isgenerator(obj):
                yield from promise
        except (PromiseException, PromiseWarning, GeneratorExit, KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:
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

    def __getattr__(self, name):
        if name in {'awaitable', '__await__', '__aiter__', '__anext__', 'asend', 'athrow', 'aclose'}:
            return self._not_async
        return object.__getattribute__(self, name)
