import sys
import kaa
import time

def update(progress):
    eta = int(progress.eta)
    sys.stdout.write('\r' + progress.get_progressbar(40))
    sys.stdout.write(' ETA %02d:%02d' % (eta / 60, eta % 60))
    sys.stdout.flush()

@kaa.threaded(progress=True)
def scan1(progress):
    progress.set(max=20)
    for i in range(20):
        progress.update()
        time.sleep(0.1)

@kaa.coroutine(interval=0.1, progress=True)
def scan2(progress):
    progress.set(max=20)
    for i in range(20):
        progress.update()
        yield kaa.NotFinished
        
@kaa.coroutine()
def test():
    async = scan1()
    async.progress.connect(update)
    yield async
    print
    async = scan2()
    async.progress.connect(update)
    yield async
    print
    sys.exit(0)
    
test()
kaa.main.run()
