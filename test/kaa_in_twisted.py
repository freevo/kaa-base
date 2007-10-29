import sys
import kaa

import kaa.notifier

# get reactor
from twisted.internet import reactor

def twisted_callback1():
    print "twisted", kaa.notifier.is_mainthread()
    
def twisted_callback2():
    print "twisted (shutdown)", kaa.notifier.is_mainthread()
    reactor.stop()
    
def kaa_callback():
    print 'kaa', kaa.notifier.is_mainthread()
    # sys.exit(0)

kaa.notifier.init('thread', handler = reactor.callFromThread, shutdown = reactor.stop)
# there is special code in kaa.notifier that does the same by calling
# kaa.notifier.init('twisted')

reactor.callLater(2.5, twisted_callback1)
reactor.callLater(3.5, twisted_callback2)
kaa.notifier.Timer(kaa_callback).start(1)

reactor.run()

kaa.notifier.shutdown()
print 'stop'
