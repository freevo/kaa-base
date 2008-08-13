import kaa

@kaa.coroutine(policy=kaa.POLICY_SYNCHRONIZED)
def f(x):
    print 'in', x
    yield kaa.NotFinished
    print 'work1', x
    yield kaa.NotFinished
    print 'work2', x
    yield kaa.NotFinished
    print 'out', x
    
f(1)
f(2)
f(3)
kaa.main.run()
