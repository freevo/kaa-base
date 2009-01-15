# import sys
import kaa

# install special kaa reactor
import kaa.reactor
kaa.reactor.install()

# get reactor
from twisted.internet import reactor

def twisted_callback1():
    print "twisted", kaa.is_mainthread()

def twisted_callback2():
    print "twisted (shutdown)", kaa.is_mainthread()
    # you can either call reactor.stop or kaa.main.stop
    reactor.stop()
#     kaa.main.stop()

def kaa_callback():
    print 'kaa', kaa.is_mainthread()
    # sys.exit(0)

reactor.callLater(0.5, twisted_callback1)
reactor.callLater(1.5, twisted_callback2)
kaa.Timer(kaa_callback).start(1)

# you can either call kaa.main.run() or reactor.run()
# reactor.run()
kaa.main.run()

print 'stop'
