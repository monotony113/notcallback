# Not callback

Promise-style interfaces for callback-based asynchronous libraries.

```python
yield from (
    Promise.all(
        open_db_connection(),
        Promise.race(
            fetch_data_region_US(),
            fetch_data_region_DE(),
        ),
    )
    .then(parse_data)
    .then(update_rows)
    .then(commit)
    .catch(rollback)
    .finally_(close_connection)
)
```

## Contents

- [Note on asynchrony](#note-on-asynchrony)
- [Examples](#examples)
- [`async/await` and asyncio](#async)
- [API Reference](#api-reference)

----

This library imitates the logic of the `Promise` API found in ECMAScript.
It lets you restructure existing callback-style code into Promise workflows that are more readable.
It also provides a set of utility functions to let you better control the flow of your async programs.

This library is written using the [Promise/A+](https://promisesaplus.com/) specification as the reference. I try to recreate most of
the behaviors outlined in Promise/A+. However, the standards-compliance of the library has not been evaluated.
Most importantly:

## Note on asynchrony

**This is not an async framework.** There is no event loop magic happening in this library. You must
already be working with an existing asynchronous/concurrency framework (preferably a callback-based one) for this
library to be any useful. Otherwise, your Promises will simply run sequentially and block.

Here is an example of how one might turn [Scrapy](https://scrapy.org/)'s `Request` (which uses callbacks and is powered by [Twisted](https://twistedmatrix.com/trac/)) into
Promise:

```python
import json
import logging
from notcallback import Promise
from scrapy import Request

def fetch(**kwargs):
    """Create a Promise that will schedule a Request."""
    def executor(resolve, reject):
        # When the response is ready, the Promise gets resolved by Scrapy through the `resolve` function.
        yield Request(**kwargs, callback=resolve, errback=reject)
    return Promise(executor)

def start_requests(self):
    # Promises are iterable, and Scrapy will receive the yielded Requests
    return (
        # When the Promise is resolved, the handler in `.then()` gets executed.
        fetch('https://httpbin.org/ip')
        # A second Request is created from the response of the first one and is scheduled.
        .then(lambda response: fetch(json.loads(response.text)['origin']))
        # Print out the Response object from the second Request.
        .then(print)
        # If an exception was raised at anytime during the Promise, log it.
        .catch(lambda exc: logging.getLogger().error(exc))
    )
```

----

That being said, this library does provide a version of Promise that can work with the asyncio library.
See [`async/await` and asyncio](#async) for more info.

## Examples

If you are unfamiliar with how Promise works in JavaScript, a great starting point would be MDN's [Promise API reference](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise)
and the guide to [Using Promises](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Using_promises).
Most of the usage choices here should be analogous to how Promise is used in JavaScript (except for the generator syntax).

#### Creating a new Promise

```python
def executor(resolve, reject):
    ...
    if should_fulfill:
        yield from resolve(value)  # marks this Promise as resolved and begin the resolution process
                                   # eventually the Promise will become either fulfilled or rejected
    else:
        yield from reject(reason)  # rejects this Promise with the specified reason

promise = Promise(executor)
```

#### Evaluating a Promise

Promises themselves are generators. You complete a Promise by exhausting it.

```python
# Within another generator:
yield from promise
# In a loop:
for i in promise:
    ...
# As a coroutine (non async/await)
promise.send(None)
```

#### Accessing Promise properties

The main properties of a Promise are its state and value:

```python
>>> promise  # resolved with True
>>> promise.state
<PromiseState.FULFILLED: 'fulfilled'>
>>> promise.get()  # return the value of the Promise
True
>>> promise.is_settled
True
```

#### Providing handlers

The most important feature of Promise is the `.then(on_fulfill, on_reject)` instance method, which allows you
to add handlers to a Promise.

```python
def extract_keys(file):
    data = json.load(file)
    return data.keys()

def print_exception(exc):
    return print(repr(exc), file=sys.stderr)

>>> Promise.settle(Promise(correct_file).then(extract_keys, print_exception))
# Promise.settle runs a Promise until completion
<Promise at 0x10b4baa10 (fulfilled) => dict_keys([...])>

>>> Promise.settle(Promise(wrong_file).then(extract_keys).catch(print_exception)
# Promise.catch is a convenient method for adding exception handlers
FileNotFoundError: [Errno 2] No such file or directory: 'wrong_file.json'
<Promise at 0x10b4bad50 (fulfilled) => None>  
# The state is fulfilled because the exception was successfully handled
# The value is None because print() returns None.
```

#### Promise branching

A Promise can register multiple handlers. Handlers are evaluated in the order they are registered.

```python
conn = Promise(open_connection())
for recipient in bcc:
    Promise.settle(conn.then(update_rows(recipient)))
```

Note that Promises will always be evaluated only once: once they are settled, the executor will not be run again. However,
you can still attach handlers to an already settled Promise, and the resulting Promise, when evaluated, will run the handlers
immediately with the value of the settled Promise.

#### Promise chaining

**Promise().then() returns a new Promise,** which means you can chain multiple `.then()` handlers together

```python
def add(delta):
    """Create a handler that adds `delta` to the incoming `val` and returns it."""
    def accumulate(val=0):
        return val + delta
    return accumulate

>>> Promise.settle(
... Promise.resolve(-1)  # Promise.resolve() returns a Promise that is already fulfilled with the given value.
... .then(add(3))
... .then(add(6))
... .then(add(10))
... .then(print)
... )
18
```

If you call `.then()` without providing a rejection handler, the rejection is propagated down the Promise chain
like how an exception would bubble up the stack, until it encounters a Promise with a valid rejection handler.

```python
yield from (
    Promise.all(...)    # Uncaught exceptions raised in
    .then(parse_data)   # any
    .then(update_rows)  # of
    .then(commit)       # these
    .catch(rollback)    # handlers will be caught here.
    .finally_(close_connection)
)
```

#### Dynamic chaining

If you return another Promise in your `.then()` handlers, it will get resolved, and then the remaining handlers will
be attached to it.

```python
def load_page(url):
    def executor(resolve, reject):
        yield Request(url, callback=resolve, errback=reject)  # A Scrapy scenario
    return Promise(executor)

def next_page(response):
    ...
    page_id = response.get('pageId')
    if page_id:
        url = f'{response.url}&continueAt={page_id}'
        # Return a new Promise
        return load_page(url).then(next_page)

yield from load_page(start_url).then(next_page).then(finalize)
#    Promises are inserted into the chain here ^
# If there are multiple pages, the Promise chain will look like
# load_page => next_page => load_page => next_page => load_page => next_page => ... => finalize
```

#### Promise aggregation functions

This library provides all 4 static Promise methods available in JavaScript: `Promise.all()`, `Promise.race()`,
`Promise.all_settled()`, and `Promise.any()`.

For example:

**`Promise.all()`**: Only resolve when all the Promises in the list are fulfilled, and reject as soon as one of them rejects:

```python
Promise.all(register_hardware, config_simulators, load_assets).then(render).catch(warn)
```

**`Promise.race()`**: Resolve/reject as soon as one of the promises fulfills/rejects:
```python
Promise.race(*[access(file, region) for region in [
    'USNCalifornia',
    'USOregon',
    'USEOhio',
    'USNewYork',
]]).then(respond).catch(purge_cache)
```

## <span id="async">`async/await` and asyncio</span>

Although this library is only meant to work with async frameworks that predates [PEP 492](https://www.python.org/dev/peps/pep-0492/), it does come with
experimental support for the `async/await` syntax and asyncio.

Note: I designed the interface between Promise and asyncio mainly to learn how async functions in Python work. If you are already working with async functions and asyncio, you will probably find this library rarely useful.

----

Import Promise from `notcallback.async_` instead of `notcallback`.

```python
from notcallback.async_ import Promise
```

The async Promise is API-compatible with the non-async version, meaning it still works as an iterator/generator. 

However, with async Promise:
- `Promise` can be `await`ed

    `await` will return the Promise's value if it fulfills, or raise an exception if it rejects. This is very similar
    to how `async/await` works in JavaScript.

    ```python
    def key(resolve, _):
        yield from resolve(42)

    def authenticate(key):
        def executor(resolve, reject):
            if key == 42.1:
                yield from resolve()
            else:
                yield from reject('Access denied.')
        return Promise(executor)
    
    # within an async function
    >>> await Promise(key)
    42
    >>> await authenticate(await Promise(key))
    Traceback (most recent call last):
      ...
    notcallback.exceptions.PromiseRejection: PromiseRejection: 'Access denied.'
    ```

- If you **`yield`** an awaitable from you executor or handler function, `Promise` will schedule it for you:

    ```python
    # sleep with extra steps
    def sleep(sec):
        def do_sleep(resolve, reject):
            yield asyncio.sleep(sec)  # sleep here
            yield from resolve(repr(f'slept for {sec}s'))
        return Promise(do_sleep)

    async def main():
        return await sleep(5)

    >>> timeit.timeit(lambda: asyncio.run(main()), number=1)
    5.003376382999988
    ```

- If you need to yield values from your functions, Promises can be used as async iterators.

    ```python
    def sleepn(n):
        def sleep(resolve, reject):
            for sec in range(1, n + 1):
                yield sec
                yield asyncio.sleep(sec)
            yield from resolve()
        return Promise(sleep)

    async def main():
        async for sec in sleepn(3):
            print(sec)

    >>> timeit.timeit(lambda: asyncio.run(main()), number=1)
    1
    2
    3
    6.007059991999995
    ```

- **`Promise.all()`**, **`Promise.race()`**, **`Promise.all_settled()`**, and **`Promise.any()`** now accept an additional
`concurrently` keyword-only argument, which is default to `False`. Setting it to `True` allows Promises to run with asyncio
concurrently.

    ```python
    async def main():
        return await Promise.all(
            sleep(2),
            sleep(3),
            sleep(5),
            concurrently=True,  # run Promises concurrently
        )

    >>> timeit.timeit(lambda: asyncio.run(main()), number=1)
    5.003311451000002
    ```

    Note that for **`Promise.race()`** and **`Promise.any()`**, the time for the `await` expression to finish will always be
    the same as that of the **longest-running** Promise. This is so that all asyncio tasks are properly `await`ed. This means that these
    methods will not save you execution time.

    The usefulness of these two methods is in that the aggregated Promise will _settle_ early, and by that, all the handlers attached
    to the aggregated Promise will also run early:

    ```python
    def sleep(sec):
        def do_sleep(resolve, reject):
            yield asyncio.sleep(sec)
            yield from resolve(f'finished sleeping for {sec}s at {time.perf_counter():.3f}')
        return Promise(do_sleep)

    async def main():
        return await (
            Promise.race(
                sleep(2).then(print),
                sleep(3).then(print),
                sleep(5).then(print),
                concurrently=True,
            )
            .then(lambda _: print(f'Promise.race fulfilled at {time.perf_counter():.3f}'))
        )

    >>> total_time = timeit.timeit(lambda: asyncio.run(main()), number=1)
    finished sleeping for 2s at 14.542
    Promise.race fulfilled at 14.542
    finished sleeping for 3s at 15.541
    finished sleeping for 5s at 17.542
    >>> print(f'main coroutine finished in {total_time:.3f} seconds')
    main coroutine finished in 5.003 seconds
    ```

- _Using async functions as executors or handlers is **not** supported._

- _Known issues:_
    - Using Promises with asyncio functions:

        With async support, the `Promise` class will be a subclass of both `collections.abc.Generator` and
        `collections.abc.Coroutine`.

        The problem is that some asyncio functions, such as `asyncio.gather()`, perform runtime type checking on
        their arguments to see if they are awaitables or coroutines, and act differently. And, at least for
        `asyncio.gather()`, a `RuntimeError` will be thrown if it encounters a `yield from` expression at any point.

        This means that you can no longer do things like `yield from resolve()` when using `asyncio.gather()`.
        This is hard-wired into asyncio.

        If you need to use Promises with asyncio functions, and you do not need to `yield` any intermediate values
        (except for awaitables), then a solution will be to use the `.awaitable()` instance method, which is guaranteed to
        return a non-coroutine awaitable, which asyncio has no issue running.

## API Reference

#### Initializer

**`Promise(executor)`**

_Reference JavaScript function: [Promise() constructor](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/Promise)_

Turn a function into a Promise.

`executor` is a function that takes exactly 2 arguments, `resolve` and `reject`. `executor` can be a
regular function or a generator function. When it is ready to settle the Promise, `executor` should call
either `resolve()` or `reject()` with the fulfilled value/rejection reason as the only argument. Both
`resolve()` and `reject()` return a new generator, and `executor` must exhaust it, either by using `yield from`
or iterate over it.

#### Properties

**`Promise().state`**

Return the state of the Promise. This is a `notcallback.base.PromiseState` Enum which can be one of 3 values:
`PENDING`, `FULFILLED`, or `REJECTED`.

**`Promise().value`**

Return the value of the Promise if it is fulfilled, or the reason of rejection if it is rejected.

Attempting to retrieve the value of the Promise when it is still pending will result in a `PromisePending`
exception. This is so that the `None` that the Promise initially has as its "value" does not get mistaken
as a fulfillment or rejection whose value/reason is `None`.

See also: [**`Promise().get()`**](#get-method), [**`Promise().fulfilled(exc_type)`**](#fulfilled-rejected), [**`Promise().rejected(exc_type)`**](#fulfilled-rejected)

**`Promise().is_pending`**, **`Promise().is_fulfilled`**,
**`Promise().is_rejected`**, **`Promise().is_settled`**

These properties check whether a Promise is in a certain state.

#### Instance methods

**`Promise().then(on_fulfill, on_reject)`**

_Reference JavaScript function: [Promise.prototype.then()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/then)_

Return a new Promise that waits for this Promise to settle and then reacts accordingly.

Accepts 1 to 2 arguments. Must be callable.

If this Promise (the Promise whose `.then` is called) is fulfilled, `on_fulfill()` will be called with the fulfilled value;
if this Promise is rejected, `on_reject()` will be called with the reason of rejection.

`on_reject` may be omitted, and the rejection will be reraised (if the rejection value is not an exception, it will be wrapped in a
`PromiseRejection` exception).

The new Promise will resolve with the return value of the handler. If the returned value is another
`Promise`, that `Promise` will be settled first, and then the new Promise (the one returned by `.then`) will adopt
the state and value of that `Promise`.

If the handler raises an exception, the new Promise will be rejected with that exception.

**`Promise().catch(on_reject)`**

_Reference JavaScript function: [Promise.prototype.catch()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/catch)_

Convenience method for registering an exception handler. Sugar for `Promise().then(on_reject=on_reject)`.

**`Promise().finally_(on_settle)`**

_Reference JavaScript function: [Promise.prototype.finally()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/finally)_

Return a Promise whose handler will run regardless of how the previous Promise was settled.

`on_settle` can be a function or a generator function. It will be called with no argument.

The new Promise will adopt the state and value of the previous Promise. If an exception was raised
when running `on_settle`, the new Promise will reject with that exception.

**`Promise().get(default=None)`**<span id="get-method"></span>

Return the value of the Promise if it is FULFILLED, or the reason fpr rejection if its REJECTED.

Unlike the `Promise().value` property, which raises if the Promise is not settled, this method
will return `default` if the Promise's value is None regardless of its state.

**`Promise().fulfilled(default=None)`**, **`Promise().rejected(default=None)`**<span id="fulfilled-rejected"></span>

Return the value of the Promise only if it is in the specified state

Return the default value if it is not in that state, or if the value is `None`.

**`Promise().is_rejected_due_to(exc_type)`**

Check whether the Promise was rejected due to a specific type of exception.

Return `True` if the Promise is rejected and its value is an instance of `exc_class`, and `False` in
all other cases.

**`Promise().awaitable()`**

_Only available in `notcallback.async_.Promise`_

Return the Promise as an awaitable.

#### Class methods

**`Promise.all(*promises)`**

_Reference JavaScript function: [Promise.all()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/all)_

Return a new Promise that fulfills when all the provided Promises are fulfilled and rejects if any of them is rejected.

If it fulfills, meaning all the provided Promises are fulfilled, its handlers will receive a `tuple` that contains
the values of all the Promises, with order preserved.

If it rejects, it is rejected with the reason of the first rejection that occurred.

Note: 
- The Promises are evaluated sequentially.
- All of the Promises will be evaluated even if one of them rejects; only the execution order is different.

For a call that looks like:

```python
>>> Promise.all(promise1, promise2, promise3).then(on_fulfill).catch(on_reject)
```

where none of the Promises have async capabilities (meaning they run in order), if all Promises fulfill
successfully, the execution order will be

    promise1 => promise2 => promise3 => on_fulfill()

If e.g. promise2 rejects or raises an exception, it will be

    promise1 => promise2 => on_reject() => promise3

If there are multiple rejections, only the first one will have any effect.

_Only available in `notcallback.async_.Promise`_: accepts an additional `concurrently` keyword-only argument.

**`Promise.race(*promises)`**

_Reference JavaScript function: [Promise.race()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/all)_

Return a new Promise that fulfills/rejects as soon as one of the Promises fulfills/rejects.

It will adopt the state and value of the fulfilled/rejected Promise.

Note:
- The Promises are evaluated sequentially. This means that if your function does not have actual async capabilities,
the first Promise in the list will always "win the race."
- All of the Promises will be evaluated in all cases; only the execution order is different: the Promise's
`on_fulfill`/`on_reject` handlers are run immediately after the first Promise has settled.

_Only available in `notcallback.async_.Promise`_: accepts an additional `concurrently` keyword-only argument.

**`Promise.all_settled(*promises)`**

_Reference JavaScript function: [Promise.allSettled()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/allSettled)_

Return a new Promise that fulfills when all the Promises have settled i.e. either fulfilled or rejected.

The returned Promise always fulfills with the list of Promises provided.

_Only available in `notcallback.async_.Promise`_: accepts an additional `concurrently` keyword-only argument.

**`Promise.any(*promises)`**

_Reference JavaScript function: [Promise.any()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/any)_

Return a new Promise that ignores rejections among the provided Promises and fulfills upon the first fulfillment.

If all Promises reject, it will reject with a `PromiseAggregateError`.

Note:
- All Promises are evaluated regardless of their state; only the execution order is different: the Promise's
`on_fulfill`/`on_reject` handlers are run immediately after the first Promise that was fulfilled.

_Only available in `notcallback.async_.Promise`_: accepts an additional `concurrently` keyword-only argument.

**`Promise.resolve(value)`**

_Reference JavaScript function: [Promise.resolve()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/resolve)_

Return a new Promise that will resolve with `value` when it is evaluated. If the value is another Promise, this new Promise will
adopt the state and value of that Promise.

**`Promise.reject(reason)`**

_Reference JavaScript function: [Promise.reject()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/reject)_

Return a new Promise that will reject with `reason` when it is evaluated.

**`Promise.settle(promise)`**

A helper function that runs the Promise until it's settled and then return it. All intermediate values are discarded.
