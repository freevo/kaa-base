import kaa

# method can be either
# 0: use thread based mainloop
# 1: use twisted thread based mainloop
# 2: use twisted experimental pynotifier
#    Known Bug: Twisted does not stop the reactor on SystemExit. If a
#    callback calls sys.exit() to shutdown the program, this won't work.
#    This has to be fixed in pynotifier
method = 2

# test auto-stop or stop with C-c
stop_on_exit = True

# get reactor
from twisted.internet import reactor

def twisted_callback1():
    print "twisted", kaa.is_mainthread()
    
def twisted_callback2():
    print "twisted (shutdown)", kaa.is_mainthread()
    if not stop_on_exit:
        return
    if method == 2:
        kaa.main.stop()
    else:
        reactor.stop()
    
def kaa_callback():
    print 'kaa', kaa.is_mainthread()

def shutdown_callback():
    print 'shutdown signal'

if method == 0:
    # select the thread loop and provide callbacks for a hander and how to
    # stop the real mainloop
    loop = kaa.main.select_notifier('thread', handler = reactor.callFromThread, \
                                    shutdown = reactor.stop)
    # stop the thread when twisted is done. Without this code the app will wait
    # until the nf thread will be done which will never happen.
    reactor.addSystemEventTrigger('after', 'shutdown', loop.stop)

if method == 1:
    # there is special code in kaa that does the same as method 0
    kaa.main.select_notifier('twisted')
if method == 2:
    # or use the real twisted mainloop
    kaa.main.select_notifier('twisted_experimental')

reactor.callLater(0.5, twisted_callback1)
reactor.callLater(1.5, twisted_callback2)
kaa.Timer(kaa_callback).start(1)
kaa.main.signals['shutdown'].connect(shutdown_callback)

if method == 2:
    # the twisted_experimental needs kaa.main.run()
    kaa.main.run()
else:
    reactor.run()

print 'done'
