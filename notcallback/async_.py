import asyncio
from typing import Any

from .exceptions import PromiseRejection


def with_async_addons(cls):
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
        if self.is_fulfilled:
            return self._value
        elif self.is_rejected:
            reason = self.value
            if isinstance(reason, BaseException):
                raise reason
            raise PromiseRejection(reason)

    async def awaitable(self) -> Any:
        return await self

    cls.__await__ = __await__
    cls.awaitable = awaitable

    return cls
