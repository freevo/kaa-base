import sys
import kaa
from kaa.net import mdns

# some setup stuff
from dbus.mainloop.glib import DBusGMainLoop
DBusGMainLoop( set_as_default=True )
kaa.main.select_notifier('generic')
kaa.gobject_set_threaded()

def added(service, type):
    print 'found', service, type
    s = mdns.get_type(type)
    print 'all'
    for s in s.services:
        print '', s
    
def removed(service):
    print 'lost', service

if len(sys.argv) > 1:
    # go into provide mode
    # mdns.py ServiceName Port
    mdns.provide(sys.argv[1], '_test._tcp', int(sys.argv[2]), {'foo': 'bar'})
else:
    # go into listen mode
    # monitor printer
    s = mdns.get_type('_ipp._tcp')
    s.signals['added'].connect(added, '_ipp._tcp')
    # monitor test apps that provide stuff
    s = mdns.get_type('_test._tcp')
    s.signals['added'].connect(added, '_test._tcp')
    s.signals['removed'].connect(removed)
kaa.main.run()
