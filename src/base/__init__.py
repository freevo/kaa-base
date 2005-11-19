import logging

from kaa.base.weakref import weakref

def create_logger(level = logging.WARNING):
    """
    Create a simple logging object for applicatins that don't want
    to create a logging handler on their own. You should always have
    a logging object.
    """
    log = logging.getLogger()
    # delete current handler
    for l in log.handlers:
        log.removeHandler(l)
    
    # Create a simple logger object
    if len(logging.getLogger().handlers) > 0:
        # there is already a logger, skipping
        print 'already there'
        return

    formatter = logging.Formatter('%(levelname)s %(module)s'+ \
                                  '(%(lineno)s): %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.setLevel(level)
