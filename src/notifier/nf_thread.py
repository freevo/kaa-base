import threading
import logging

import kaa.notifier
import nf_wrapper

# get logging object
log = logging.getLogger('notifier')

class ThreadLoop(threading.Thread):

    def __init__(self, interleave, shutdown = None):
        super(ThreadLoop, self).__init__()
        self.interleave = interleave
        self.condition = threading.Semaphore(0)
        self.sleeping = False
        self.shutdown = kaa.notifier.shutdown
        if shutdown:
            self.shutdown = shutdown
        
    def handle(self):
        try:
            try:
                nf_wrapper.step(sleep = False)
            except (KeyboardInterrupt, SystemExit):
                kaa.notifier.running = False
        finally:
            self.condition.release()

    def run(self):
        kaa.notifier.running = True
        try:
            while True:
                self.sleeping = True
                nf_wrapper.step(simulate = True)
                self.sleeping = False
                if not kaa.notifier.running:
                    break
                self.interleave(self.handle)
                self.condition.acquire()
                if not kaa.notifier.running:
                    break
        except (KeyboardInterrupt, SystemExit):
            pass
        except Exception, e:
            log.exception('loop')
        kaa.notifier.running = False
        self.interleave(self.shutdown)


class Wakeup(object):
    def __init__(self, loop, func):
        self.loop = loop
        self.func = func

    def __call__(self, *args, **kwargs):
        ret = self.func(*args, **kwargs)
        if self.loop.sleeping:
            kaa.notifier.wakeup()
        return ret


def get_handler(module):
    """
    Use the thread based mainloop with twisted.
    """
    if module == 'twisted':
        # get reactor and return callback
        from twisted.internet import reactor
        return reactor.callFromThread, reactor.stop
    raise RuntimeError('no handler defined for thread mainloop')


def init( module, handler = None, shutdown = None, **options ):
    """
    Init the notifier.
    """
    if handler == None:
        handler, shutdown = get_handler(module)
    loop = ThreadLoop(handler, shutdown)
    nf_wrapper.init( 'generic', use_pynotifier=False, **options )
    # set main thread and init thread pipe
    kaa.notifier.set_current_as_mainthread()
    # adding a timer or socket is not thread safe in general but
    # an additional wakeup we don't need does not hurt. And in
    # simulation mode the step function does not modify the
    # internal variables.
    nf_wrapper.timer_add = Wakeup(loop, nf_wrapper.timer_add)
    nf_wrapper.socket_add = Wakeup(loop, nf_wrapper.socket_add)
    loop.start()
