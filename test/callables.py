# Test suite for kaa notifier classes

import kaa

def test(result, expected):
    if result != expected:
        raise ValueError, "expected: %s - got: %s" % (str(expected), str(result))

def cb_func(*args, **kwargs):
    return args, kwargs

class Cls(object):
    def meth(self, *args, **kwargs):
        return args, kwargs

##############################################################
# Callbacks
#######################
print "Callbacks ..." 

cb = kaa.Callable(cb_func)
test( cb(42), ((42,), {}) )

cb = kaa.Callable(cb_func, 42)
test( cb(), ((42,), {}) )

cb = kaa.Callable(cb_func)
test( cb(42, "foo", bar="baz"), ((42,"foo"), {"bar":"baz"}) )


cb_meth = Cls().meth
cb = kaa.Callable(cb_meth)
test( cb(42), ((42,), {}) )

cb = kaa.Callable(cb_meth)
del cb_meth
test( cb(42), ((42,), {}) )



##############################################################
# Weak callbacks
#######################
print "Weak Callbacks ..." 

def cb_func2(*args, **kwargs):
    return args, kwargs

cb = kaa.WeakCallable(cb_func)
test( cb(42), ((42,), {}) )

# Lambdas are not weakref'd
cb = kaa.WeakCallable(lambda arg: arg)
test( cb(42), 42)

# Functions are weakref'd
cb = kaa.WeakCallable(cb_func2)
del cb_func2
try:
    cb(42)
except kaa.CallableError:
    pass

cb_meth = Cls().meth
cb = kaa.WeakCallable(cb_meth)
del cb_meth
try:
    cb(42)
except kaa.CallableError:
    pass


##############################################################
# Timers
#######################
print "Timers ..." 

def test_OneShotTimer(arg):
    result.append(arg)

def test_Timer(arg):
    result.append(arg)

class Cls(object):
    def meth(self, arg):
        result.append(arg)

result = []
kaa.OneShotTimer(test_OneShotTimer, 42).start(0)
kaa.main.step()
test(result, [42])

result = []
kaa.OneShotTimer(Cls().meth, 42).start(0)
kaa.main.step()
test(result, [42])

result = []
kaa.WeakOneShotTimer(Cls().meth, 42).start(0)
kaa.main.step()
test(result, [])

result = []
cb = Cls().meth
kaa.WeakOneShotTimer(cb, 42).start(0)
kaa.main.step()
test(result, [42])

result = []
timer = kaa.Timer(Cls().meth, 42)
timer.start(0)
for i in range(5):
    kaa.main.step()
timer.stop()
test(result, [42, 42, 42, 42, 42])

result = []
# Tests proper destruction of a weak timer.  We hold a weak ref to Cls().meth
# and since there are no other refs, the weak timer never gets activated.
timer = kaa.WeakTimer(Cls().meth, 42)
timer.start(0)
# Notifier technically has nothing to do, so it may sleep for 30 seconds.
print '(This could take 30 seconds or so.)'
for i in range(2):
    kaa.main.step()
test(result, [])
test(timer.active, False)


##############################################################
# Signals 
#######################
print "Signals ..."

def cb_func(*arg):
    result.extend(arg)

class Cls(object):
    def meth(self, *arg):
        result.extend(arg)


sig = kaa.Signal()

sig.connect(cb_func, 42)

result = []
sig.emit()
test(result, [42])

result = []
sig.emit(42)
test(result, [42, 42])

test(sig.count(), 1)
sig.disconnect(cb_func)
test(sig.count(), 0)

sig.connect(Cls().meth, 42)

result = []
sig.emit()
test(result, [42])

sig.connect(Cls().meth, 42)
test(sig.count(), 2)

result = []
sig.emit()
test(result, [42, 42])

sig.disconnect_all()
test(sig.count(), 0)

cb = Cls().meth
sig.connect_weak(cb, 42)

result = []
sig.emit()
test(result, [42])

test(sig.count(), 1)
del cb
test(sig.count(), 0)
sig.emit()
test(sig.count(), 0)

result = []
sig.emit()
test(result, [])

cb = Cls().meth
sig.connect_weak(cb, Cls())
test(sig.count(), 0)
sig.emit()
test(sig.count(), 0)

# TODO: test threads too.
