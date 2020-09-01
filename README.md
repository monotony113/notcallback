# Not Callback.

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

This library imitates the logic of the `Promise` API found in ECMAScript.
It lets you restructure existing callback-style code into Promise workflows that are more readable.
It also provides a set of utility functions to let you better control the flow of your async programs.

This library is written using the [Promise/A+] specification as the reference. I try to recreate most of
the behaviors outlined in Promise/A+. However, the standards-compliance of the library has not been evaluated.

## Note on "asynchronous"

**This is not an async framework.** There is no event loop magic happening in this library. You must
already be working with an existing asynchronous/concurrency framework (preferably a callback-based one) for this
library to be any useful. Otherwise, your Promises will simply run sequentially and blocking.

Here is an example of how one might turn Scrapy's Request (which uses callbacks and is powered by Twisted) into
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
See another chapter for more info.

## Examples

If you are unfamiliar with how Promise works in JavaScript, a great starting point would be MDN's [Promise API reference]
and the guide to [Using Promises].
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

Promises themselves are generators. You complete a Promise by exhausting the it.

```python
# In another generator:
yield from promise
# Using a loop:
for i in promise:
    ...
# Like a coroutine (non async/await)
promise.send(None)
```

#### Accessing Promise properties

The main properties of a Promise are its state and value

```python
>>> promise  # resolved with True
>>> promise.state
<PromiseState.FULFILLED: 'fulfilled'>
>>> promise.value
True
>>> promise.is_settled
True
```

#### Providing handlers

The most powerful feature of Promise is the `.then(on_fulfill, on_reject)` instance method, which allows you
to add handlers to a Promise.

```python
def extract_keys(file):
    data = json.load(file)
    return data.keys()

def print_exception(exc):
    return print(repr(exc), file=sys.stderr)

>>> Promise.settle(Promise(correct_file).then(extract_keys, print_exception))  # Promise.settle runs a Promise until completion
<Promise at 0x10b4baa10 (fulfilled) => dict_keys([...])>

>>> Promise.settle(Promise(wrong_file).then(extract_keys).catch(print_exception)  # Promise.catch is a convenient method for adding exception handlers
FileNotFoundError: [Errno 2] No such file or directory: 'wrong_file.json'
<Promise at 0x10b4bad50 (fulfilled) => None>  # It is fulfilled because the exception was successfully handled
                                              # It is None because print returns None.
```

#### Promise branching

A Promise can register multiple handlers.

```python
conn = Promise(open_connection())
for recipient in bcc:
    for _ in conn.then(update_rows(recipient)):
        pass
```

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

If you call then without providing a rejection handler, the rejection is propagated down the Promise chain
like how an Exception would bubble up the stack, until it encounters a Promise with a valid rejection handler.

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

#### Promise aggregation utilities

This library provides all 4 static Promise methods available in JavaScript: `Promise.all()`, `Promise.race()`,
`Promise.all_settled()`, and `Promise.any()`.

For example:

**`Promise.all()`**: Only resolve when all Promises in the list are resolved, and reject as soon as one of the rejects:

```python
Promise.all(register_hardware, config_simulators, load_assets).then(render).catch(warn)
```

**`Promise.race()`**: Resolve/reject as soon as one of the promises resolves/rejects:
```python
Promise.race(*[access(file, region) for region in [
    'USNCalifornia',
    'USOregon',
    'USEOhio',
    'USNewYork',
]]).then(respond).catch(purge_cache)
```

## API Reference

**`Promise(executor)`**

**`Promise().then(on_fulfill, on_reject)`**

**`Promise().catch(on_reject)`**

**`Promise().finally_(on_settle)`**

**`Promise.all(*promises)`**

**`Promise.race(*promises)`**

**`Promise.all_settled(*promises)`**

**`Promise.any(*promises)`**

**`Promise().state`**

**`Promise().value`**

**`Promise().is_pending`**, **`Promise().is_fulfilled`**,

**`Promise().is_rejected`**, **`Promise().is_settled`**

**`Promise().is_rejected_due_to(exc_type)`**

**`Promise.resolve(value)`**

**`Promise.reject(reason)`**

**`Promise.settle(promise)`**

## `async/await` and asyncio
