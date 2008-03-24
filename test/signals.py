import kaa

def myfunc(value):
    print 'x', value
    
signals = kaa.Signals('foo', 'bar')
signals.connect('foo', myfunc)

signals['foo'].emit(1)
signals.emit('foo', 2)

sig2 = kaa.Signals(signals, 'new')
print sig2.keys()
