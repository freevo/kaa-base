import threading
import logging

import kaa.notifier
import nf_wrapper

# get logging object
log = logging.getLogger('notifier')

class ThreadLoop(threading.Thread):

    def __init__(self, interleave):
        super(ThreadLoop, self).__init__()
        self.interleave = interleave
        self.condition = threading.Semaphore(0)
        self.sleeping = False
        
    def handle(self):
        nf_wrapper.step(sleep = False)
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
        except (KeyboardInterrupt, SystemExit):
            pass
        except Exception, e:
            log.exception('loop')
        kaa.notifier.running = False
        kaa.notifier.shutdown()


class Wakeup(object):
    def __init__(self, loop, func):
        self.loop = loop
        self.func = func

    def __call__(self, *args, **kwargs):
        ret = self.func(*args, **kwargs)
        if self.loop.sleeping:
            kaa.notifier.wakeup()
        return ret


def init( handler ):
    """
    Init the notifier.
    """
    loop = ThreadLoop(handler)
    nf_wrapper.init( 'generic', use_pynotifier=False )
    # set main thread and init thread pipe
    kaa.notifier.set_current_as_mainthread()
    # adding a timer or socket is not thread safe in general but
    # an additional wakeup we don't need does not hurt. And in
    # simulation mode the step function does not modify the
    # internal variables.
    nf_wrapper.timer_add = Wakeup(loop, nf_wrapper.timer_add)
    nf_wrapper.socket_add = Wakeup(loop, nf_wrapper.socket_add)
    loop.start()
