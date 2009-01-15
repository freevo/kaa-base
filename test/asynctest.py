import time
import os
import sys
import gc
import kaa
import kaa.rpc

sig = kaa.Signals('one', 'two', 'three')

class Server(object):
    def __init__(self):
        self.s = kaa.rpc.Server('test')
        self.s.connect(self)

    @kaa.rpc.expose('test1')
    def test1(self, x):
        return x, kaa.is_mainthread()
    
    @kaa.rpc.expose('test2')
    @kaa.threaded('yield')
    def test2(self, x):
        return x, kaa.is_mainthread()

    @kaa.rpc.expose('test3')
    @kaa.coroutine()
    def test3(self, x):
        yield kaa.NotFinished
        yield x

    @kaa.coroutine()
    def _test4(self, x):
        yield kaa.NotFinished
        yield x

    @kaa.rpc.expose('test4')
    def test4(self, x):
        return self._test4(x)

    @kaa.rpc.expose('test5')
    def test5(self, x):
        time.sleep(0.1)
        return x

    @kaa.rpc.expose('test6')
    def test6(self, x):
        raise ValueError('This exception is expected')

    @kaa.rpc.expose('shutdown')
    def shutdown(self):
        sys.exit(0)

def async(callback, *args, **kwargs):
    kaa.OneShotTimer(callback, *args, **kwargs).start(0.1)

@kaa.threaded('foo')
def thread(x):
    return x + 1 - 1

@kaa.threaded()
def thread2(c, x):
    # call rpc in thread using MainThreadCallback
    cb = kaa.MainThreadCallback(c.rpc)
    # we not only wait to get the InProgress back, we also wait
    # for the real return from rpc
    #cb.set_async(False)
    x = cb('test5', x).wait()
    print x
    return x + 1

@kaa.coroutine()
def subyield():
    print 3
    yield kaa.NotFinished
    print 4
    yield 5

@kaa.coroutine()
def fast():
    yield 2

@kaa.coroutine()
def foo():

    pid = os.fork()
    if not pid:

        s = Server()
        kaa.main.run()
        print 'server down'
        sys.exit(0)

    print 1
    for f in ('fast', 'subyield'):
        x = eval(f)()
        if isinstance(x, kaa.InProgress):
            # this should happen when calling subyield
            print f, 'needs more time'
            yield x                     # waiting...
            # subyield is now done
            x = x.get_result()
        else:
            # this should happen for fast
            print f, 'was a yield function but did not stop'
        print x
    print 6

    # just break here and return again in the next mainloop iteration
    yield kaa.NotFinished

    # call some async function with different types of
    # results (given as parameter)
    
    callback = kaa.InProgressCallback()
    async(callback, 7, 8)
    yield callback
    print callback.get_result()                # (7, 8)

    callback = kaa.InProgressCallback()
    async(callback)
    yield callback
    print callback.get_result()                # None

    callback = kaa.InProgressCallback()
    async(callback, 9)
    yield callback
    print callback.get_result()                # 9

    callback = kaa.InProgressCallback()
    async(callback, foo=10)
    yield callback
    print callback.get_result()                # 10

    callback = kaa.InProgressCallback()
    async(callback, foo=11, bar=12)
    yield callback
    print callback.get_result()                # {'foo': 11, 'bar': 12}

    x = thread(13)
    # this is also an InProgress object
    yield x
    print x.get_result()                           # 13

    x = thread('crash')
    try:
        # the thread raised an exception, so x() will
        # raise it here
        yield x
        print x.get_result()
        print 'crash test failed'
    except:
        print 'crash test ok'
        
    print 14

    print 'connect to server'
    while 1:
        try:
            c = kaa.rpc.Client('test')
            break
        except Exception, e:
            time.sleep(0.1)
            print e
            pass
    print 'server tests'

    # normal rpc
    result = c.rpc('test1', 15)
    yield result
    print result.get_result()

    # rpc in a thread
    result = c.rpc('test2', 16)
    yield result
    print result.get_result()
    
    # rpc with yield direct
    result = c.rpc('test3', 17)
    yield result
    print result.get_result()
    
    # rpc with yield indirect
    result = c.rpc('test4', 18)
    yield result
    print result.get_result()
    
    # rpc with yield error
    result = c.rpc('crash')
    try:
        yield result
        result.get_result()
        print 'bad rpc test failed'
    except:
        print 'bad rpc test ok'

    # rpc with remote exception
    result = c.rpc('test6', 18)
    try:
        yield result
        result.get_result()
        print 'remote rpc exception test failed'
    except ValueError, e:
        print 'remote rpc exception test ok'
        print "========= A traceback (for rpc) is expected below:"
        print e

    # call rpc in thread
    x = thread2(c, 19)
    yield x                             # print 19
    print x.get_result()                           # 20
    
    # Test InProgressCallback destruction cleans up signal connection.
    ip = kaa.inprogress(sig['one'])
    assert(len(sig['one']) == 1)
    del ip
    gc.collect()
    assert(len(sig['one']) == 0)
    print 'InProgressCallback cleanup ok'

    # Test InProgressAny via Signals.any()
    kaa.OneShotTimer(sig['three'].emit, 'worked').start(0.5)
    print 'Testing InProgressAny, should return in 0.5s'
    n, args = yield sig.subset('one', 'three').any()
    print 'InProgressAny returned:', n, args
    # Force InProgressCallbacks implicitly created by any() to be deleted.
    gc.collect()
    # Verify that they _are_ deleted and detached from the signal.
    print sig['one']._callbacks
    assert(len(sig['one']) == 0)
    assert(n == 1)

    # Test InProgressAll via Signals.all()
    kaa.OneShotTimer(sig['one'].emit, 'result for sig one').start(0.5)
    kaa.OneShotTimer(sig['two'].emit, 'result for sig two').start(0.2)
    print 'Testing InProgressAll, should return in 0.5s'
    ip = yield sig.subset('one', 'two').all()
    print 'InProgressAll returned: %s -- %s' % (ip[0].result, ip[1].result)

    # normal rpc, we don't care about the answer
    c.rpc('shutdown')
    yield 21

def end(res):
    print res                           # 21
    # ugly, do some steps before server is down
    kaa.main.step()
    time.sleep(0.1)
    kaa.main.step()
    kaa.main.stop()
    
foo().connect(end)
kaa.main.run()
