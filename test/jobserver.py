import time
import logging

import kaa
from kaa import ThreadPoolCallable

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

ThreadPoolCallable('x', foo, 1)()
ThreadPoolCallable('x', foo, 2)()
ThreadPoolCallable(('x', 5), foo, 3)()
j = ThreadPoolCallable('x', foo, 4)()
ThreadPoolCallable('x', foo, 5)()
ThreadPoolCallable('y', foo, 6)()
j.abort()
kaa.main.run()
