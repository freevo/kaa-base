### FIXME: make this a class to make it possible to start one than one
### lirc instance (different app names or different rc files) and make
### it possible to stop it (e.g. freevo-daemon needs this)

import os, time
import kaa, kaa.notifier

_key_delay_map = [ 0.4, 0.2, 0.2, 0.15, 0.1 ]
_last_code = None
_key_delay_times = None
_last_key_time = 0
_dispatcher = None

def _handle_lirc_input():
    import pylirc

    global _key_delay_times, _last_code, _repeat_count, _last_key_time
    now = time.time()
    codes = pylirc.nextcode()

    if codes == None:
        # Either end of repeat, or just a delay between repeats...
        if _last_key_time + _key_delay_map[0] + 0.05 <= now:
            # Too long since the last key, so reset
            _last_key_time = 0
            _repeat_count = 0
        return
    elif codes == []:
        if not _key_delay_times:
            return True
        # Repeat last key iff we've passed the required key delay
        i = min(_repeat_count, len(_key_delay_times) - 2)
        delay = now - _key_delay_times[i][1]
        if delay >= _key_delay_times[i + 1][0]:
            codes = [ _last_code ]
            _key_delay_times[i + 1][1] = now
            _repeat_count += 1
        else:
            return True
    else:
        _key_delay_times = [[0, now]] + [ [x, 0] for x in _key_delay_map ]
        _repeat_count = 0
        
    _last_key_time = now
    for code in codes:
        kaa.signals["lirc"].emit(code)
        _last_code = code

    return True

def _handle_lirc_shutdown(pylirc):
    _dispatcher.unregister()
    pylirc.exit()

def init(appname = None, cfg = None):
    global _dispatcher

    if cfg == None:
        cfgfile = os.path.expanduser("~/.lircrc")
    if appname == None:
        appname = "kaa"

    has_lirc = False
    try:
        import pylirc
    except ImportError:
        return False

    try:
        fd = pylirc.init(appname, cfgfile)
    except IOError:
        return False

    if fd:
        pylirc.blocking(0)
        _dispatcher = kaa.notifier.SocketDispatcher(_handle_lirc_input)
        _dispatcher.register(fd)
        kaa.signals["shutdown"].connect(_handle_lirc_shutdown, pylirc)
        kaa.signals["lirc"] = kaa.notifier.Signal()
        has_lirc = True
    
    return has_lirc

if __name__ == "__main__":
    init()
    def cb(code):
        print "CODE", code
    kaa.signals["lirc"].connect(cb)
    kaa.main()
