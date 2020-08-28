import asyncio
from typing import Any


def async_compatible(cls):
    def _as_async(item):
        try:
            return asyncio.ensure_future(item)
        except TypeError:
            future = asyncio.Future()
            future.set_result(item)
            return future

    def __await__(self):
        for i in self:
            yield from _as_async(i)
        return self._value

    _send = cls.send
    _throw = cls.throw

    def send(self, value):
        return _as_async(_send(self, value))

    def throw(self, typ, val=None, tb=None):
        return _as_async(_throw(self, typ, val, tb))

    @classmethod
    async def await_settle(cls, promise) -> Any:
        return await promise

    cls.__await__ = __await__
    cls.send = send
    cls.throw = throw
    cls.await_settle = await_settle
    return cls
