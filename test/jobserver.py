import time
import logging

from kaa import ThreadCallback, loop

def foo(i):
    time.sleep(0.1)
    print i

logger = logging.getLogger()
formatter = logging.Formatter('%(levelname)s %(module)s'+\
                              '(%(lineno)s): %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

ThreadCallback(foo, 1).register('x')
ThreadCallback(foo, 2).register('x')
ThreadCallback(foo, 3).register('x', 5)
j = ThreadCallback(foo, 4)
j.register('x')
ThreadCallback(foo, 5).register('x')
ThreadCallback(foo, 6).register('y')
j.unregister()
loop()
