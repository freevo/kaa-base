import kaa

def foo(event):
    if event == 'FOO_EVENT':
        print 'got FOO'
    elif event == 'BAR_EVENT':
        print 'got BAR with %s' % event.arg

e = kaa.EventHandler(foo)
e.register(('FOO_EVENT', 'BAR_EVENT'))

kaa.Event('FOO_EVENT').post()
kaa.Event('BAR_EVENT').post(1)
kaa.Event('BAR_EVENT', 2).post()

kaa.main.run()
