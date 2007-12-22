from kaa.notifier import execute_in_timer, Timer, OneShotTimer, loop, \
     is_mainthread, execute_in_thread, execute_in_mainloop


class Foo(object):

    @execute_in_timer(Timer, 0.1, 'once')
    def poll(self, x):
        if not x:
            return False
        y = x.pop(0)
        print '1', y
        return True

    @execute_in_timer(Timer, 0.1, 'once')
    def poll2(self, x):
        if not x:
            return False
        y = x.pop(0)
        print '2', y
        return True

    @execute_in_thread('name')
    def foo(self):
        print 'foo is mainthread:', is_mainthread()
        self.bar()
        
    @execute_in_mainloop()
    def bar(self):
        print 'bar is mainthread:', is_mainthread()
        

@execute_in_timer(Timer, 0.1, 'override')
def poll(x):
    if not x:
        return False
    y = x.pop(0)
    print y
    return True


@execute_in_timer(OneShotTimer, 0.1)
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
loop()
