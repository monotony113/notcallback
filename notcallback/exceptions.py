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

import warnings
from contextlib import contextmanager
from traceback import format_tb


class PromiseRejection(RuntimeError):
    def __init__(self, non_exc):
        self.value = non_exc

    def __str__(self):
        return self.__class__.__name__ + ': ' + str(self.value)


class StopEarly(GeneratorExit):
    pass


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
