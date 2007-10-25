import time
from timer import OneShotTimer

class OneShotAtTimer(OneShotTimer):

    def schedule(self, hour=range(24), min=range(60), sec=0):
        if not isinstance(hour, (list, tuple)):
            hour = [ hour ]
        if not isinstance(min, (list, tuple)):
            min = [ min ]
        if not isinstance(sec, (list, tuple)):
            sec = [ sec ]
        self._timings = [ ( 5, sec), (4, min), (3, hour) ]
        self._schedule_next()


    def _schedule_next(self):
        ctime = time.time()
        next = list(time.localtime(ctime))
        for pos, values in self._timings:
            for v in values:
                if v > next[pos]:
                    next[pos] = v
                    self.start(time.mktime(next) - ctime)
                    return
            next[pos] = values[0]
        self.start(time.mktime(next + 24 * 60 * 60) - ctime)


class AtTimer(OneShotAtTimer):
    
    def __call__(self, *args, **kwargs):
        super(AtTimer,self).__call__(*args, **kwargs)
        self._schedule_next()
