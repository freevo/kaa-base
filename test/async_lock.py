import kaa.notifier

@kaa.notifier.yield_execution(lock=True)
def f(x):
    print 'in', x
    yield kaa.notifier.YieldContinue
    print 'work1', x
    yield kaa.notifier.YieldContinue
    print 'work2', x
    yield kaa.notifier.YieldContinue
    print 'out', x
    
f(1)
f(2)
f(3)
kaa.notifier.loop()
