import sys
import logging

log = logging.getLogger()

def save_execution():
    """
    """
    def decorator(func):

        def newfunc(*args, **kwargs):
            try:
                func(*args, **kwargs)
            except (KeyboardInterrupt, SystemExit), e:
                sys.exit(0)
            except Exception, e:
                log.exception('crash:')

        newfunc.func_name = func.func_name
        return newfunc

    return decorator

