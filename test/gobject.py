import kaa

class Test():
    
    @kaa.threaded(kaa.GOBJECT)
    @kaa.synchronized()
    def foo(self):
        import time
        time.sleep(0.4)
        return kaa.is_mainthread()

    @kaa.coroutine()
    def test(self):
        r = yield self.foo()
        print 'foo', kaa.is_mainthread(), r

    @kaa.synchronized()
    def has_to_wait(self):
        print 'go'
        
if 1:
    kaa.gobject_set_threaded()
else:
    kaa.main.select_notifier('gtk')

t = Test()
kaa.OneShotTimer(t.test).start(0.1)
kaa.OneShotTimer(t.has_to_wait).start(0.2)
kaa.main.run()
print 'done'
