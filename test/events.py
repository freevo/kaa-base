import kaa

FOO_EVENT = kaa.Event('FOO_EVENT')

def foobar(event):
    if event == 'FOO_EVENT':
        print 'got FOO'
    elif event == 'BAR_EVENT':
        print 'got BAR with %s' % event.arg

def foo(event):
    if event == 'FOO_EVENT':
        print 'foo got FOO'
    else:
        print 'This can not happen'

def all(event):
    print event
    
e = kaa.EventHandler(foobar)
e.register(('FOO_EVENT', 'BAR_EVENT'))

e = kaa.EventHandler(foo)
e.register((FOO_EVENT,))

e = kaa.EventHandler(all)
e.register([])

FOO_EVENT.post()
kaa.Event('BAR_EVENT').post(1)
kaa.Event('BAR_EVENT', 2).post()

kaa.main.run()
