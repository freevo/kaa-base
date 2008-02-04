import sys
import kaa

# get reactor
from twisted.internet import reactor

def twisted_callback1():
    print "twisted", kaa.is_mainthread()
    
def twisted_callback2():
    print "twisted (shutdown)", kaa.is_mainthread()
    reactor.stop()
    
def kaa_callback():
    print 'kaa', kaa.is_mainthread()
    # sys.exit(0)

def shutdown_callback():
    print 'shutdown signal'
    
kaa.main.select_notifier('thread', handler = reactor.callFromThread, \
                         shutdown = reactor.stop)
# there is special code in kaa that does the same by calling
# kaa.main.select_notifier('twisted')

reactor.callLater(2.5, twisted_callback1)
reactor.callLater(3.5, twisted_callback2)
kaa.Timer(kaa_callback).start(1)
kaa.main.signals['shutdown'].connect(shutdown_callback)

reactor.run()

print 'done'
