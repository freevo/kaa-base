from __future__ import with_statement
import threading
import kaa

class Test(object):

    def foo(self):
        with kaa.synchronized(self):
            print 5

    @kaa.synchronized()
    def bar(self, x, y):
        print 1, x, y


# threading.Lock does NOT work
lock = threading.RLock()
@kaa.synchronized(lock)
def foo():
    print 6

t = Test()

@kaa.synchronized(t)
def bar(x):
    print 7, x

@kaa.synchronized()
def zap(x):
    print 9, x

@kaa.synchronized()
def baz():
    print 10

t.bar(5, 9)
t.foo()

t2 = Test()
t2.foo()

foo()
bar(8)
zap(8)
baz()
