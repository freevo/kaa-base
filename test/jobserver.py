import time
import logging

import kaa
from kaa import NamedThreadCallback

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

NamedThreadCallback('x', foo, 1)()
NamedThreadCallback('x', foo, 2)()
NamedThreadCallback(('x', 5), foo, 3)()
j = NamedThreadCallback('x', foo, 4)()
NamedThreadCallback('x', foo, 5)()
NamedThreadCallback('y', foo, 6)()
j.abort()
kaa.main.run()
