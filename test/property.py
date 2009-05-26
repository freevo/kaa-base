#!/usr/bin/python
#
# This tests the property decorator in kaa.utils, which is designed to be
# forward-compatible with Python 2.6 and Python 3.0.  Demonstrates propety
# getters, setters, and deleters, with inheritance.
#
# See:
#   http://bugs.python.org/issue1416
#   http://permalink.gmane.org/gmane.comp.python.general/551183
#   http://bugs.python.org/issue1620

from kaa.utils import property

class A(object):
    def __init__(self):
        self._readonly = 42
        self._writable = 0

    @property
    def readonly(self):
        "readonly docstring"
        return self._readonly

    @property
    def writable(self):
        return self._writable

    @writable.setter
    def writable(self, value):
        self._writable = value


class B(A):
    @A.readonly.getter
    def readonly(self):
        "subclass readonly docstring"
        return super(B, self).readonly * 2

    @readonly.setter
    def readonly(self, value):
        # Ok, not exactly readonly anymore :)
        self._readonly = value

    @A.writable.deleter
    def writable(self):
        self._writable = None


a = A()
assert(a.readonly == 42)
try:
    a.readonly = 0
except AttributeError:
    pass
else:
    raise AttributeError('a.readonly was writable')

a.writable = a.readonly / 2
assert(a.writable == 21)

try:
    del a.writable
except AttributeError:
    pass
else:
    raise AttributeError('del a.writable did not raise exception as expected')

assert(A.readonly.__doc__ == 'readonly docstring')

b = B()
assert(b.readonly == 42*2)
b.readonly = 20
assert(b.readonly == 20*2)
del b.writable
assert(b.writable is None)

assert(B.readonly.__doc__ == 'subclass readonly docstring')
print 'All property tests ok.'

