import warnings
from contextlib import contextmanager
from traceback import format_tb


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
