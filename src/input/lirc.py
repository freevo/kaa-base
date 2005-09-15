import os, time
import kaa, kaa.notifier

_key_delay_map = [ 0.4, 0.2, 0.2, 0.15, 0.1 ]
_last_code = None
_key_delay_times = None
_last_key_time = 0

def input_check_lirc():
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
        return False
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


def init(appname = None, cfg = None):
    if cfg == None:
        cfgfile = os.path.expanduser("~/.lircrc")
    if appname == None:
        appname = "kaa"

    has_lirc = False
    try:
        import pylirc
        ver = pylirc.init(appname, cfgfile)
        if ver:
            pylirc.blocking(0)
            kaa.signals["idle"].connect(input_check_lirc)
            kaa.signals["shutdown"].connect(pylirc.exit)
            kaa.signals["lirc"] = kaa.notifier.Signal()
            has_lirc = True
    except ImportError:
        pass
    
    return has_lirc

if __name__ == "__main__":
    init()
    def cb(code):
        print "CODE", code
    kaa.signals["lirc"].connect(cb)
    kaa.main()
