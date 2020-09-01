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

"""Common definitions."""

from enum import Enum


class PromiseState(Enum):
    """Enum of possible Promise states.

    A Promise can be in one of three states:

    - `PENDING`: When the Promise has not been settled. Promises are initialized with
    this state and remains `PENDING` during its evaluation.
    - `FULFILLED`: When the Promise has been successfully resolved without errors or
    rejections. A Promise in the `FULFILLED` state will have a value associated with it.
    - `REJECTED`: When the Promise is rejected with a value, an exception, or an exception
    was raised while it is being evaluated. A Promise in the `REJECTED` state will include
    the reason of its rejection, which is usually an Exception.

    A Promise that is either `FULFILLED` or `REJECTED` is said to have been "settled." A Promise
    that is settled cannot be changed to any other state, and cannot have its value/reason changed.
    """

    PENDING = 'pending'
    FULFILLED = 'fulfilled'
    REJECTED = 'rejected'

    def __str__(self):
        """Print PromiseState."""
        return self.value


PENDING = PromiseState.PENDING
FULFILLED = PromiseState.FULFILLED
REJECTED = PromiseState.REJECTED
