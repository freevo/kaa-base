import time
from timer import OneShotTimer

class AtTimer(OneShotTimer):

    def schedule(self, hour=range(24), min=range(60), sec=0):
        if not isinstance(hour, (list, tuple)):
            hour = [ hour ]
        self._hour = 3, hour
        if not isinstance(min, (list, tuple)):
            min = [ min ]
        self._min = 4, min
        if not isinstance(sec, (list, tuple)):
            sec = [ sec ]
        self._sec = 5, sec
        self.start()


    def __call__(self, *args, **kwargs):
        super(AtTimer,self).__call__(*args, **kwargs)
        self.start()

        
    def _getnext(self):
        ctime = time.time()
        next = list(time.localtime(ctime))
        for pos, values in ( self._sec, self._min, self._hour ):
            for v in values:
                if v > next[pos]:
                    next[pos] = v
                    return time.mktime(next) - ctime
            next[pos] = values[0]
        return time.mktime(next + 24 * 60 * 60) - ctime
        
    def start(self):
        super(AtTimer,self).start(self._getnext())
