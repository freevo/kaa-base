from kaa import timed, OneShotTimer, main, \
     is_mainthread, threaded, MAINTHREAD, POLICY_ONCE, POLICY_RESTART


class Foo(object):

    @timed(0.1, policy=POLICY_ONCE)
    def poll(self, x):
        if not x:
            return False
        y = x.pop(0)
        print '1', y
        return True

    @timed(0.1, policy=POLICY_ONCE)
    def poll2(self, x):
        if not x:
            return False
        y = x.pop(0)
        print '2', y
        return True

    @threaded('name')
    def foo(self):
        print 'foo is mainthread:', is_mainthread()
        self.bar()
        
    @threaded(MAINTHREAD)
    def bar(self):
        print 'bar is mainthread:', is_mainthread()
        

@timed(0.1, policy=POLICY_RESTART)
def poll(x):
    if not x:
        return False
    y = x.pop(0)
    print y
    return True


@timed(0.1, OneShotTimer, policy=POLICY_RESTART)
def bla(f, msg):
    print msg
    f.foo()
    f.bar()
    
f = Foo()
f.poll([0,1,2,3,4,5])
f.poll2(['a','b','c','d','e','f'])

poll([10,11,12,13,14,15])
bla(f, 'test')
bla(f, 'test2')
OneShotTimer(poll, [20,21,22,23,24]).start(0.3)
OneShotTimer(f.poll, [30,31,32,33,34]).start(0.3)
main.run()
